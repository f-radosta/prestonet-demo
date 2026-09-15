from fastapi.testclient import TestClient

from src.proposals import ProposalStore


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


def test_missing_source_is_invalid(client: TestClient) -> None:
    response = client.post("/map", json={"actor_id": "user-1"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_input"
