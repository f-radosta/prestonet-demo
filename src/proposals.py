from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from src.schemas import MappingItem, ProposalStatus


class ProposalNotFoundError(Exception):
    pass


class ProposalConflictError(Exception):
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
        self._items[proposal.id] = proposal
        return proposal

    def get(self, proposal_id: str) -> Proposal:
        proposal = self._items.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        return proposal

    def decide(self, proposal_id: str, *, actor_id: str, status: ProposalStatus) -> Proposal:
        proposal = self.get(proposal_id)
        if proposal.status != "pending":
            raise ProposalConflictError(proposal.status)
        proposal.status = status
        proposal.decided_by = actor_id
        proposal.write_performed = False
        return proposal
