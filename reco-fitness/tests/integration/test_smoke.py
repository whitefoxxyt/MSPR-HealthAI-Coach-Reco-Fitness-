"""Smoke test d'integration -- verifie que les containers demarrent et repondent."""
import pytest
from sqlalchemy import text


@pytest.mark.integration
def test_postgres_container_is_reachable(pg_container):
    engine = pg_container["engine"]
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


@pytest.mark.integration
def test_mongo_container_is_reachable(mongo_container):
    from pymongo import MongoClient
    client = MongoClient(mongo_container["url"])
    result = client.admin.command("ping")
    assert result.get("ok") == 1.0
    client.close()


@pytest.mark.integration
def test_db_session_fixture_provides_working_session(db_session):
    result = db_session.execute(text("SELECT 42 AS answer"))
    assert result.scalar() == 42


@pytest.mark.integration
def test_mongo_db_fixture_supports_insert_and_find(mongo_db):
    mongo_db.test_col.insert_one({"hello": "world"})
    doc = mongo_db.test_col.find_one({"hello": "world"})
    assert doc is not None
    assert doc["hello"] == "world"
