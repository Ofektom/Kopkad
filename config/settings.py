import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import logging

# Load environment variables from specific .env file
load_dotenv("/Users/decagon/Documents/Ofektom/savings-system/.env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info(f"Raw POSTGRES_URI from os.getenv: {os.getenv('POSTGRES_URI')}")

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
    PAYSTACK_SECRET_KEY: str
    ENV: str
    REDIS_URL: str | None = None  # Optional Redis cache URL
    
    # Financial Advisor ML Parameters
    ANOMALY_DETECTION_CONTAMINATION: float = 0.1
    ANOMALY_DEVIATION_THRESHOLD: float = 50.0  # percentage
    RECURRING_EXPENSE_MIN_OCCURRENCES: int = 3
    RECURRING_INTERVAL_TOLERANCE: float = 0.3  # 30% variation
    SAVINGS_RATE_TARGET_MIN: float = 10.0  # percentage
    SAVINGS_RATE_TARGET_OPTIMAL: float = 20.0  # percentage
    SAVINGS_RATE_TARGET_AGGRESSIVE: float = 30.0  # percentage
    
    # Notification Settings
    ENABLE_EMAIL_NOTIFICATIONS: bool = True
    ENABLE_PROACTIVE_ALERTS: bool = True
    OVERSPENDING_ALERT_THRESHOLD: float = 20.0  # percentage increase
    GOAL_BEHIND_SCHEDULE_THRESHOLD: float = 20.0  # percentage behind
    HEALTH_SCORE_UPDATE_DAYS: int = 7  # days between auto-updates
    
    # Score Calculation Weights (should sum to 100)
    SCORE_WEIGHT_EXPENSE_RATIO: int = 30
    SCORE_WEIGHT_SAVINGS_RATE: int = 25
    SCORE_WEIGHT_GOAL_ACHIEVEMENT: int = 20
    SCORE_WEIGHT_SPENDING_CONSISTENCY: int = 15
    SCORE_WEIGHT_SAVINGS_ACTIVITY: int = 10

    model_config = SettingsConfigDict(
        env_file="/Users/decagon/Documents/Ofektom/savings-system/.env",
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
        logger.info(f"Settings loaded POSTGRES_URI: {self.POSTGRES_URI}")
        logger.info(f"Settings BASE_DIR after init: {self.BASE_DIR}")
        logger.info(
            f"SMTP Settings - Host: {self.SMTP_HOST}, Port: {self.SMTP_PORT}, Username: {self.SMTP_USERNAME}, Password: {self.SMTP_PASSWORD[:4]}****"
        )
        logger.info(f"GOOGLE_REDIRECT_URI from settings: {self.GOOGLE_REDIRECT_URI}")
        logger.info(f"PAYSTACK_SECRET_KEY: {self.PAYSTACK_SECRET_KEY[:4]}****")

settings = Settings()