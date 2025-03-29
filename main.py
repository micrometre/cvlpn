import numpy as np  # Add this line at the top of the file
import os
import time
import logging
from .utils.logging_setup import setup_logging
from .models.queue_manager import BeanstalkdQueue
from .srevices.video_service import process_video

from .config import *

def main():
    setup_logging()
    logging.info("🚀 Starting License Plate Detection System")
    
    # Initialize components
    queue = BeanstalkdQueue()
    
    # Process videos
    for video_file in os.listdir(VIDEOS_FOLDER):
        if video_file.lower().endswith(('.mp4', '.avi', '.mov')):
            video_path = os.path.join(VIDEOS_FOLDER, video_file)
            logging.info(f"🔍 Processing: {video_file}")
            try:
                process_video(video_path, queue)
            except Exception as e:
                logging.error(f"Failed to process {video_file}: {e}")

    logging.info(f"Processing complete. Output saved to: {os.path.abspath(OUTPUT_FOLDER)}")

if __name__ == "__main__":
    main()