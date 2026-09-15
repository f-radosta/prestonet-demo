from __future__ import annotations

import re
from dataclasses import dataclass

from src.dictionary import (
    ALIASES,
    APPROVED_TERMS,
    COMPACT_ALIASES,
    CONFIDENCE_THRESHOLD,
    compact,
)


_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
_NON_ALNUM_RE = re.compile(r"[^a-zA-Z0-9]+")


@dataclass(frozen=True)
class MappingHit:
    suggested_variable: str | None
    confidence: float
    reason: str
    needs_review: bool


def to_snake(name: str) -> str:
    stepped = _CAMEL_RE.sub(r"\1_\2", name)
    return _NON_ALNUM_RE.sub("_", stepped).strip("_").lower()


def normalize(name: str) -> str:
    return to_snake(name)


def token_set(name: str) -> frozenset[str]:
    return frozenset(part for part in normalize(name).split("_") if part)


def _hit(
    term: str,
    confidence: float,
    reason: str,
    *,
    needs_review: bool | None = None,
) -> MappingHit:
    review = needs_review if needs_review is not None else confidence < CONFIDENCE_THRESHOLD
    return MappingHit(
        suggested_variable=term,
        confidence=confidence,
        reason=reason,
        needs_review=review,
    )


def strong_map(source: str) -> MappingHit | None:
    """High-confidence deterministic mapping, or None if LLM/review is needed."""
    normalized = normalize(source)
    if not normalized:
        return None

    if normalized in APPROVED_TERMS:
        return _hit(normalized, 1.0, "exact match to approved term")

    if normalized in ALIASES:
        term = ALIASES[normalized]
        return _hit(term, 0.98, f"known alias of {term}")

    compacted = compact(normalized)
    if compacted in COMPACT_ALIASES:
        term = COMPACT_ALIASES[compacted]
        return _hit(term, 0.95, f"normalized alias of {term}")

    src_tokens = token_set(source)
    token_matches = [
        term for term in sorted(APPROVED_TERMS) if src_tokens and src_tokens == token_set(term)
    ]
    if len(token_matches) == 1:
        term = token_matches[0]
        return _hit(term, 0.88, f"same tokens in different order as {term}")
    if len(token_matches) > 1:
        return MappingHit(
            suggested_variable=None,
            confidence=0.2,
            reason=f"multiple token matches: {', '.join(token_matches)}",
            needs_review=True,
        )
    return None


def weak_map(source: str) -> MappingHit | None:
    """Ambiguous prefix/partial hint. Always needs review and stays below threshold."""
    tokens = token_set(source)
    if not tokens:
        return None

    candidates: set[str] = set()
    for term in APPROVED_TERMS:
        for approved_token in token_set(term):
            for src in tokens:
                if len(src) >= 3 and (
                    approved_token.startswith(src) or src.startswith(approved_token)
                ):
                    candidates.add(term)

    for alias, term in ALIASES.items():
        for src in tokens:
            if len(src) >= 3 and (alias.startswith(src) or compact(alias).startswith(src)):
                candidates.add(term)

    if len(candidates) == 1:
        term = next(iter(candidates))
        return _hit(
            term,
            0.4,
            f"ambiguous partial match to {term}",
            needs_review=True,
        )
    return None


def deterministic_map(source: str) -> MappingHit | None:
    return strong_map(source) or weak_map(source)
