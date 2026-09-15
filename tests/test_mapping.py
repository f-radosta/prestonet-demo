import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.dictionary import APPROVED_TERMS
from src.llm_client import MockLlmClient
from src.proposals import ProposalStore
from tests.conftest import mapping_by_source


def test_clear_mapping_does_not_call_llm(client: TestClient, llm: MockLlmClient) -> None:
    response = client.post(
        "/map",
        json={"actor_id": "user-1", "variables": ["customerId"]},
    )
    assert response.status_code == 200
    body = response.json()
    item = mapping_by_source(body, "customerId")
    assert item["suggested_variable"] == "customer_id"
    assert item["confidence"] >= 0.8
    assert item["needs_review"] is False
    assert body["write_performed"] is False
    assert body["requires_approval"] is True
    assert llm.call_count == 0


@pytest.mark.parametrize("source", ["addr", "cislo"])
def test_ambiguous_mapping_needs_review(client: TestClient, source: str) -> None:
    response = client.post(
        "/map",
        json={"actor_id": "user-1", "variables": [source]},
    )
    assert response.status_code == 200
    body = response.json()
    item = mapping_by_source(body, source)
    assert item["needs_review"] is True
    assert item["confidence"] < 0.8
    assert body["write_performed"] is False


def test_unknown_variable(client: TestClient) -> None:
    response = client.post(
        "/map",
        json={"actor_id": "user-1", "variables": ["vatId"]},
    )
    assert response.status_code == 200
    body = response.json()
    item = mapping_by_source(body, "vatId")
    assert item["suggested_variable"] is None
    assert item["needs_review"] is True
    assert body["write_performed"] is False


def test_llm_timeout_returns_partial_without_write() -> None:
    llm = MockLlmClient(fail=True)
    client = TestClient(create_app(llm=llm, store=ProposalStore()))
    response = client.post(
        "/map",
        json={"actor_id": "user-1", "variables": ["customerId", "vatId"]},
    )
    assert response.status_code == 502
    body = response.json()
    assert body["write_performed"] is False
    assert body["error"]["code"] == "llm_unavailable"
    assert mapping_by_source(body, "customerId")["suggested_variable"] == "customer_id"
    vat = mapping_by_source(body, "vatId")
    assert vat["needs_review"] is True
    assert vat["suggested_variable"] is None
    assert body["proposal_id"]


@pytest.mark.parametrize("doc_name", ["doc_a", "doc_b", "doc_c"])
def test_fixture_documents_map_approved_terms(
    client: TestClient, fixtures: dict, doc_name: str
) -> None:
    response = client.post(
        "/map",
        json={
            "actor_id": "user-1",
            "document_id": doc_name,
            "document": fixtures[doc_name],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    suggested = {item["suggested_variable"] for item in body["mappings"]}
    assert suggested == set(APPROVED_TERMS)
    assert all(item["needs_review"] is False for item in body["mappings"])
    assert body["write_performed"] is False
