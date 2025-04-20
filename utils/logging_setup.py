import logging
import os
from ..config import OUTPUT_FOLDER

def setup_logging():
    """Configure logging system"""
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(OUTPUT_FOLDER, 'plate_detection.log')),
            logging.StreamHandler()
        ]
    )
    logging.info("Logging system initialized")