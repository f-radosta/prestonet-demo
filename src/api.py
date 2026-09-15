from __future__ import annotations

import hmac
import logging
import os
import time
from pathlib import Path
from threading import Lock
from typing import Annotated

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from src.dictionary import RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_S
from src.llm_client import LlmClient, build_llm_client
from src.proposals import (
    ProposalConflictError,
    ProposalNotFoundError,
    ProposalStore,
    SelfDecisionError,
    StoreFullError,
)
from src.schemas import MapRequest, MapResponse, ProposalResponse, ProposalStatus, clean_actor_id
from src.worker import InvalidInputError, SensitiveInputError, run_mapping

logger = logging.getLogger(__name__)

ActorHeader = Annotated[str | None, Header(alias="X-Actor-Id")]
ApiKeyHeader = Annotated[str | None, Header(alias="X-Api-Key")]
DEMO_HTML = Path(__file__).parent / "static" / "demo.html"


class RateLimiter:
    def __init__(
        self,
        max_requests: int = RATE_LIMIT_MAX_REQUESTS,
        window_s: float = RATE_LIMIT_WINDOW_S,
    ) -> None:
        self.max_requests = max_requests
        self.window_s = window_s
        self._hits: dict[str, list[float]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_s
        with self._lock:
            hits = [ts for ts in self._hits.get(key, []) if ts > cutoff]
            if len(hits) >= self.max_requests:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


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
    try:
        return clean_actor_id(actor_id)
    except ValueError:
        return _error_body(
            code="invalid_input",
            message="X-Actor-Id header is invalid",
            status_code=400,
        )


def _check_api_key(expected: str, provided: str | None) -> JSONResponse | None:
    if not expected:
        return None
    given = provided or ""
    if not hmac.compare_digest(given, expected):
        return _error_body(
            code="unauthorized",
            message="Invalid or missing API key",
            status_code=401,
        )
    return None


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
    *,
    api_key: str | None = None,
    limiter: RateLimiter | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Prestonet mapping worker PoC",
        description="Proposes field-name mappings. Never writes source documents.",
    )
    app.state.llm = llm or build_llm_client()
    app.state.store = store or ProposalStore()
    app.state.limiter = limiter or RateLimiter()
    if api_key is None:
        app.state.api_key = os.getenv("MAPPING_API_KEY", "").strip()
    else:
        app.state.api_key = api_key

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

    @app.get("/")
    def demo_page() -> FileResponse:
        return FileResponse(DEMO_HTML, media_type="text/html")

    @app.post("/map", response_model=MapResponse)
    def map_variables(
        body: MapRequest,
        x_api_key: ApiKeyHeader = None,
    ) -> MapResponse | JSONResponse:
        denied = _check_api_key(app.state.api_key, x_api_key)
        if denied:
            return denied
        if not app.state.limiter.allow(f"map:{body.actor_id}"):
            return _error_body(code="rate_limited", message="Too many requests", status_code=429)
        try:
            result = run_mapping(body, app.state.store, app.state.llm)
        except SensitiveInputError as exc:
            return _error_body(code="sensitive_input_blocked", message=exc.message, status_code=422)
        except InvalidInputError as exc:
            return _error_body(code="invalid_input", message=exc.message, status_code=400)
        except StoreFullError:
            return _error_body(
                code="store_full",
                message="Proposal store is full",
                status_code=503,
            )

        payload = result.response.model_dump()
        if result.llm_failed:
            return JSONResponse(status_code=502, content=payload)
        return result.response

    @app.get("/proposals/{proposal_id}", response_model=ProposalResponse)
    def get_proposal(
        proposal_id: str,
        x_actor_id: ActorHeader = None,
        x_api_key: ApiKeyHeader = None,
    ) -> ProposalResponse | JSONResponse:
        denied = _check_api_key(app.state.api_key, x_api_key)
        if denied:
            return denied
        actor = _require_actor(x_actor_id)
        if isinstance(actor, JSONResponse):
            return actor
        try:
            proposal = app.state.store.get(proposal_id)
        except ProposalNotFoundError:
            return _error_body(code="not_found", message="Proposal not found", status_code=404)
        return _proposal_response(proposal)

    @app.post("/proposals/{proposal_id}/approve", response_model=ProposalResponse)
    def approve_proposal(
        proposal_id: str,
        x_actor_id: ActorHeader = None,
        x_api_key: ApiKeyHeader = None,
    ) -> ProposalResponse | JSONResponse:
        return _decide(app, proposal_id, x_actor_id, x_api_key, "approved")

    @app.post("/proposals/{proposal_id}/reject", response_model=ProposalResponse)
    def reject_proposal(
        proposal_id: str,
        x_actor_id: ActorHeader = None,
        x_api_key: ApiKeyHeader = None,
    ) -> ProposalResponse | JSONResponse:
        return _decide(app, proposal_id, x_actor_id, x_api_key, "rejected")

    return app


def _decide(
    app: FastAPI,
    proposal_id: str,
    x_actor_id: str | None,
    x_api_key: str | None,
    status: ProposalStatus,
):
    denied = _check_api_key(app.state.api_key, x_api_key)
    if denied:
        return denied
    actor = _require_actor(x_actor_id)
    if isinstance(actor, JSONResponse):
        return actor
    if not app.state.limiter.allow(f"decide:{actor}"):
        return _error_body(code="rate_limited", message="Too many requests", status_code=429)
    try:
        proposal = app.state.store.decide(proposal_id, actor_id=actor, status=status)
    except ProposalNotFoundError:
        return _error_body(code="not_found", message="Proposal not found", status_code=404)
    except SelfDecisionError:
        return _error_body(
            code="forbidden",
            message="Author cannot approve or reject their own proposal",
            status_code=403,
        )
    except ProposalConflictError:
        return _error_body(
            code="conflict",
            message="Proposal is not pending",
            status_code=409,
        )
    logger.info(
        "proposal %s proposal_id=%s decided_by=%s write_performed=%s",
        status,
        proposal.id,
        actor,
        False,
    )
    return _proposal_response(proposal)


app = create_app()
