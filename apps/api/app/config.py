from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Postgres
    postgres_user: str = "case_user"
    postgres_password: str = "change_me_in_production"
    postgres_db: str = "case_db"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "change_me_in_production"
    api_cors_origins: list[str] = ["http://localhost:3000"]

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Vault encryption – 32-byte hex key for AES-256-GCM.
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    vault_encryption_key: str = "change_me_in_production_64_hex_chars_00000000000000000000000000000000"
    # Previous key kept during rotation so existing tokens can still be decrypted.
    vault_encryption_key_previous: str = ""

    # Google OAuth (optional – leave blank to disable)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:3000/auth/google/callback"

    @property
    def database_url(self) -> str:
        """Async URL for asyncpg (used at runtime)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync URL for psycopg2 (used by Alembic migrations)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
