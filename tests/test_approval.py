from fastapi.testclient import TestClient


def test_map_creates_pending_proposal_without_write(client: TestClient) -> None:
    created = client.post(
        "/map",
        json={"actor_id": "author-1", "variables": ["customerId"]},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["write_performed"] is False
    proposal_id = body["proposal_id"]

    fetched = client.get(f"/proposals/{proposal_id}", headers={"X-Actor-Id": "author-1"})
    assert fetched.status_code == 200
    proposal = fetched.json()
    assert proposal["status"] == "pending"
    assert proposal["write_performed"] is False
    assert proposal["actor_id"] == "author-1"


def test_approve_does_not_write_and_second_approve_conflicts(client: TestClient) -> None:
    created = client.post(
        "/map",
        json={"actor_id": "author-1", "variables": ["customerId"]},
    )
    proposal_id = created.json()["proposal_id"]
    headers = {"X-Actor-Id": "approver-1"}

    approved = client.post(f"/proposals/{proposal_id}/approve", headers=headers)
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "approved"
    assert body["write_performed"] is False
    assert body["decided_by"] == "approver-1"

    again = client.post(f"/proposals/{proposal_id}/approve", headers=headers)
    assert again.status_code == 409
    assert again.json()["write_performed"] is False


def test_reject_then_approve_conflicts(client: TestClient) -> None:
    created = client.post(
        "/map",
        json={"actor_id": "author-1", "variables": ["customerId"]},
    )
    proposal_id = created.json()["proposal_id"]
    headers = {"X-Actor-Id": "approver-1"}

    rejected = client.post(f"/proposals/{proposal_id}/reject", headers=headers)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["write_performed"] is False

    approved = client.post(f"/proposals/{proposal_id}/approve", headers=headers)
    assert approved.status_code == 409


def test_approve_missing_proposal(client: TestClient) -> None:
    response = client.post(
        "/proposals/does-not-exist/approve",
        headers={"X-Actor-Id": "approver-1"},
    )
    assert response.status_code == 404


def test_author_cannot_approve_own_proposal(client: TestClient) -> None:
    created = client.post(
        "/map",
        json={"actor_id": "author-1", "variables": ["customerId"]},
    )
    proposal_id = created.json()["proposal_id"]
    response = client.post(
        f"/proposals/{proposal_id}/approve",
        headers={"X-Actor-Id": "author-1"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert response.json()["write_performed"] is False


def test_get_proposal_requires_actor(client: TestClient) -> None:
    created = client.post(
        "/map",
        json={"actor_id": "author-1", "variables": ["customerId"]},
    )
    proposal_id = created.json()["proposal_id"]
    response = client.get(f"/proposals/{proposal_id}")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_input"
