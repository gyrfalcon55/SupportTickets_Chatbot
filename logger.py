import logging
from datetime import datetime
from pathlib import Path

# Resolve the project root (parent of the directory containing this file).
PROJECT_ROOT = Path(__file__).resolve().parents[0]

# Create the logs directory inside the project root.
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = datetime.now().strftime("%m_%d_%Y_%H_%M.log")
LOG_FILE_PATH = LOGS_DIR / LOG_FILE

logging.basicConfig(
    filename=LOG_FILE_PATH,
    format="[ %(asctime)s ] %(lineno)d %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
