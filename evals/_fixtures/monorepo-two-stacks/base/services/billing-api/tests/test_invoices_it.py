import pytest
from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="module")
def client():
    with PostgresContainer("postgres:16-alpine") as db:
        import os

        os.environ["DATABASE_URL"] = db.get_connection_url()
        from app.main import app

        yield TestClient(app)


def test_unknown_invoice_returns_null(client):
    assert client.get("/invoices/999").json() is None
