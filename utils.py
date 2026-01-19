import hashlib
import logging
import os
from config import LOGS_DIR

# ==========================================
# HELPER TOOLS (Utils)
# ==========================================
# These are small tools that help the main robot do specific jobs,
# like creating ID tags or writing in a diary (logging).

def get_unique_id(text_to_hash):
    """
    Creates a unique fingerprint (ID) for a piece of text (like a URL).

    Think of this like taking a fingerprint. No matter how many times
    you check the same URL, it will always give the same fingerprint code.
    This helps us avoid saving duplicates.
    """
    # 1. Convert the text to a standard format (bytes)
    text_bytes = text_to_hash.encode('utf-8')

    # 2. Use the MD5 mathematical formula to create a hash
    hash_object = hashlib.md5(text_bytes)

    # 3. Return the code as a string of letters and numbers
    return hash_object.hexdigest()

def setup_logger(name, log_file, level=logging.INFO):
    """
    Sets up a diary (logger) for the robot to write down what it does.

    Args:
        name: The name of the logger (like "MainRobot").
        log_file: The file where the diary entries will be saved.
        level: How detailed the notes should be.
    """
    # Create the folder for logs if it doesn't exist
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    # Also log to console (stdout) for GitHub Actions visibility
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

def save_error(message, error_file):
    """
    Writes a specific error message to the error report.
    """
    with open(error_file, "a") as f:
        f.write(f"{message}\n")
