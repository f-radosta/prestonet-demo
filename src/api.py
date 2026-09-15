from __future__ import annotations

import logging
from typing import Annotated

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.llm_client import LlmClient, build_llm_client
from src.proposals import ProposalConflictError, ProposalNotFoundError, ProposalStore
from src.schemas import MapRequest, MapResponse, ProposalResponse
from src.worker import InvalidInputError, SensitiveInputError, run_mapping

logger = logging.getLogger(__name__)

ActorHeader = Annotated[str | None, Header(alias="X-Actor-Id")]


def _error_body(
    *,
    code: str,
    message: str,
    status_code: int,
    request_id: str | None = None,
    mappings: list | None = None,
    proposal_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "request_id": request_id,
            "status": "error",
            "write_performed": False,
            "proposal_id": proposal_id,
            "error": {"code": code, "message": message},
            "mappings": mappings or [],
        },
    )


def _require_actor(actor_id: str | None) -> str | JSONResponse:
    if not actor_id or not actor_id.strip():
        return _error_body(
            code="invalid_input",
            message="X-Actor-Id header is required",
            status_code=400,
        )
    return actor_id.strip()


def _proposal_response(proposal) -> ProposalResponse:
    return ProposalResponse(
        proposal_id=proposal.id,
        status=proposal.status,
        write_performed=False,
        requires_approval=True,
        actor_id=proposal.actor_id,
        decided_by=proposal.decided_by,
        mappings=proposal.mappings,
        document_id=proposal.document_id,
        request_id=proposal.request_id,
    )


def create_app(
    llm: LlmClient | None = None,
    store: ProposalStore | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Prestonet mapping worker PoC",
        description="Proposes field-name mappings. Never writes source documents.",
    )
    app.state.llm = llm or build_llm_client()
    app.state.store = store or ProposalStore()

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_body(
            code="invalid_input",
            message="; ".join(
                f"{'.'.join(str(part) for part in err.get('loc', ()))}: {err.get('msg')}"
                for err in exc.errors()
            )
            or "Invalid input",
            status_code=400,
        )

    @app.post("/map", response_model=MapResponse)
    def map_variables(body: MapRequest) -> MapResponse | JSONResponse:
        try:
            result = run_mapping(body, app.state.store, app.state.llm)
        except SensitiveInputError as exc:
            return _error_body(code="sensitive_input_blocked", message=exc.message, status_code=422)
        except InvalidInputError as exc:
            return _error_body(code="invalid_input", message=exc.message, status_code=400)

        payload = result.response.model_dump()
        if result.llm_failed:
            return JSONResponse(status_code=502, content=payload)
        return result.response

    @app.get("/proposals/{proposal_id}", response_model=ProposalResponse)
    def get_proposal(proposal_id: str) -> ProposalResponse | JSONResponse:
        try:
            proposal = app.state.store.get(proposal_id)
        except ProposalNotFoundError:
            return _error_body(code="not_found", message="Proposal not found", status_code=404)
        return _proposal_response(proposal)

    @app.post("/proposals/{proposal_id}/approve", response_model=ProposalResponse)
    def approve_proposal(proposal_id: str, x_actor_id: ActorHeader = None) -> ProposalResponse | JSONResponse:
        actor = _require_actor(x_actor_id)
        if isinstance(actor, JSONResponse):
            return actor
        try:
            proposal = app.state.store.decide(proposal_id, actor_id=actor, status="approved")
        except ProposalNotFoundError:
            return _error_body(code="not_found", message="Proposal not found", status_code=404)
        except ProposalConflictError:
            return _error_body(
                code="conflict",
                message="Proposal is not pending",
                status_code=409,
            )
        logger.info(
            "proposal approved proposal_id=%s decided_by=%s write_performed=%s",
            proposal.id,
            actor,
            False,
        )
        return _proposal_response(proposal)

    @app.post("/proposals/{proposal_id}/reject", response_model=ProposalResponse)
    def reject_proposal(proposal_id: str, x_actor_id: ActorHeader = None) -> ProposalResponse | JSONResponse:
        actor = _require_actor(x_actor_id)
        if isinstance(actor, JSONResponse):
            return actor
        try:
            proposal = app.state.store.decide(proposal_id, actor_id=actor, status="rejected")
        except ProposalNotFoundError:
            return _error_body(code="not_found", message="Proposal not found", status_code=404)
        except ProposalConflictError:
            return _error_body(
                code="conflict",
                message="Proposal is not pending",
                status_code=409,
            )
        logger.info("proposal rejected proposal_id=%s decided_by=%s write_performed=%s", proposal.id, actor, False)
        return _proposal_response(proposal)

    return app


app = create_app()
