# config/settings.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    POSTGRES_URI: str
    SECRET_KEY: str
    JWT_ALGORITHM: str
    REFRESH_TOKEN_EXPIRES_IN: int
    ACCESS_TOKEN_EXPIRES_IN: int
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    SMTP_FROM_EMAIL: str
    SMTP_FROM_NAME: str
    BASE_DIR: str
    GOOGLE_CLIENT_ID: str | None
    GOOGLE_CLIENT_SECRET: str | None
    GOOGLE_REDIRECT_URI: str | None
    FACEBOOK_CLIENT_ID: str | None
    FACEBOOK_CLIENT_SECRET: str | None
    FACEBOOK_REDIRECT_URI: str | None
    APP_BASE_URL: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def __init__(self, **kwargs):
        if not os.getenv("BASE_DIR"):
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            os.environ["BASE_DIR"] = base_dir
            logger.info(f"Set BASE_DIR dynamically to: {base_dir}")
        else:
            logger.info(f"Using BASE_DIR from environment: {os.getenv('BASE_DIR')}")

        super().__init__(**kwargs)
        logger.info(f"Settings BASE_DIR after init: {self.BASE_DIR}")
        logger.info(f"SMTP Settings - Host: {self.SMTP_HOST}, Port: {self.SMTP_PORT}, Username: {self.SMTP_USERNAME}, Password: {self.SMTP_PASSWORD[:4]}****")
        logger.info(f"GOOGLE_REDIRECT_URI from settings: {self.GOOGLE_REDIRECT_URI}")

settings = Settings()