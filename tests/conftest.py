import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.llm_client import MockLlmClient
from src.proposals import ProposalStore

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def llm() -> MockLlmClient:
    return MockLlmClient()


@pytest.fixture
def store() -> ProposalStore:
    return ProposalStore()


@pytest.fixture
def client(llm: MockLlmClient, store: ProposalStore) -> TestClient:
    return TestClient(create_app(llm=llm, store=store))


@pytest.fixture
def fixtures() -> dict[str, dict]:
    loaded = {}
    for name in ("doc_a", "doc_b", "doc_c"):
        loaded[name] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return loaded


def mapping_by_source(body: dict, source: str) -> dict:
    return next(item for item in body["mappings"] if item["source_variable"] == source)
