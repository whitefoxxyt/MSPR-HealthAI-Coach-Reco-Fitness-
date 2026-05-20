"""
Initialisation des collections MongoDB du service Reco-Fitness.

Cree les 3 collections de la plateforme HealthAI Coach (cf. MSPR-MongoDB)
et les index necessaires. Idempotent : peut etre rejoue sans casser.

Usage :
    # depuis du code Python (sync, pymongo)
    from app.db.init_mongo import init_mongo
    init_mongo(db)

    # depuis le shell (utilise MONGO_URI + MONGO_DATABASE)
    python -m app.db.init_mongo
"""
from pymongo.database import Database
from pymongo import ASCENDING, DESCENDING


COLLECTIONS = ("user_fitness_profiles", "workout_programs", "recommendation_history")


def init_mongo(db: Database) -> None:
    """
    Cree les collections et index attendus par le service Reco-Fitness.
    Idempotent : MongoDB ignore une creation de collection ou d'index deja existante.
    """
    existing = set(db.list_collection_names())
    for name in COLLECTIONS:
        if name not in existing:
            db.create_collection(name)

    # user_id unique : un seul profil fitness par utilisateur (upsert s'appuie dessus).
    db["user_fitness_profiles"].create_index(
        [("user_id", ASCENDING)], unique=True, name="user_id_unique"
    )
    # Lecture par utilisateur, du plus recent au plus ancien.
    db["workout_programs"].create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_recent"
    )
    db["recommendation_history"].create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_recent"
    )


def _main() -> None:
    from pymongo import MongoClient
    from app.config import settings

    client = MongoClient(settings.MONGO_URI)
    try:
        init_mongo(client[settings.MONGO_DATABASE])
    finally:
        client.close()


if __name__ == "__main__":
    _main()
