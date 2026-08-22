"""
Structured Logging Framework for Multi-Agent Financial Analysis System.
Provides JSON formatting for file storage/observability and readable console output.
"""

import json
import logging
import logging.config
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure project root is in sys.path for module resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))



class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs structured JSON log records.
    Captures timestamps, log levels, source location, and arbitrary extra fields.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception info if present
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        # Include custom extra metadata passed during logging
        # Standard attributes of LogRecord to ignore in 'extra'
        standard_attrs = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "module", "msecs",
            "message", "msg", "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "thread", "threadName"
        }

        extra_data = {
            k: v for k, v in record.__dict__.items()
            if k not in standard_attrs and not k.startswith("_")
        }
        if extra_data:
            log_payload["extra"] = extra_data

        return json.dumps(log_payload, ensure_ascii=False)


_logging_initialized = False


def setup_logging(
    config_path: Optional[str | Path] = None,
    default_level: str = "INFO",
    logs_dir: Optional[str | Path] = None,
) -> None:
    """
    Initialize logging configuration.
    Loads YAML config if available, otherwise sets up robust fallback logging.
    """
    global _logging_initialized

    # Ensure logs directory exists
    if logs_dir is None:
        logs_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    else:
        logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Determine config file path
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent.parent / "configs" / "logging.yaml"
    else:
        config_path = Path(config_path)

    if config_path.exists():
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            # Ensure the log file path in config has absolute or valid directory
            if "handlers" in config and "file" in config["handlers"]:
                config["handlers"]["file"]["filename"] = str(logs_dir / "app.log")

            logging.config.dictConfig(config)
            _logging_initialized = True
            return
        except Exception as e:
            # Fallback if YAML parsing or dictConfig fails
            sys.stderr.write(f"Warning: Failed to load logging config from {config_path}: {e}. Using fallback.\n")

    # Fallback basic configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, default_level.upper(), logging.INFO))
    root_logger.handlers.clear()

    # Console Handler (Human-readable)
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File Handler (JSON structured)
    try:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            filename=str(logs_dir / "app.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)
    except Exception as err:
        sys.stderr.write(f"Warning: Failed to create log file handler: {err}\n")

    _logging_initialized = True


def get_logger(name: str = "finagent") -> logging.Logger:
    """
    Get a configured logger instance.
    Ensures logging setup is performed on first call.
    """
    global _logging_initialized
    if not _logging_initialized:
        setup_logging()
    return logging.getLogger(name)


if __name__ == "__main__":
    # Self-test when executed directly
    setup_logging()
    logger = get_logger("src.test")
    logger.info("Structured logging framework initialized successfully!", extra={"ticker": "VNM", "phase": 0})
    logger.warning("Sample warning log for testing rotation and format.", extra={"status": "ok"})
    print("Logger test passed. Check logs/app.log for JSON output.")
