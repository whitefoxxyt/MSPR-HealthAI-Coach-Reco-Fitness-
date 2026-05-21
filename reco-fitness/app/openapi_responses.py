"""
Reponses HTTP communes a documenter dans OpenAPI (RF-16).

Les schemas FastAPI declarent par defaut 200 + 422. Ce module centralise les
codes additionnels que le frontend doit pouvoir distinguer : 401 (JWT
absent/invalide), 404 (ressource introuvable), 429 (rate limit), 503
(dependance externe injoignable).
"""
from typing import Any

ERROR_EXAMPLE = {"application/json": {"example": {"detail": "Message d'erreur lisible."}}}

UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    401: {
        "description": "JWT manquant ou invalide.",
        "content": {
            "application/json": {"example": {"detail": "Token JWT manquant ou expire."}}
        },
    },
}

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {
        "description": "Ressource demandee introuvable.",
        "content": ERROR_EXAMPLE,
    },
}

RATE_LIMITED: dict[int | str, dict[str, Any]] = {
    429: {
        "description": "Quota depasse (10 generations / heure, 3 / minute par utilisateur).",
        "content": {
            "application/json": {
                "example": {"error": "Rate limit exceeded: 10 per 1 hour"}
            }
        },
    },
}

SERVICE_UNAVAILABLE: dict[int | str, dict[str, Any]] = {
    503: {
        "description": (
            "Dependance externe injoignable (PostgreSQL ou MongoDB). Le service"
            " degrade automatiquement vers le tier free quand MSPR-AUTH est"
            " injoignable, donc 503 ne provient jamais de l'auth."
        ),
        "content": ERROR_EXAMPLE,
    },
}


def auth_responses() -> dict[int | str, dict[str, Any]]:
    """
    Reponses standard pour un endpoint protege par JWT et qui touche au moins
    une dependance externe (Mongo, PG, MSPR-AUTH). Tous les endpoints /api/v1
    du service tombent dans cette categorie.
    """
    return {**UNAUTHORIZED, **SERVICE_UNAVAILABLE}
