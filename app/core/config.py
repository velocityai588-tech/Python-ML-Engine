from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # Add this line - default to False if not in .env
    DEBUG: bool = False 
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()