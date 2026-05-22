"""
Tests de qualite de la doc OpenAPI generee par FastAPI (RF-16).

Verifient les criteres d'acceptance de l'issue 27 :
- tags configures et coherents (liste fermee)
- descriptions presentes et non vides
- exemples de requete/reponse
- codes d'erreur HTTP documentes (401, 404, 422, 429, 503)
- /docs, /redoc, /openapi.json rendent sans erreur
"""
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


# Tags officiels du service. La liste vient des criteres d'acceptance de
# l'issue 27 et doit etre stable : tout nouveau endpoint doit reutiliser
# un tag existant pour rester coherent.
OFFICIAL_TAGS = {"Sante", "Profil", "Recommandations", "Feedback", "Historique"}


def _all_operations():
    """Itere sur (method, path, operation_object) du schema OpenAPI."""
    schema = app.openapi()
    for path, methods in schema["paths"].items():
        for method, op in methods.items():
            yield method, path, op


def test_all_endpoints_use_official_tags():
    """Chaque endpoint a au moins un tag, et tous ses tags sont officiels."""
    offenders = []
    for method, path, op in _all_operations():
        tags = op.get("tags") or []
        if not tags or any(t not in OFFICIAL_TAGS for t in tags):
            offenders.append(f"{method.upper()} {path} -> {tags}")
    assert not offenders, (
        "Endpoints avec tag manquant ou hors liste officielle "
        f"{sorted(OFFICIAL_TAGS)} : {offenders}"
    )


def test_docs_endpoints_render():
    """/docs, /redoc et /openapi.json doivent etre accessibles sans erreur."""
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    body = schema.json()
    # Tous les endpoints prevus par l'issue 27 doivent apparaitre dans le schema
    expected_paths = {
        "/health",
        "/api/v1/fitness-profile/me",
        "/api/v1/recommendations",
        "/api/v1/programs/{program_id}/feedback",
        "/api/v1/programs/me",
        "/api/v1/feedback/me",
    }
    assert expected_paths.issubset(body["paths"].keys())


def test_app_metadata_complete():
    """Title, version semver, description longue qui mentionne PRD + tiers."""
    schema = app.openapi()
    info = schema["info"]
    assert info["title"]
    assert info["version"].count(".") >= 1, "version doit etre semver"
    description = info.get("description") or ""
    assert len(description) >= 200, "description app trop courte"
    # On veut que la doc OpenAPI pointe vers le PRD et explique le freemium.
    assert "RF-" in description or "PRD" in description or "#13" in description, (
        "description doit referencer la PRD"
    )
    assert "free" in description.lower(), "description doit mentionner les tiers"


def _has_request_examples(op: dict) -> bool:
    """Vrai si l'operation a au moins un example sur son requestBody."""
    rb = op.get("requestBody") or {}
    for content in rb.get("content", {}).values():
        if content.get("example") or content.get("examples"):
            return True
        # Pydantic peut aussi exposer un example dans le schema referencee.
        schema = content.get("schema") or {}
        if schema.get("example") or schema.get("examples"):
            return True
    return False


def test_endpoints_with_body_have_examples():
    """
    Tout endpoint avec un requestBody doit exposer au moins un exemple,
    pour que le frontend voit quoi envoyer dans Swagger UI.
    """
    offenders = []
    for method, path, op in _all_operations():
        if op.get("requestBody") and not _has_request_examples(op):
            offenders.append(f"{method.upper()} {path}")
    assert not offenders, "RequestBody sans example :\n" + "\n".join(offenders)


def test_protected_endpoints_document_401():
    """Tout endpoint sous /api/v1 doit documenter une reponse 401 (JWT manquant/invalide)."""
    offenders = []
    for method, path, op in _all_operations():
        if not path.startswith("/api/v1"):
            continue
        if "401" not in op["responses"]:
            offenders.append(f"{method.upper()} {path}")
    assert not offenders, "401 absent du schema :\n" + "\n".join(offenders)


def test_endpoints_that_can_404_document_it():
    """
    Les endpoints qui lisent une ressource specifique doivent documenter 404.
    Inventaire derive du code (fitness_profile_service, feedback_service).
    """
    must_document_404 = {
        ("get", "/api/v1/fitness-profile/me"),
        ("put", "/api/v1/programs/{program_id}/feedback"),
    }
    offenders = []
    for method, path, op in _all_operations():
        if (method, path) in must_document_404 and "404" not in op["responses"]:
            offenders.append(f"{method.upper()} {path}")
    assert not offenders, "404 manquant :\n" + "\n".join(offenders)


def test_recommendations_documents_429():
    """POST /recommendations doit documenter 429 puisqu'il est rate-limite."""
    schema = app.openapi()
    op = schema["paths"]["/api/v1/recommendations"]["post"]
    assert "429" in op["responses"], "429 absent du POST /recommendations"


def test_external_dependent_endpoints_document_503():
    """
    Tout endpoint qui ecrit/lit Mongo ou PostgreSQL doit documenter 503
    pour signaler une panne de dependance externe au frontend.
    """
    must_document_503 = {
        ("get", "/api/v1/fitness-profile/me"),
        ("put", "/api/v1/fitness-profile/me"),
        ("post", "/api/v1/recommendations"),
        ("put", "/api/v1/programs/{program_id}/feedback"),
        ("get", "/api/v1/programs/me"),
        ("get", "/api/v1/feedback/me"),
    }
    offenders = []
    for method, path, op in _all_operations():
        if (method, path) in must_document_503 and "503" not in op["responses"]:
            offenders.append(f"{method.upper()} {path}")
    assert not offenders, "503 manquant :\n" + "\n".join(offenders)


def test_all_endpoints_have_rich_description():
    """
    Chaque endpoint a un summary court et une description longue.
    Seuil 80 caracteres : la description doit donner cas d'usage + limitations,
    pas juste reprendre le summary.
    """
    offenders = []
    for method, path, op in _all_operations():
        summary = (op.get("summary") or "").strip()
        description = (op.get("description") or "").strip()
        if not summary:
            offenders.append(f"{method.upper()} {path} : summary absent")
        if len(description) < 80:
            offenders.append(
                f"{method.upper()} {path} : description trop courte "
                f"({len(description)} chars)"
            )
    assert not offenders, "Descriptions OpenAPI insuffisantes :\n" + "\n".join(offenders)
