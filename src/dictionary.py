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

SENSITIVE_KEY_DENYLIST: frozenset[str] = frozenset(
    {
        "password",
        "secret",
        "api_key",
        "apikey",
        "token",
        "ssn",
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
