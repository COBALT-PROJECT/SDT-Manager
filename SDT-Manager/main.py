# File: main.py
from sdt_manager_core import SDT_ManagerCore
import logging
import time
import signal
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("sdt_manager.log")
    ]
)
logger = logging.getLogger(__name__)

def signal_handler(sig, frame):
    logger.info("Shutdown signal received")
    if manager:
        manager.stop()
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start the manager
    manager = SDT_ManagerCore()
    manager.start()
    
    logger.info("SDT Manager running. Press CTRL+C to exit.")
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        manager.stop()
        logger.info("SDT Manager shutdown complete")