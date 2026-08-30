from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_ID: int
    GEMINI_API_KEY: str
    CURRENCY_SYMBOL: str = "с"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def bot_token(self) -> str:
        return self.BOT_TOKEN

    @property
    def admin_id(self) -> int:
        return self.ADMIN_ID

    @property
    def gemini_api_key(self) -> str:
        return self.GEMINI_API_KEY

settings = Settings()