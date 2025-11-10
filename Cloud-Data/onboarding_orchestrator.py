import os, json, boto3
from botocore.exceptions import BotoCoreError, ClientError

LAMBDA = boto3.client("lambda")

def _env(n):
    v = os.environ.get(n)
    if not v:
        raise RuntimeError(f"Missing env var {n}")
    return v

# ---- Child function ARNs ----
MAP = {
    "extract_id_from_s3": _env("FN_EXTRACT_ID"),
    "verify_identity":    _env("FN_VERIFY_ID"),
    "create_customer":    _env("FN_CREATE_CUSTOMER"),
}

DEFAULT_BUCKET = os.environ.get("UPLOAD_BUCKET", "")

def _safe_json_loads(s):
    try: return json.loads(s)
    except Exception: return None

def _params_to_dict(p):
    out = {}
    if isinstance(p, list):
        for x in p:
            if isinstance(x, dict) and "name" in x:
                out[x.get("name")] = x.get("value")
    elif isinstance(p, dict):
        out.update(p)
    return out

def _unwrap_child_result(o):
    if isinstance(o, dict) and "body" in o:
        b = o["body"]
        if isinstance(b, dict): return b
        if isinstance(b, str):
            j = _safe_json_loads(b)
            if isinstance(j, dict):
                if "body" in j and isinstance(j["body"], str):
                    j2 = _safe_json_loads(j["body"])
                    return j2 if isinstance(j2, dict) else j
                return j
            return {"_raw_body": b}
    return o

def _invoke_child(arn, payload):
    try:
        r = LAMBDA.invoke(
            FunctionName=arn,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8"),
        )
        raw = r.get("Payload").read()
        data = _safe_json_loads(raw.decode("utf-8", errors="replace"))
        return _unwrap_child_result(data if data is not None else {"_raw": raw.decode("utf-8", "replace")})
    except Exception as e:
        return {"error": "INVOKE_EXCEPTION", "detail": str(e), "calledArn": arn, "payload": payload}

def _wrap_for_bedrock(event, fn, body_obj, session, prompt, state=None):
    try:
        txt = json.dumps(body_obj, separators=(",", ":")) if not isinstance(body_obj, str) else body_obj
    except Exception:
        txt = str(body_obj)
    resp = {"responseBody": {"TEXT": {"body": txt}}}
    out = {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": (event or {}).get("actionGroup"),
            "function": fn,
            "functionResponse": resp,
        },
        "sessionAttributes": session or {},
        "promptSessionAttributes": prompt or {},
    }
    if state: out["responseState"] = state
    return out

def _merge_defaults_for_extract(params, session_attrs):
    merged = dict(params or {})
    if not merged.get("bucket") and DEFAULT_BUCKET:
        merged["bucket"] = DEFAULT_BUCKET
    if not merged.get("country"):
        country = session_attrs.get("country") or session_attrs.get("session.country")
        if not country and isinstance(session_attrs.get("session"), dict):
            country = session_attrs["session"].get("country")
        if country: merged["country"] = country
    if not merged.get("sessionId") and not merged.get("key"):
        sid = session_attrs.get("sessionId") or session_attrs.get("session.sessionId")
        if not sid and isinstance(session_attrs.get("session"), dict):
            sid = session_attrs["session"].get("sessionId")
        if sid: merged["sessionId"] = sid
    return merged

def lambda_handler(event, context):
    try:
        fn = (event or {}).get("function")
        base = (fn or "").split("__")[-1] if fn else ""
        params = _params_to_dict((event or {}).get("parameters", []))
        sess = dict((event or {}).get("sessionAttributes") or {})
        prompt = dict((event or {}).get("promptSessionAttributes") or {})

        if base not in MAP:
            return _wrap_for_bedrock(event, fn,
                {"error":"UNKNOWN_FUNCTION","function":fn,"known":list(MAP.keys())},
                sess, prompt, "REPROMPT")

        if base == "extract_id_from_s3":
            params = _merge_defaults_for_extract(params, sess)

        child = _invoke_child(MAP[base], params)

        # ---- Auto-chain: extract -> verify -> create ----
        if base == "extract_id_from_s3" and isinstance(child, dict):
            sess["verificationStatus"] = sess.get("verificationStatus") or "UPLOADED"

            identity = (child.get("identity") or {})
            nid = (identity.get("nationalId") or "").strip()
            country = identity.get("country") or params.get("country") or sess.get("country")

            verify_res = None
            create_res = None

            if (child.get("status") == "OK") and nid and country:
                # VERIFY
                verify_payload = {"nationalId": nid, "country": country}
                verify_res = _invoke_child(MAP["verify_identity"], verify_payload)

                if isinstance(verify_res, dict) and verify_res.get("status") == "VERIFIED":
                    # VERIFIED -> CREATE
                    sess["verificationStatus"] = "VERIFIED"
                    prompt["verified.last4"] = nid[-4:]
                    prompt["verified.country"] = country

                    create_payload = {"verification": verify_res}
                    create_res = _invoke_child(MAP["create_customer"], create_payload)
                else:
                    sess["verificationStatus"] = "UPLOADED"

            body = {
                "extract": child,
                "verify": verify_res,
                "create": create_res,
                "_orchestrator": {
                    "called": base,
                    "autoChained": ("verify_identity -> create_customer"
                                    if create_res else
                                    "verify_identity" if verify_res else "none"),
                    "mergedParams": {k: v for k, v in params.items()
                                     if k in ("bucket","key","sessionId","country")}
                }
            }
            return _wrap_for_bedrock(event, fn, body, sess, prompt)

        # ---- Pass-through for verify_identity / create_customer ----
        body = child
        if isinstance(body, dict):
            body.setdefault("_orchestrator", {})
            body["_orchestrator"].update({
                "called": base,
                "mergedParams": {k: v for k, v in params.items()
                                 if k in ("bucket","key","sessionId","country")}
            })
        return _wrap_for_bedrock(event, fn, body, sess, prompt)

    except (BotoCoreError, ClientError) as e:
        return _wrap_for_bedrock(event, (event or {}).get("function"),
            {"error":"DOWNSTREAM_LAMBDA","detail":str(e)},
            (event or {}).get("sessionAttributes"),
            (event or {}).get("promptSessionAttributes"), "FAILURE")
    except Exception as e:
        return _wrap_for_bedrock(event, (event or {}).get("function"),
            {"error":"ORCHESTRATOR_EXCEPTION","detail":str(e)},
            (event or {}).get("sessionAttributes"),
            (event or {}).get("promptSessionAttributes"), "FAILURE")
