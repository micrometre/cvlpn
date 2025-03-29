
import numpy as np  # Add this line at the top of the file
import os
import cv2
from datetime import datetime
from ..config import OUTPUT_FOLDER

class FileService:
    """Handles all file system operations"""
    
    @staticmethod
    def ensure_output_dir():
        """Create output directory if missing"""
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    @staticmethod
    def save_plate_image(image: np.ndarray, filename: str) -> str:
        """Save processed plate image"""
        FileService.ensure_output_dir()
        path = os.path.join(OUTPUT_FOLDER, filename)
        cv2.imwrite(path, image)
        return path
    
    @staticmethod
    def get_video_files() -> list:
        """Get all video files from input directory"""
        return [
            f for f in os.listdir(VIDEOS_FOLDER)
            if f.lower().endswith(('.mp4', '.avi', '.mov'))
        ]