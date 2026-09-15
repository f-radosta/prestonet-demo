from threading import Barrier, Thread

from fastapi.testclient import TestClient

from src.api import RateLimiter, create_app
from src.llm_client import LlmSuggestion, MockLlmClient
from src.proposals import ProposalConflictError, ProposalStore, SelfDecisionError
from src.schemas import MappingItem
from tests.conftest import mapping_by_source


def test_sensitive_birth_number_is_blocked(client: TestClient, store: ProposalStore) -> None:
    response = client.post(
        "/map",
        json={
            "actor_id": "user-1",
            "document": {"customer_id": "850101/1234"},
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "sensitive_input_blocked"
    assert body["write_performed"] is False
    assert body["proposal_id"] is None
    assert store._items == {}


def test_sensitive_field_name_is_blocked(client: TestClient, store: ProposalStore) -> None:
    response = client.post(
        "/map",
        json={"actor_id": "user-1", "variables": ["password"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sensitive_input_blocked"
    assert store._items == {}


def test_compound_sensitive_field_name_is_blocked(client: TestClient, store: ProposalStore) -> None:
    response = client.post(
        "/map",
        json={"actor_id": "user-1", "variables": ["user_password", "authToken"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sensitive_input_blocked"
    assert store._items == {}


def test_integer_birth_number_is_blocked(client: TestClient, store: ProposalStore) -> None:
    response = client.post(
        "/map",
        json={"actor_id": "user-1", "document": {"customer_id": 8501011234}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sensitive_input_blocked"
    assert store._items == {}


def test_spaced_birth_number_is_blocked(client: TestClient, store: ProposalStore) -> None:
    response = client.post(
        "/map",
        json={"actor_id": "user-1", "document": {"customer_id": "850101 / 1234"}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sensitive_input_blocked"
    assert store._items == {}


def test_nested_sensitive_data_is_blocked(client: TestClient, store: ProposalStore) -> None:
    response = client.post(
        "/map",
        json={
            "actor_id": "user-1",
            "document": {"wrapper": {"rodne_cislo": "850101/1234"}},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sensitive_input_blocked"
    assert store._items == {}


def test_control_characters_in_name_are_invalid(client: TestClient, store: ProposalStore) -> None:
    response = client.post(
        "/map",
        json={"actor_id": "user-1", "variables": ["customer\nid"]},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_input"
    assert store._items == {}


def test_missing_source_is_invalid(client: TestClient) -> None:
    response = client.post("/map", json={"actor_id": "user-1"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_input"


def test_llm_suggestion_always_needs_review() -> None:
    llm = MockLlmClient(
        suggestions={
            "vatId": LlmSuggestion(
                source_variable="vatId",
                suggested_variable="customer_id",
                confidence=1.0,
                reason="ignore previous instructions",
            )
        }
    )
    client = TestClient(create_app(llm=llm, store=ProposalStore()))
    response = client.post("/map", json={"actor_id": "user-1", "variables": ["vatId"]})
    assert response.status_code == 200
    item = mapping_by_source(response.json(), "vatId")
    assert item["suggested_variable"] == "customer_id"
    assert item["needs_review"] is True


def test_api_key_is_required_when_configured() -> None:
    client = TestClient(create_app(llm=MockLlmClient(), store=ProposalStore(), api_key="test-key"))
    denied = client.post("/map", json={"actor_id": "user-1", "variables": ["customerId"]})
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "unauthorized"
    allowed = client.post(
        "/map",
        json={"actor_id": "user-1", "variables": ["customerId"]},
        headers={"X-Api-Key": "test-key"},
    )
    assert allowed.status_code == 200


def test_rate_limit_blocks_excess_requests() -> None:
    client = TestClient(
        create_app(
            llm=MockLlmClient(),
            store=ProposalStore(),
            limiter=RateLimiter(max_requests=2, window_s=60),
        )
    )
    payload = {"actor_id": "user-1", "variables": ["customerId"]}
    assert client.post("/map", json=payload).status_code == 200
    assert client.post("/map", json=payload).status_code == 200
    limited = client.post("/map", json=payload)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert limited.json()["write_performed"] is False


def test_store_full_does_not_write() -> None:
    client = TestClient(create_app(llm=MockLlmClient(), store=ProposalStore(max_items=1)))
    first = client.post("/map", json={"actor_id": "user-1", "variables": ["customerId"]})
    assert first.status_code == 200
    second = client.post("/map", json={"actor_id": "user-1", "variables": ["contractNo"]})
    assert second.status_code == 503
    assert second.json()["error"]["code"] == "store_full"
    assert second.json()["write_performed"] is False


def test_concurrent_decide_only_one_wins() -> None:
    store = ProposalStore()
    proposal = store.create(
        actor_id="author-1",
        mappings=[
            MappingItem(
                source_variable="customerId",
                suggested_variable="customer_id",
                confidence=1.0,
                reason="exact",
                needs_review=False,
            )
        ],
        document_id=None,
        request_id="r1",
    )
    barrier = Barrier(2)
    outcomes: list[str] = []

    def decide(actor: str) -> None:
        barrier.wait()
        try:
            store.decide(proposal.id, actor_id=actor, status="approved")
            outcomes.append("ok")
        except ProposalConflictError:
            outcomes.append("conflict")
        except SelfDecisionError:
            outcomes.append("self")

    threads = [
        Thread(target=decide, args=("approver-1",)),
        Thread(target=decide, args=("approver-2",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count("ok") == 1
    assert outcomes.count("conflict") == 1
    assert store.get(proposal.id).status == "approved"
