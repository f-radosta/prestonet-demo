from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from uuid import uuid4

from src.dictionary import (
    APPROVED_TERMS,
    CONFIDENCE_THRESHOLD,
    MAX_DOCUMENT_DEPTH,
    MAX_DOCUMENT_NODES,
    MAX_VARIABLE_NAME_LENGTH,
    MAX_VARIABLES,
    SENSITIVE_COMPACT,
    SENSITIVE_KEY_DENYLIST,
    compact,
)
from src.llm_client import LlmClient, LlmSuggestion, LlmUnavailableError, sanitize_llm_reason
from src.mapper import MappingHit, deterministic_map, normalize, strong_map, token_set
from src.proposals import ProposalStore
from src.schemas import ErrorDetail, MapRequest, MapResponse, MappingItem

logger = logging.getLogger(__name__)

BIRTH_NUMBER_RE = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})[\s./-]*(\d{3,4})(?!\d)")
_SEPARATORS_RE = re.compile(r"[\s./-]")


class InvalidInputError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SensitiveInputError(Exception):
    def __init__(self, message: str = "Sensitive or disallowed input blocked") -> None:
        super().__init__(message)
        self.message = message


@dataclass
class WorkerResult:
    response: MapResponse
    llm_failed: bool = False


def _unique_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def extract_variables(request: MapRequest) -> list[str]:
    if request.variables:
        return _unique_names(request.variables)
    assert request.document is not None
    return _unique_names([str(key) for key in request.document.keys()])


def _has_illegal_chars(name: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in name)


def is_sensitive_field_name(name: str) -> bool:
    normalized = normalize(name)
    if not normalized:
        return False
    compact_name = compact(normalized)
    tokens = token_set(name)
    if tokens & SENSITIVE_KEY_DENYLIST or tokens & SENSITIVE_COMPACT:
        return True
    return any(term and term in compact_name for term in SENSITIVE_COMPACT)


def _plausible_birth_date(month: str, day: str) -> bool:
    mm = int(month)
    dd = int(day)
    if not 1 <= dd <= 31:
        return False
    return 1 <= mm <= 12 or 21 <= mm <= 32 or 51 <= mm <= 62 or 71 <= mm <= 82


def _looks_like_birth_number(value: object) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int):
        text = str(abs(value))
    elif isinstance(value, float) and value.is_integer():
        text = str(abs(int(value)))
    elif isinstance(value, str):
        text = value.strip()
    else:
        return False

    digits = _SEPARATORS_RE.sub("", text)
    if digits.isdigit() and len(digits) in (9, 10):
        return _plausible_birth_date(digits[2:4], digits[4:6])
    match = BIRTH_NUMBER_RE.search(text)
    return bool(match) and _plausible_birth_date(match.group(2), match.group(3))


def _assert_safe_name(name: str) -> None:
    if len(name) > MAX_VARIABLE_NAME_LENGTH or _has_illegal_chars(name):
        raise InvalidInputError("Variable name is invalid")
    if is_sensitive_field_name(name):
        raise SensitiveInputError("Sensitive field name is not allowed")


def _scan_document(value: object, *, depth: int, remaining: list[int]) -> None:
    if remaining[0] <= 0:
        raise InvalidInputError("Document is too large")
    remaining[0] -= 1
    if depth > MAX_DOCUMENT_DEPTH:
        raise InvalidInputError("Document is nested too deeply")

    if isinstance(value, dict):
        for key, nested in value.items():
            _assert_safe_name(str(key))
            if _looks_like_birth_number(nested):
                raise SensitiveInputError("Document value looks like personal identification data")
            if isinstance(nested, (dict, list)):
                _scan_document(nested, depth=depth + 1, remaining=remaining)
        return

    if isinstance(value, list):
        for item in value:
            if _looks_like_birth_number(item):
                raise SensitiveInputError("Document value looks like personal identification data")
            if isinstance(item, (dict, list)):
                _scan_document(item, depth=depth + 1, remaining=remaining)


def reject_if_sensitive(request: MapRequest, variables: list[str]) -> None:
    for name in variables:
        _assert_safe_name(name)
    if request.document is not None:
        _scan_document(request.document, depth=0, remaining=[MAX_DOCUMENT_NODES])


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, value))


def validate_hit(source: str, hit: MappingHit) -> MappingItem:
    suggested = hit.suggested_variable
    if suggested is not None and suggested not in APPROVED_TERMS:
        return MappingItem(
            source_variable=source,
            suggested_variable=None,
            confidence=0.0,
            reason="suggestion outside approved dictionary discarded",
            needs_review=True,
        )

    confidence = _clamp_confidence(hit.confidence)
    needs_review = hit.needs_review or suggested is None or confidence < CONFIDENCE_THRESHOLD
    return MappingItem(
        source_variable=source,
        suggested_variable=suggested,
        confidence=confidence,
        reason=hit.reason,
        needs_review=needs_review,
    )


def _from_llm(source: str, suggestion: LlmSuggestion) -> MappingItem:
    suggested = suggestion.suggested_variable
    if suggested is not None and suggested not in APPROVED_TERMS:
        suggested = None
        reason = "llm suggestion outside approved dictionary discarded"
        confidence = 0.0
    else:
        reason = sanitize_llm_reason(suggestion.reason or "llm suggestion")
        confidence = _clamp_confidence(suggestion.confidence)
        if suggested is None:
            reason = reason or "not in target dictionary"
    # LLM output is untrusted: keep the suggestion if it is in the dictionary,
    # but never auto-clear needs_review.
    needs_review = True
    return MappingItem(
        source_variable=source,
        suggested_variable=suggested,
        confidence=confidence,
        reason=reason,
        needs_review=needs_review,
    )


def _unmapped(source: str, reason: str) -> MappingItem:
    return MappingItem(
        source_variable=source,
        suggested_variable=None,
        confidence=0.0,
        reason=reason,
        needs_review=True,
    )


def run_mapping(
    request: MapRequest,
    store: ProposalStore,
    llm: LlmClient,
) -> WorkerResult:
    variables = extract_variables(request)
    if not variables:
        raise InvalidInputError("No variable names to map")
    if len(variables) > MAX_VARIABLES:
        raise InvalidInputError(f"Too many variables (max {MAX_VARIABLES})")

    reject_if_sensitive(request, variables)

    request_id = request.request_id or str(uuid4())
    document_id = request.document_id or ("inline-document" if request.document else "variable-list")

    mappings: list[MappingItem] = []
    pending: list[str] = []
    pending_fallback: dict[str, MappingItem] = {}

    for source in variables:
        strong = strong_map(source)
        if strong and strong.confidence >= CONFIDENCE_THRESHOLD and not strong.needs_review:
            mappings.append(validate_hit(source, strong))
            continue
        weak = deterministic_map(source)
        if weak:
            pending_fallback[source] = validate_hit(source, weak)
        pending.append(source)

    llm_failed = False
    if pending:
        try:
            suggestions = {
                item.source_variable: item
                for item in llm.suggest(pending, sorted(APPROVED_TERMS))
            }
            for source in pending:
                if source in suggestions:
                    mappings.append(_from_llm(source, suggestions[source]))
                elif source in pending_fallback:
                    mappings.append(pending_fallback[source])
                else:
                    mappings.append(
                        _unmapped(source, "not in target dictionary; no safe candidate")
                    )
        except LlmUnavailableError:
            llm_failed = True
            for source in pending:
                if source in pending_fallback:
                    item = pending_fallback[source]
                    mappings.append(
                        item.model_copy(
                            update={
                                "reason": f"{item.reason}; LLM unavailable",
                                "needs_review": True,
                            }
                        )
                    )
                else:
                    mappings.append(_unmapped(source, "LLM unavailable"))

    proposal = store.create(
        actor_id=request.actor_id,
        mappings=mappings,
        document_id=document_id,
        request_id=request_id,
    )

    logger.info(
        "mapped actor=%s document_id=%s proposal_id=%s variables=%s needs_review=%s llm_failed=%s",
        request.actor_id,
        document_id,
        proposal.id,
        [item.source_variable for item in mappings],
        [item.source_variable for item in mappings if item.needs_review],
        llm_failed,
    )

    status = "error" if llm_failed else "proposal_ready"
    error = (
        ErrorDetail(
            code="llm_unavailable",
            message="External model timeout. Deterministic mappings returned; remaining items marked needs_review.",
        )
        if llm_failed
        else None
    )
    response = MapResponse(
        request_id=request_id,
        status=status,
        write_performed=False,
        proposal_id=proposal.id,
        requires_approval=True,
        mappings=mappings,
        error=error,
    )
    return WorkerResult(response=response, llm_failed=llm_failed)
