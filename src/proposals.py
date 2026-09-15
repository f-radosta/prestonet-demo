from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4

from src.dictionary import MAX_PROPOSALS
from src.schemas import MappingItem, ProposalStatus


class ProposalNotFoundError(Exception):
    pass


class ProposalConflictError(Exception):
    pass


class SelfDecisionError(Exception):
    pass


class StoreFullError(Exception):
    pass


@dataclass
class Proposal:
    id: str
    actor_id: str
    status: ProposalStatus
    mappings: list[MappingItem]
    write_performed: bool = False
    document_id: str | None = None
    request_id: str | None = None
    decided_by: str | None = None

    def __post_init__(self) -> None:
        # The worker never writes source documents, including after approval.
        self.write_performed = False


@dataclass
class ProposalStore:
    _items: dict[str, Proposal] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)
    max_items: int = MAX_PROPOSALS

    def create(
        self,
        *,
        actor_id: str,
        mappings: list[MappingItem],
        document_id: str | None,
        request_id: str,
    ) -> Proposal:
        proposal = Proposal(
            id=str(uuid4()),
            actor_id=actor_id,
            status="pending",
            mappings=mappings,
            write_performed=False,
            document_id=document_id,
            request_id=request_id,
        )
        with self._lock:
            if len(self._items) >= self.max_items:
                raise StoreFullError("Proposal store is full")
            self._items[proposal.id] = proposal
        return proposal

    def _get_unlocked(self, proposal_id: str) -> Proposal:
        proposal = self._items.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        return proposal

    def get(self, proposal_id: str) -> Proposal:
        with self._lock:
            return self._get_unlocked(proposal_id)

    def decide(self, proposal_id: str, *, actor_id: str, status: ProposalStatus) -> Proposal:
        with self._lock:
            proposal = self._get_unlocked(proposal_id)
            if proposal.status != "pending":
                raise ProposalConflictError(proposal.status)
            if proposal.actor_id == actor_id:
                raise SelfDecisionError(actor_id)
            proposal.status = status
            proposal.decided_by = actor_id
            proposal.write_performed = False
            return proposal
