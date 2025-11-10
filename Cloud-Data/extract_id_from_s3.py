import os
import json
import re
import base64
import logging
from datetime import datetime
from typing import Any, Dict, Tuple, List
import urllib.request
import urllib.error
import time

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# -------- env --------
REGION = os.environ.get("AWS_REGION", "eu-central-1")
WRITE_JSON = os.environ.get("WRITE_JSON", "true").strip().lower() == "true"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")  # e.g., gpt-4o, gpt-4o-mini
OPENAI_TIMEOUT = int(os.environ.get("OPENAI_TIMEOUT_SEC", "40"))
OPENAI_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "2"))

s3 = boto3.client("s3", region_name=REGION)

# ------------------------ helpers ------------------------

def _parse_event(e: Any) -> Dict[str, Any]:
    """Accept dict, {body:'...'}, or raw JSON string."""
    if isinstance(e, dict) and "body" in e:
        b = e["body"]
        if isinstance(b, str) and b:
            try:
                return json.loads(b)
            except json.JSONDecodeError:
                return {}
        if isinstance(b, dict):
            return b
        return {}
    if isinstance(e, str):
        try:
            return json.loads(e)
        except json.JSONDecodeError:
            return {}
    return e if isinstance(e, dict) else {}

def _get_obj_bytes(bucket: str, key: str) -> bytes:
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()

def _find_key_by_session(bucket: str, country: str, session_id: str) -> str:
    """Finds latest object under today's prefix that contains the sessionId."""
    today = datetime.utcnow()
    prefix = f"onboard/{(country or 'SE').upper()}/{today:%Y/%m/%d}/{session_id}/"
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    items = resp.get("Contents") or []
    if not items:
        return ""
    return sorted(items, key=lambda x: x["LastModified"], reverse=True)[0]["Key"]

# -------------------- country patterns & normalization ----------------------

def _regex_for_country(country: str) -> re.Pattern:
    c = (country or "SE").upper()
    if c == "SE":
        return re.compile(r"\b(?:\d{6}|\d{8})-?\d{4}\b")            # YYMMDD-XXXX or YYYYMMDD-XXXX
    if c == "DK":
        return re.compile(r"\b\d{6}-?\d{4}\b")                      # DDMMYY-XXXX
    if c == "NO":
        return re.compile(r"\b\d{11}\b")                            # 11 digits
    if c == "FI":
        return re.compile(r"\b\d{6}[-+A][0-9A-Za-z]{4}\b", re.I)    # DDMMYY[-+A]XXXX
    return re.compile(r".^")  # no match

def _normalize_id(national_id: str, country: str) -> str:
    if not national_id:
        return ""
    nid = national_id.strip().upper()
    # We keep whatever delimiter the model returned (hyphen often helpful).
    return nid

# -------------------- OpenAI calls ------------------------

def _clean_json_text(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = re.sub(r"^json", "", s, flags=re.I).strip()
    return s

def _openai_payload_strict(b64_jpeg: str, country: str) -> Dict[str, Any]:
    # Strong consent + JSON Schema to minimize refusals + schema drift
    schema = {
        "name": "national_id_schema",
        "schema": {
            "type": "object",
            "properties": {
                "nationalId": { "type": "string" }
            },
            "required": ["nationalId"],
            "additionalProperties": False
        },
        "strict": True
    }
    system = (
        "You are an OCR assistant used for user-consented KYC by the lawful holder of the document. "
        "Task: extract ONLY the national/personal identification number from the image. "
        "Output MUST strictly follow the provided JSON Schema."
    )
    user = (
        "Country code: {country}. The user gives consent. "
        "Find the personal identity number (synonyms by country):\n"
        "- SE: personnummer / personal identity number (YYMMDD-XXXX or YYYYMMDD-XXXX)\n"
        "- DK: CPR-nummer (DDMMYY-XXXX)\n"
        "- NO: fødselsnummer / personnummer (11 digits)\n"
        "- FI: henkilötunnus / HETU (DDMMYY[-+A]XXXX)\n"
        "Return JSON ONLY."
    ).format(country=country)

    return {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_jpeg}" }}
            ]}
        ],
        "temperature": 0,
        "max_tokens": 120,
        "response_format": {
            "type": "json_schema",
            "json_schema": schema
        }
    }

def _openai_payload_fallback(b64_jpeg: str, country: str) -> Dict[str, Any]:
    # Looser: allow the model to return candidates; we’ll pick with regex.
    system = (
        "You are an OCR assistant used for user-consented KYC by the document holder. "
        "Extract national/personal ID candidates from the image. If multiple appear, list them all. "
        "Return JSON only."
    )
    user = (
        "Country code: {country}. The user gives consent. "
        "Look for labels like: personnummer, CPR, fødselsnummer, henkilötunnus, HETU, ID number. "
        "Return JSON with keys: candidates (array of strings)."
    ).format(country=country)

    return {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_jpeg}" }}
            ]}
        ],
        "temperature": 0,
        "max_tokens": 180,
        "response_format": {"type": "json_object"}
    }

def _openai_post(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "User-Agent": "lambda-id-extract/openai-only-1.0"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=OPENAI_TIMEOUT) as r:
        resp = json.loads(r.read().decode("utf-8"))
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = msg.get("content")
    refusal = msg.get("refusal")
    return {"content": content, "refusal": refusal}, json.dumps(resp)  # raw for audit

def _extract_national_id_via_openai(img_bytes: bytes, country: str) -> Tuple[str, float, Dict[str, Any]]:
    """
    Returns (national_id, confidence, debug_info)
    Two attempts:
      1) strict JSON schema with single nationalId
      2) fallback candidates array; we pick with regex
    """
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    patt = _regex_for_country(country)

    # Attempt 1: strict
    try:
        payload = _openai_payload_strict(b64, country)
        msg, raw_resp = _openai_post(payload)
        text = msg.get("content")
        if text:
            clean = _clean_json_text(text)
            data = json.loads(clean)
            nid = (data.get("nationalId") or "").strip()
            if nid:
                m = patt.search(nid)
                if m:
                    return _normalize_id(m.group(0), country), 0.92, {"attempt":"strict", "raw": raw_resp}
                # if model returned a near-miss, try to extract inside it
                m2 = patt.search(text)
                if m2:
                    return _normalize_id(m2.group(0), country), 0.88, {"attempt":"strict-recovered", "raw": raw_resp}
        else:
            logger.warning("OpenAI strict attempt returned content=None; refusal=%s", msg.get("refusal"))
    except urllib.error.HTTPError as e:
        logger.warning("OpenAI HTTPError strict %s: %s", e.code, e.read().decode("utf-8", "ignore"))
    except Exception as e:
        logger.warning("OpenAI strict attempt failed: %s", e)

    # Attempt 2: fallback with candidates
    try:
        payload2 = _openai_payload_fallback(b64, country)
        msg2, raw_resp2 = _openai_post(payload2)
        text2 = msg2.get("content") or ""
        clean2 = _clean_json_text(text2)
        cand = []
        try:
            data2 = json.loads(clean2)
            cand = data2.get("candidates") or []
            if isinstance(cand, str):
                cand = [cand]
        except Exception:
            # try to fish IDs from any text the model produced
            cand = patt.findall(text2)

        # choose best candidate by regex (first full match)
        for item in cand:
            m = patt.search(str(item))
            if m:
                return _normalize_id(m.group(0), country), 0.80, {"attempt":"fallback", "raw": raw_resp2}

        # as a last resort, scan raw content
        m2 = patt.search(text2)
        if m2:
            return _normalize_id(m2.group(0), country), 0.75, {"attempt":"fallback-scan", "raw": raw_resp2}

        logger.warning("OpenAI fallback produced no valid candidate.")
        return "", 0.0, {"attempt":"fallback-none", "raw": raw_resp2}
    except urllib.error.HTTPError as e:
        logger.warning("OpenAI HTTPError fallback %s: %s", e.code, e.read().decode("utf-8", "ignore"))
    except Exception as e:
        logger.warning("OpenAI fallback attempt failed: %s", e)

    return "", 0.0, {"attempt":"none"}

# ------------------------ handler ------------------------

def lambda_handler(event, context):
    """
    Accepts:
      { "bucket": "...", "key": "onboard/.../id_front.jpg", "country": "SE" }
    or
      { "bucket": "...", "sessionId": "<uuid>", "country": "SE" }

    Returns:
      { "status": "OK", "identity": { "nationalId": "...", "country": "SE" }, "confidence": 0.9 }
    """
    try:
        payload = _parse_event(event)
        logger.info("event=%s", json.dumps(payload))

        bucket    = payload.get("bucket")
        key       = payload.get("key") or payload.get("keyPrefix")
        sessionId = payload.get("sessionId")
        country   = (payload.get("country") or "SE").upper()

        if not bucket:
            return {"status": "ERROR", "reason": "bucket is required"}
        if not key and sessionId:
            key = _find_key_by_session(bucket, country, sessionId)
        if not key:
            return {"status": "ERROR", "reason": "key or sessionId is required (no image found)"}

        img_bytes = _get_obj_bytes(bucket, key)

        # --- OpenAI only, with retry backoff ---
        national_id = ""
        confidence = 0.0
        debug = {}
        for attempt in range(OPENAI_MAX_RETRIES):
            nid, conf, dbg = _extract_national_id_via_openai(img_bytes, country)
            debug = dbg
            if nid:
                national_id, confidence = nid, conf
                break
            # small backoff
            time.sleep(0.8 * (attempt + 1))

        identity = {"nationalId": national_id or "", "country": country}

        if WRITE_JSON:
            try:
                audit = {
                    "openai_model": OPENAI_MODEL,
                    "attempt": debug.get("attempt"),
                    "identity": identity,
                    "confidence": confidence,
                    "source": {"bucket": bucket, "key": key},
                }
                # Limit raw dump size if present
                raw_dump = debug.get("raw")
                if raw_dump and len(raw_dump) > 10000:
                    raw_dump = raw_dump[:10000] + "...<truncated>"
                if raw_dump:
                    audit["raw_choice"] = raw_dump
                s3.put_object(
                    Bucket=bucket,
                    Key=f"{key}.extracted.json",
                    Body=json.dumps(audit, ensure_ascii=False).encode("utf-8"),
                    ContentType="application/json",
                )
            except Exception as e:
                logger.warning("audit write failed: %s", e)

        if not identity["nationalId"]:
            return {
                "status": "PARTIAL",
                "missing": ["nationalId"],
                "identity": identity,
                "confidence": confidence
            }

        return {"status": "OK", "identity": identity, "confidence": confidence}

    except Exception as e:
        logger.exception("extract_id_from_s3 failed")
        return {"status": "ERROR", "reason": str(e)}
