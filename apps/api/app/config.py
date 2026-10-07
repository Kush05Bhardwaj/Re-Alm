from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: str = "http://localhost:3000"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "realm"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"

    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


settings = Settings()
