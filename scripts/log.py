"""
log.py

Sets up a logger that writes to logs/app.log and prints to console.
Import get_logger() wherever you need logging.
"""

import os
import logging


def get_logger(name="DocumentLoader"):
    """
    Create and return a logger.

    - Writes DEBUG and above to logs/app.log
    - Prints INFO and above to the console
    """

    logger = logging.getLogger(name)

    # Only add handlers once
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Create logs folder
    os.makedirs("logs", exist_ok=True)

    # File handler
    file_handler = logging.FileHandler("logs/app.log")
    file_handler.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Format
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger