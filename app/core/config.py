from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_KEY: str
    ENV: str = "development"
    MODEL_VERSION: str = "v1.0.0-linucb"

    class Config:
        env_file = ".env"

settings = Settings()