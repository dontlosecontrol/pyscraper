import logging
import logging.config
import os
from typing import Optional

from config.config_manager import ConfigManager


DEFAULT_LOG_DIR = "logs"


def get_scraper_logger(scraper_name: str, config_manager: ConfigManager, log_dir: Optional[str] = None) -> logging.Logger:
    """
    Creates and returns a logger for a specific scraper.

    Args:
        scraper_name: Name of the scraper (e.g., 'cli', 'knifecenter').
        config_manager: The ConfigManager instance.
        log_dir: Directory for storing logs (defaults to "logs").

    Returns:
        Configured logger instance.
    """
    effective_log_dir = log_dir or DEFAULT_LOG_DIR
    #log_file = os.path.join(effective_log_dir, f"{scraper_name.lower()}.log")
    log_file = os.path.join(effective_log_dir, f"{config_manager.config.log_file.lower()}")
    

    log_level_str = getattr(config_manager.config, 'log_level', 'INFO').upper()
    logger_name = f"scraper.{scraper_name}"

    log_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': log_level_str,
                'formatter': 'standard',
                'stream': 'ext://sys.stdout',
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': log_level_str,
                'formatter': 'standard',
                'filename': log_file,
                'maxBytes': 10 * 1024 * 1024,
                'backupCount': 5,
                'encoding': 'utf-8',
            },
        },
        'loggers': {
            logger_name: {
                'handlers': ['console', 'file'],
                'level': log_level_str,
                'propagate': False,
            }
        }
    }
    
    # Create logs directory if it doesn't exist
    os.makedirs(effective_log_dir, exist_ok=True)
    
    logging.config.dictConfig(log_config)
    return logging.getLogger(logger_name)
