from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PostgreSQL
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "reco_fitness"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"

    # MongoDB
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DATABASE: str = "reco_fitness"

    # Auth
    BETTER_AUTH_SECRET: str = "changeme"
    AUTH_API_URL: str = "http://localhost:8001"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
