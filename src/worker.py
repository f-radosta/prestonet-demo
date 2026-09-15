from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from uuid import uuid4

from src.dictionary import (
    APPROVED_TERMS,
    CONFIDENCE_THRESHOLD,
    MAX_VARIABLES,
    SENSITIVE_KEY_DENYLIST,
)
from src.llm_client import LlmClient, LlmSuggestion, LlmUnavailableError
from src.mapper import MappingHit, deterministic_map, normalize, strong_map
from src.proposals import ProposalStore
from src.schemas import ErrorDetail, MapRequest, MapResponse, MappingItem

logger = logging.getLogger(__name__)

BIRTH_NUMBER_RE = re.compile(r"\b\d{6}/?\d{3,4}\b")


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


def _looks_like_birth_number(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(BIRTH_NUMBER_RE.search(value.strip()))


def reject_if_sensitive(request: MapRequest, variables: list[str]) -> None:
    for name in variables:
        normalized = normalize(name)
        compact_name = normalized.replace("_", "")
        if normalized in SENSITIVE_KEY_DENYLIST or compact_name in SENSITIVE_KEY_DENYLIST:
            raise SensitiveInputError("Sensitive field name is not allowed")

    if request.document:
        for key, value in request.document.items():
            normalized = normalize(str(key))
            if normalized in SENSITIVE_KEY_DENYLIST or normalized.replace("_", "") in SENSITIVE_KEY_DENYLIST:
                raise SensitiveInputError("Sensitive field name is not allowed")
            if _looks_like_birth_number(value):
                raise SensitiveInputError("Document value looks like personal identification data")


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
        reason = suggestion.reason or "llm suggestion"
        confidence = _clamp_confidence(suggestion.confidence)
        if suggested is None:
            reason = reason or "not in target dictionary"
    needs_review = suggested is None or confidence < CONFIDENCE_THRESHOLD
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
