import os

class Config:
    """Centralized configuration management"""
    
    @staticmethod
    def get(key: str, default=None, cast: type = str):
        env_key = f"PLATE_{key.upper()}"
        value = os.environ.get(env_key, os.environ.get(key, default))
        try:
            return cast(value)
        except (ValueError, TypeError):
            return default

# Core Configuration
VIDEOS_FOLDER = Config.get('VIDEOS_FOLDER', 'license_plate_detector/public/videos')
OUTPUT_FOLDER = Config.get('OUTPUT_FOLDER', 'license_plate_detector/public/images')
PROCESS_EVERY_N_FRAMES = Config.get('PROCESS_EVERY_N_FRAMES', 20, int)
SHOW_LIVE_PROGRESS = Config.get('SHOW_LIVE_PROGRESS', True, bool)

# Remote Server Configuration
REMOTE_SERVER_URL = Config.get('REMOTE_SERVER_URL', 'http://localhost:5000/alprd')
REMOTE_SERVER_API_KEY = Config.get('REMOTE_SERVER_API_KEY', '')
REMOTE_UPLOAD_ENABLED = Config.get('REMOTE_UPLOAD_ENABLED', True, bool)
REMOTE_UPLOAD_RETRIES = Config.get('REMOTE_UPLOAD_RETRIES', 3, int)

# Beanstalkd Configuration
BEANSTALKD_HOST = Config.get('BEANSTALKD_HOST', 'localhost')
BEANSTALKD_PORT = Config.get('BEANSTALKD_PORT', 11300, int)
BEANSTALKD_TUBE = Config.get('BEANSTALKD_TUBE', 'license_plates')

# Detection Parameters
PLATE_DETECTION_PARAMS = {
    'MIN_ASPECT_RATIO': Config.get('MIN_ASPECT_RATIO', 2.0, float),
    'MAX_ASPECT_RATIO': Config.get('MAX_ASPECT_RATIO', 6.0, float),
    'MIN_WIDTH': Config.get('MIN_WIDTH', 50, int),
    'MAX_WIDTH': Config.get('MAX_WIDTH', 500, int),
    'MIN_HEIGHT': Config.get('MIN_HEIGHT', 20, int),
    'MAX_HEIGHT': Config.get('MAX_HEIGHT', 150, int)
}

TRACKING_PARAMS = {
    'PLATE_MEMORY': Config.get('PLATE_MEMORY', 5, int),
    'MIN_REPEATED_DETECTIONS': Config.get('MIN_REPEATED_DETECTIONS', 3, int),
    'MAX_MOVEMENT_PIXELS': Config.get('MAX_MOVEMENT_PIXELS', 100, int)
}

TESSERACT_CONFIG = '--psm 11 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'