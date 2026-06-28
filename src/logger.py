"""GhostTrack — Simple file-based logger."""

import logging
from pathlib import Path

LOG_FILE = Path("ghosttrack.log")


def setup_logger() -> logging.Logger:
    """Create and configure the 'ghosttrack' logger.

    • Level: DEBUG (captures everything; filtering happens at handler level)
    • Handler: FileHandler writing to ghosttrack.log
    • Format: timestamp | level | message
    • Avoids adding duplicate handlers on repeated calls.
    """
    logger = logging.getLogger("ghosttrack")
    logger.setLevel(logging.DEBUG)

    # Guard against duplicate handlers when setup_logger() is called more than once.
    if not logger.handlers:
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def get_logger() -> logging.Logger:
    """Return the 'ghosttrack' logger instance.

    Callers should call setup_logger() once at startup; after that,
    use get_logger() everywhere to obtain the shared logger.
    """
    return logging.getLogger("ghosttrack")
