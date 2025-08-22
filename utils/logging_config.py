import logging.config

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
        "simple": {"format": "%(asctime)s %(name)s %(levelname)s %(message)s"},
    },
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/scraper.json",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "formatter": "json",
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/errors.json",
            "maxBytes": 10485760,
            "backupCount": 10,
            "formatter": "json",
            "level": "ERROR",
        },
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "scraper": {"handlers": ["file", "error_file", "console"], "level": "INFO", "propagate": False},
        "players": {"handlers": ["file", "error_file", "console"], "level": "INFO", "propagate": False},
        "services": {"handlers": ["file", "error_file", "console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}

# Initialize logging configuration
logging.config.dictConfig(LOGGING_CONFIG)


class ErrorTracker:
    """Track and categorize errors for monitoring"""

    @staticmethod
    def categorize_error(error: Exception) -> str:
        """Categorize error for metrics tracking"""
        error_type = type(error).__name__
        error_msg = str(error).lower()

        if "rate limit" in error_msg:
            return "rate_limit"
        elif "session" in error_msg and "expired" in error_msg:
            return "session_expired"
        elif "timeout" in error_msg:
            return "timeout"
        elif "connection" in error_msg:
            return "connection"
        elif "authentication" in error_msg or "unauthorized" in error_msg:
            return "auth"
        else:
            return error_type

    @staticmethod
    async def log_error(category: str, error: Exception, context: dict = None):
        """Log error with structured context"""
        logger = logging.getLogger("scraper")

        error_data = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "error_category": category,
            "context": context or {},
        }

        logger.error(f"Error occurred: {category}", extra=error_data)
