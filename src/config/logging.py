import logging
import os

# Create logs folder at project root
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Log file path
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# Configure basic logging
logging.basicConfig(
    level=logging.DEBUG,  # capture everything
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()  # also logger.info to console
    ]
)

logger = logging.getLogger("backend_logger")
logger.info("Logging is set up. Logs will be saved to %s", LOG_FILE)