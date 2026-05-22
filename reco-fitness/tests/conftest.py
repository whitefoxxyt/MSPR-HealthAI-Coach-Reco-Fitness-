"""
Harnais de tests global pour reco-fitness.

Fixtures disponibles :
  pg_container   (session) : container PostgreSQL ephemere
  mongo_container (session) : container MongoDB ephemere
  db_session     (function): session SQLAlchemy isolee avec rollback
  mongo_db       (function): base MongoDB connectee au container
  mock_auth               : respx mockant GET /api/entitlements/me
  valid_jwt               : helper generant un JWT signe
"""
import time

import pytest
import respx
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# ------------------------------------------------------------
# Constantes de test
# ------------------------------------------------------------

TEST_SECRET = "test_better_auth_secret_for_ci"
TEST_AUTH_URL = "https://fake-mspr-auth"
ENTITLEMENTS_URL = f"{TEST_AUTH_URL}/api/entitlements/me"


# ------------------------------------------------------------
# Fixtures containers (scope=session -- 1 seul demarrage par run)
# ------------------------------------------------------------

@pytest.fixture(scope="session")
def pg_container():
    """
    Demarre un container PostgreSQL ephemere pour toute la session de tests.
    Joue les migrations via SQLAlchemy metadata (create_all).
    Necessite Docker. Marque tes tests @pytest.mark.integration pour les isoler.
    """
    try:
        from app.db.session import Base
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:16-alpine") as pg:
            engine = create_engine(pg.get_connection_url())
            Base.metadata.create_all(engine)
            yield {"engine": engine, "url": pg.get_connection_url()}
            Base.metadata.drop_all(engine)
    except Exception:
        pytest.skip("Docker non disponible -- tests d'integration ignores")


@pytest.fixture(scope="session")
def mongo_container():
    """
    Demarre un container MongoDB ephemere pour toute la session de tests.
    Joue init_mongo.py au demarrage (collections + index sur reco_fitness_test).
    Necessite Docker. Marque tes tests @pytest.mark.integration pour les isoler.
    """
    try:
        from app.db.init_mongo import init_mongo
        from pymongo import MongoClient
        from testcontainers.mongodb import MongoDbContainer

        with MongoDbContainer("mongo:7-jammy") as mongo:
            url = mongo.get_connection_url()
            client = MongoClient(url)
            try:
                init_mongo(client["reco_fitness_test"])
            finally:
                client.close()
            yield {"url": url}
    except Exception:
        pytest.skip("Docker non disponible -- tests d'integration ignores")


# ------------------------------------------------------------
# Fixtures session DB (scope=function -- isolation par test)
# ------------------------------------------------------------

@pytest.fixture()
def db_session(pg_container) -> Session:
    """
    Session SQLAlchemy isolee : chaque test demarre une transaction
    qui est annulee (rollback) apres le test -- la BDD reste propre.
    """
    engine = pg_container["engine"]
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = factory(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def mongo_db(mongo_container):
    """
    Client MongoDB connecte au container ephemere.
    La base est nettoyee apres chaque test.
    """
    from pymongo import MongoClient

    client = MongoClient(mongo_container["url"])
    db = client["reco_fitness_test"]

    yield db

    # Nettoyage apres chaque test : on vide les documents mais on garde
    # les collections et leurs index (init_mongo n'est rejoue qu'au demarrage du container).
    for name in db.list_collection_names():
        db[name].delete_many({})
    client.close()


# ------------------------------------------------------------
# Fixtures auth
# ------------------------------------------------------------

@pytest.fixture()
def valid_jwt():
    """
    Produit un JWT signe avec TEST_SECRET, valable 1h.
    Accepte un user_id et un email optionnels.
    """
    def _make(user_id: str = "test-user-1", email: str = "test@example.com") -> str:
        payload = {
            "sub": user_id,
            "email": email,
            "exp": int(time.time()) + 3600,
        }
        return jwt.encode(payload, TEST_SECRET, algorithm="HS256")

    return _make


@pytest.fixture()
def mock_auth():
    """
    Configure respx pour mocker GET /api/entitlements/me cote MSPR-AUTH.
    Par defaut repond tier=free. Surcharge dans le test avec .mock(...).

    Usage :
        def test_something(mock_auth):
            mock_auth.get(ENTITLEMENTS_URL).mock(
                return_value=httpx.Response(200, json={"tier": "premium", ...})
            )
    """
    with respx.mock(base_url=TEST_AUTH_URL, assert_all_called=False) as router:
        import httpx
        router.get("/api/entitlements/me").mock(
            return_value=httpx.Response(
                200,
                json={"tier": "free", "expires_at": None, "features": []},
            )
        )
        yield router
