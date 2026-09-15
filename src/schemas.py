from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ProposalStatus = Literal["pending", "approved", "rejected"]


class MapRequest(BaseModel):
    request_id: str | None = None
    actor_id: str = Field(min_length=1)
    document_id: str | None = None
    variables: list[str] | None = None
    document: dict[str, Any] | None = None

    @field_validator("variables")
    @classmethod
    def variables_must_be_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        cleaned = [item.strip() for item in value if item and str(item).strip()]
        if value and not cleaned:
            raise ValueError("variables must contain at least one non-empty name")
        return cleaned or None

    @model_validator(mode="after")
    def require_source(self) -> MapRequest:
        if not self.variables and not self.document:
            raise ValueError("Provide variables or document")
        return self


class MappingItem(BaseModel):
    source_variable: str
    suggested_variable: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    needs_review: bool


class ErrorDetail(BaseModel):
    code: str
    message: str


class MapResponse(BaseModel):
    request_id: str
    status: str
    write_performed: bool = False
    proposal_id: str
    requires_approval: bool = True
    mappings: list[MappingItem]
    error: ErrorDetail | None = None


class ProposalResponse(BaseModel):
    proposal_id: str
    status: ProposalStatus
    write_performed: bool = False
    requires_approval: bool = True
    actor_id: str
    decided_by: str | None = None
    mappings: list[MappingItem]
    document_id: str | None = None
    request_id: str | None = None
