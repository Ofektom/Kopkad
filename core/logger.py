import logging
import sys
from loguru import logger

class InterceptHandler(logging.Handler):
    """
    Default handler from examples in loguru documention.
    It intercepts standard logging messages and routes them to loguru.
    """
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

def setup_logging():
    # Remove standard loguru handlers (e.g., default console)
    logger.remove()
    
    # Add a JSON handler for production-style structured logging to stdout 
    # Render.com captures stdout natively
    logger.add(
        sys.stdout,
        serialize=True,  # Outputs JSON format
        enqueue=True,    # Thread-safe async queueing
        level="INFO",
    )
    
    # Optional: Human readable rolling log file (useful for local development)
    logger.add(
        "logs/app.log",
        rotation="10 MB",
        retention="10 days",
        level="INFO",
        enqueue=True,
        serialize=False, # standard readable format
    )

    # Intercept existing standard loggers (like uvicorn, fastapi, sqlalchemy, etc.)
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    for _log in ["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"]:
        _logger = logging.getLogger(_log)
        _logger.handlers = [InterceptHandler()]
        _logger.propagate = False

    logger.info("Structured logging (Loguru) initialized successfully.")
