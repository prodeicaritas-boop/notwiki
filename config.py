import os

# ==========================================
# CONFIGURATION SETTINGS
# ==========================================
# This file holds the "rules" for our robot.
# It tells the robot how to behave, where to look, and what secrets to use.

# 1. SECRET CREDENTIALS
# We get these from the computer's hidden safe (Environment Variables).
# We never write passwords directly in the code!
EMAIL_SENDER = os.environ.get("EMAIL_NOTIFY_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_NOTIFY_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_NOTIFY_RECEIVER")

# 2. FILE PATHS
# Where we save our work.
DATA_DIR = "data"
DAILY_DATA_DIR = os.path.join(DATA_DIR, "daily")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
ASSETS_DIR = "assets"
THUMBNAILS_DIR = os.path.join(ASSETS_DIR, "thumbnails")
LOGS_DIR = "logs"
ERROR_LOG = os.path.join(LOGS_DIR, "error_report.txt")
BROKEN_LINKS_LOG = os.path.join(LOGS_DIR, "broken_links.txt")

# 3. ROBOT DISGUISE (User-Agents)
# The website might block us if it knows we are a robot.
# We wear different "masks" (User-Agents) to look like normal web browsers.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

# 4. TIMING RULES
# How long to wait between actions.
MIN_SLEEP = 3  # Minimum seconds to wait
MAX_SLEEP = 7  # Maximum seconds to wait
RETRY_SLEEP = 60 # Seconds to wait if we get blocked (Error 429)

# 5. IMAGE SETTINGS
IMAGE_QUALITY = 70
IMAGE_MAX_WIDTH = 150
