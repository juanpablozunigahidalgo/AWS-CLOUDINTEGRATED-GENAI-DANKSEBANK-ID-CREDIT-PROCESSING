import json
import unicodedata
from typing import Dict, Any, Optional

# --- Registros mock embebidos (referencias nacionales) ---

DK_CPR_REGISTRY: Dict[str, Dict[str, Any]] = {
    "123456-7890": {
        "firstName": "John",
        "lastName": "Doe",
        "dateOfBirth": "1985-04-12",
        "gender": "male",
        "address": "POC Street 1, 2100 Copenhagen",
        "maritalStatus": "married",
        "citizenship": ["Denmark"],
    },
    "160778-1234": {
        "firstName": "Maria",
        "lastName": "Larsen",
        "dateOfBirth": "1978-07-16",
        "gender": "female",
        "address": "Hovedgaden 10, 8000 Aarhus",
        "maritalStatus": "single",
        "citizenship": ["Denmark"],
    },
}

SE_SPAR_REGISTRY: Dict[str, Dict[str, Any]] = {
    "19800101-1230": {
        "firstName": "Anna",
        "lastName": "Svensson",
        "dateOfBirth": "1980-01-01",
        "gender": "female",
        "address": "Storgatan 1, 111 22 Stockholm",
        "maritalStatus": "married",
        "citizenship": ["Sweden"],
    },
    "19950715-8899": {
        "firstName": "Erik",
        "lastName": "Johansson",
        "dateOfBirth": "1995-07-15",
        "gender": "male",
        "address": "Västra Hamngatan 5, 411 17 Göteborg",
        "maritalStatus": "single",
        "citizenship": ["Sweden"],
    },
    "860714-1556": {
        "firstName": "Juan Pablo Rafael",
        "lastName": "Zúñiga Hidalgo",
        "dateOfBirth": "1986-07-14",
        "gender": "male",
        "address": "Molnvadersgatan 8",
        "maritalStatus": "single",
        "citizenship": ["Sweden"],
    },
}

NO_FOLKEREGISTER: Dict[str, Dict[str, Any]] = {
    "47010112345": {
        "firstName": "Ola",
        "lastName": "Nordmann",
        "dateOfBirth": "2001-01-01",
        "gender": "male",
        "address": "Karl Johans gate 1, 0154 Oslo",
        "maritalStatus": "single",
        "citizenship": ["Norway"],
    },
    "47020254321": {
        "firstName": "Kari",
        "lastName": "Nordmann",
        "dateOfBirth": "2002-02-02",
        "gender": "female",
        "address": "Bygdøy allé 20, 0262 Oslo",
        "maritalStatus": "married",
        "citizenship": ["Norway"],
    },
}

FI_POPULATION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "FI-120394-123X": {
        "firstName": "Matti",
        "lastName": "Korhonen",
        "dateOfBirth": "1994-03-12",
        "gender": "male",
        "address": "Mannerheimintie 10, 00100 Helsinki",
        "maritalStatus": "married",
        "citizenship": ["Finland"],
    },
    "FI-010180-999Y": {
        "firstName": "Liisa",
        "lastName": "Virtanen",
        "dateOfBirth": "1980-01-01",
        "gender": "female",
        "address": "Hämeenkatu 5, 33100 Tampere",
        "maritalStatus": "single",
        "citizenship": ["Finland"],
    },
}

# --- CORS helpers (AÑADIDO) ---
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Requested-With,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}

def cors_response(status_code: int, payload: Any):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(payload),
    }

# --- Funciones auxiliares ---

def normalize_text(s: Optional[str]) -> str:
    """Quita tildes, espacios y pone en minúscula para comparar."""
    if not s:
        return ""
    s = ''.join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    return s.strip().lower()

def normalize_country(country: Optional[str]) -> str:
    """Acepta abreviaciones y nombres en varios idiomas."""
    if not country:
        return "DK"
    c = normalize_text(country)
    if c in ("dk", "danmark", "denmark"): return "DK"
    if c in ("se", "sweden", "sverige"):  return "SE"
    if c in ("no", "norway", "norge"):    return "NO"
    if c in ("fi", "finland", "suomi"):   return "FI"
    return "DK"

def compare_optional_fields(registry: Dict[str, Any],
                            firstName: Optional[str],
                            lastName: Optional[str],
                            dateOfBirth: Optional[str]) -> Optional[str]:
    """Verifica coherencia de campos opcionales."""
    if firstName and normalize_text(firstName) != normalize_text(registry.get("firstName")):
        return f"First name mismatch (got '{firstName}', expected '{registry.get('firstName')}')."
    if lastName and normalize_text(lastName) != normalize_text(registry.get("lastName")):
        return f"Last name mismatch (got '{lastName}', expected '{registry.get('lastName')}')."
    if dateOfBirth and dateOfBirth.strip() != registry.get("dateOfBirth"):
        return f"Date of birth mismatch (got '{dateOfBirth}', expected '{registry.get('dateOfBirth')}')."
    return None

# --- Lógica principal (sin CORS) ---

def handler(event, context):
    """
    Lambda handler. Compatible con AWS Console (string o dict).
    """
    try:
        # Si viene de API Gateway proxy
        if isinstance(event, dict) and "body" in event:
            try:
                body = event["body"]
                if isinstance(body, str) and body:
                    event = json.loads(body)
                elif isinstance(body, dict):
                    event = body
                else:
                    event = {}
            except Exception:
                event = {}

        # Si el evento viene como string JSON
        if isinstance(event, str):
            try:
                event = json.loads(event)
            except json.JSONDecodeError:
                return {"status": "ERROR", "reason": "Invalid JSON input", "registry_record": None, "source": "unknown"}

        if not isinstance(event, dict):
            return {"status": "ERROR", "reason": "Event must be a JSON object", "registry_record": None, "source": "unknown"}

        # --- Extraer campos ---
        national_id = (event.get("nationalId") or "").strip()
        country = normalize_country(event.get("country"))
        firstName = event.get("firstName")
        lastName = event.get("lastName")
        dateOfBirth = event.get("dateOfBirth")

        if not national_id:
            return {"status": "ERROR", "reason": "nationalId is required", "registry_record": None, "source": "unknown"}

        # --- Seleccionar registro por país ---
        registry_map = {
            "DK": ("denmark", DK_CPR_REGISTRY),
            "SE": ("sweden", SE_SPAR_REGISTRY),
            "NO": ("norway", NO_FOLKEREGISTER),
            "FI": ("finland", FI_POPULATION_REGISTRY),
        }

        source_name, registry = registry_map.get(country, ("denmark", DK_CPR_REGISTRY))
        person = registry.get(national_id)

        if not person:
            return {
                "status": "NOT_FOUND",
                "reason": f"ID {national_id} not found in {source_name} registry.",
                "registry_record": None,
                "source": source_name,
            }

        # --- Verificación opcional ---
        mismatch_reason = compare_optional_fields(person, firstName, lastName, dateOfBirth)
        if mismatch_reason:
            return {
                "status": "MISMATCH",
                "reason": mismatch_reason,
                "registry_record": {"national_id": national_id, **person},
                "source": source_name,
            }

        # --- OK ---
        return {
            "status": "VERIFIED",
            "reason": f"Found in {source_name} registry.",
            "registry_record": {"national_id": national_id, **person},
            "source": source_name,
        }

    except Exception as e:
        return {"status": "ERROR", "reason": str(e), "registry_record": None, "source": "unknown"}

# --- Alias compatible con AWS Lambda (con CORS y OPTIONS) ---

def lambda_handler(event, context):
    """Alias requerido por AWS Lambda"""
    if isinstance(event, dict) and event.get("httpMethod") == "OPTIONS":
        return cors_response(200, {"ok": True})

    payload = handler(event, context)
    return cors_response(200, payload)
