"""Approved target dictionary and known aliases for the PoC."""

APPROVED_TERMS: frozenset[str] = frozenset(
    {
        "customer_id",
        "contract_number",
        "service_address",
    }
)

# Keys must already be snake_case / lowercase (see mapper.normalize).
ALIASES: dict[str, str] = {
    "contract_no": "contract_number",
    "id_zakaznika": "customer_id",
    "cislo_smlouvy": "contract_number",
    "adresa_sluzby": "service_address",
}

CONFIDENCE_THRESHOLD = 0.8
MAX_VARIABLES = 50
MAX_VARIABLE_NAME_LENGTH = 128
MAX_ACTOR_ID_LENGTH = 64
MAX_DOCUMENT_DEPTH = 8
MAX_DOCUMENT_NODES = 200
MAX_PROPOSALS = 500
MAX_LLM_REASON_LENGTH = 300
RATE_LIMIT_MAX_REQUESTS = 60
RATE_LIMIT_WINDOW_S = 60.0

SENSITIVE_KEY_DENYLIST: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "api_key",
        "apikey",
        "private_key",
        "token",
        "ssn",
        "credential",
        "rodne_cislo",
        "birth_number",
        "birthnumber",
    }
)


def compact(name: str) -> str:
    return name.replace("_", "")


def compact_alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {compact(term): term for term in APPROVED_TERMS}
    for alias, term in ALIASES.items():
        mapping[compact(alias)] = term
    return mapping


COMPACT_ALIASES = compact_alias_map()
SENSITIVE_COMPACT = frozenset(compact(item) for item in SENSITIVE_KEY_DENYLIST)
