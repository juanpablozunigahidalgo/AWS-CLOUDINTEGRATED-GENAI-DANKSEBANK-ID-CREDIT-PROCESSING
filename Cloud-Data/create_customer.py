import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

# ---- Config ----
TABLE_NAME = os.environ.get("TABLE_NAME", "DanskeBankCustomers")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

# ---- CORS ----
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",  # en prod, restringe a tu(s) dominio(s)
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Requested-With,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}

def cors_response(status_code: int, payload: Any):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(payload),
    }

# ---- Utils ----
def normalize_text(s: Optional[str]) -> str:
    if not s:
        return ""
    s = ''.join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    return s.strip().lower()

def normalize_country(country: Optional[str]) -> str:
    if not country:
        return "DK"
    c = normalize_text(country)
    if c in ("dk", "danmark", "denmark"): return "DK"
    if c in ("se", "sweden", "sverige"):  return "SE"
    if c in ("no", "norway", "norge"):    return "NO"
    if c in ("fi", "finland", "suomi"):   return "FI"
    return "DK"

def generate_email(first_name: str, last_name: str) -> str:
    fname = normalize_text(first_name).replace(" ", "")
    lname = normalize_text(last_name).replace(" ", "")
    email = f"{fname}.{lname}@danskebank.com"
    # solo minúsculas, dígitos, punto y @
    email = re.sub(r"[^a-z0-9.@]", "", email)
    return email

def parse_event_any(e: Any) -> Dict[str, Any]:
    """Acepta dict, string JSON, o proxy {body:'...'} y devuelve dict."""
    if isinstance(e, dict) and "body" in e:
        body = e["body"]
        if isinstance(body, str) and body:
            try:    return json.loads(body)
            except json.JSONDecodeError: return {}
        if isinstance(body, dict): return body
        return {}
    if isinstance(e, str):
        try:    return json.loads(e)
        except json.JSONDecodeError: return {}
    return e if isinstance(e, dict) else {}

def extract_verification(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Acepta formas:
      1) {"verification": {...}}
      2) {...} ya con shape de verify_identity (status, registry_record, source)
      3) {"verification": {"statusCode":200,"body":"{...}"}}
      4) {"statusCode":200,"body":"{...}"}
    Devuelve dict de verificación normalizado.
    """
    # Caso 1
    if isinstance(payload.get("verification"), dict):
        v = payload["verification"]
        if "body" in v and isinstance(v["body"], str):
            try:    return json.loads(v["body"])
            except json.JSONDecodeError: pass
        return v

    # Caso 4: wrapper HTTP directo
    if "body" in payload and isinstance(payload["body"], str):
        try:
            inner = json.loads(payload["body"])
            if isinstance(inner, dict) and "status" in inner and "registry_record" in inner:
                return inner
            if isinstance(inner.get("verification"), dict):
                v = inner["verification"]
                if "body" in v and isinstance(v["body"], str):
                    return json.loads(v["body"])
                return v
        except json.JSONDecodeError:
            pass

    # Caso 2
    if "status" in payload and "registry_record" in payload:
        return payload

    return {}

# ---- Dynamo helpers ----
def get_existing_customer(pk: str, sk: str = "PROFILE") -> Optional[Dict[str, Any]]:
    try:
        res = table.get_item(Key={"PK": pk, "SK": sk})
        return res.get("Item")
    except ClientError as e:
        # Propaga el error para que lo maneje el handler
        raise

def put_customer_ddb(item: Dict[str, Any]) -> bool:
    """
    Inserta el item con idempotencia.
    Devuelve True si creó; False si ya existía (usando condición).
    """
    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(PK)"
        )
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False  # ya existía
        raise

# ---- Handler core ----
def handler_core(event) -> Dict[str, Any]:
    payload = parse_event_any(event)
    verification = extract_verification(payload)

    if not verification:
        vraw = payload.get("verification")
        if isinstance(vraw, str):
            try:    verification = json.loads(vraw)
            except json.JSONDecodeError: pass

    if not verification or not isinstance(verification, dict):
        return {"status": "ERROR", "reason": "Missing or invalid verification."}

    if str(verification.get("status")).upper() != "VERIFIED":
        return {"status": "ERROR", "reason": "Identity must be VERIFIED before registration."}

    reg = verification.get("registry_record") or {}
    source = verification.get("source", verification.get("country", "unknown"))

    # Campos mínimos del registro verificado
    national_id   = reg.get("national_id") or reg.get("nationalId")
    first_name    = reg.get("firstName")
    last_name     = reg.get("lastName")
    date_of_birth = reg.get("dateOfBirth")

    if not all([national_id, first_name, last_name, date_of_birth]):
        return {"status": "ERROR", "reason": "Missing fields in registry_record."}

    # País
    country_map = {"denmark": "DK", "sweden": "SE", "norway": "NO", "finland": "FI"}
    country = country_map.get(normalize_text(source), "DK")

    # Claves
    pk = f"{country}#{national_id}"
    sk = "PROFILE"

    # 1) Chequeo idempotente (rápido)
    existing = get_existing_customer(pk, sk)
    if existing:
        return {
            "status": "ALREADY_REGISTERED",
            "email": existing.get("email"),
            "customerId": existing.get("customerId"),
            "nationalId": existing.get("nationalId"),
            "country": existing.get("country"),
            "reason": "El usuario ya está registrado."
        }

    # 2) Crear (con condición anti-carrera)
    created_at = datetime.now(timezone.utc).isoformat()
    customer_id = str(uuid.uuid4())
    email = generate_email(first_name, last_name)

    item = {
        "PK": pk,
        "SK": sk,
        "customerId": customer_id,
        "firstName": first_name,
        "lastName": last_name,
        "dateOfBirth": date_of_birth,
        "nationalId": national_id,
        "country": country,
        "email": email,
        "source": source,
        "status": "REGISTERED",
        "createdAt": created_at,
        # GSI por email (opcional)
        "GSI1PK": email,
        "GSI1SK": created_at
    }

    try:
        created = put_customer_ddb(item)
        if created:
            return {
                "status": "REGISTERED",
                "email": email,
                "customerId": customer_id,
                "nationalId": national_id,
                "country": country,
                "reason": "Customer created from VERIFIED identity."
            }
        # Si la condición falló por carrera, leemos y devolvemos “ya registrado”
        existing = get_existing_customer(pk, sk) or {}
        return {
            "status": "ALREADY_REGISTERED",
            "email": existing.get("email", email),
            "customerId": existing.get("customerId"),
            "nationalId": national_id,
            "country": country,
            "reason": "El usuario ya está registrado."
        }
    except ClientError as e:
        return {"status": "ERROR", "reason": e.response.get("Error", {}).get("Message", str(e))}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}

# ---- Entradas/salidas HTTP con CORS ----
def lambda_handler(event, context):
    if isinstance(event, dict) and event.get("httpMethod") == "OPTIONS":
        return cors_response(200, {"ok": True})
    try:
        out = handler_core(event)
        return cors_response(200, out)
    except Exception as e:
        return cors_response(500, {"status": "ERROR", "reason": str(e)})
