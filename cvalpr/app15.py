import datetime
import cv2
import numpy as np
import pytesseract
import os
import uuid
import requests
from collections import defaultdict
from beanstalkc import Connection as BeanstalkConnection
import time
import json
import logging
from typing import Dict, List, Tuple, Optional

# ======================
# CONFIGURATION MANAGEMENT
# ======================
class Config:
    """Centralized configuration management with environment variable support."""
    
    @staticmethod
    def get(key: str, default=None, cast=str):
        """
        Retrieve configuration with support for environment variables and type casting.
        Allows overriding via environment variables with prefix PLATE_
        """
        env_key = f"PLATE_{key.upper()}"
        value = os.environ.get(env_key, os.environ.get(key, default))
        
        try:
            return cast(value)
        except (ValueError, TypeError):
            return default

# Core Configuration
VIDEOS_FOLDER = Config.get('VIDEOS_FOLDER', 'public/videos')
OUTPUT_FOLDER = Config.get('OUTPUT_FOLDER', 'public/images')
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

# Plate Detection Parameters
PLATE_DETECTION_PARAMS = {
    'MIN_ASPECT_RATIO': Config.get('MIN_ASPECT_RATIO', 2.0, float),
    'MAX_ASPECT_RATIO': Config.get('MAX_ASPECT_RATIO', 6.0, float),
    'MIN_WIDTH': Config.get('MIN_WIDTH', 50, int),
    'MAX_WIDTH': Config.get('MAX_WIDTH', 500, int),
    'MIN_HEIGHT': Config.get('MIN_HEIGHT', 20, int),
    'MAX_HEIGHT': Config.get('MAX_HEIGHT', 150, int)
}

# Tracking Parameters
TRACKING_PARAMS = {
    'PLATE_MEMORY': Config.get('PLATE_MEMORY', 5, int),
    'MIN_REPEATED_DETECTIONS': Config.get('MIN_REPEATED_DETECTIONS', 3, int),
    'MAX_MOVEMENT_PIXELS': Config.get('MAX_MOVEMENT_PIXELS', 100, int)
}

# OCR Configuration
TESSERACT_CONFIG = '--psm 11 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('plate_detection.log'),
        logging.StreamHandler()
    ]
)

class RemoteServerUploader:
    """Enhanced remote server uploader with comprehensive error handling."""
    
    def __init__(self, url: str, api_key: str = '', retries: int = 3):
        self.url = url
        self.retries = retries
        self.session = self._create_session(api_key)
    
    def _create_session(self, api_key: str) -> requests.Session:
        """Create a configured requests session."""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'LicensePlateProcessor/2.0',
            'Content-Type': 'application/json'
        })
        if api_key:
            session.headers['Authorization'] = f'Bearer {api_key}'
        return session
    
    def upload_plate_data(self, plate_data: Dict) -> bool:
        """
        Upload plate data with advanced error handling and logging.
        Implements exponential backoff and detailed error tracking.
        """
        if not REMOTE_UPLOAD_ENABLED:
            logging.info("Remote upload is disabled")
            return False
        
        for attempt in range(self.retries + 1):
            try:
                response = self.session.post(
                    self.url,
                    data=json.dumps(plate_data),
                    timeout=10
                )
                
                if response.status_code in (200, 201):
                    logging.info(f"Successfully uploaded plate {plate_data.get('plate', 'Unknown')}")
                    return True
                
                logging.warning(f"Server rejected plate (Attempt {attempt + 1}): "
                                f"{response.status_code} - {response.text[:200]}")
            
            except requests.exceptions.RequestException as e:
                logging.error(f"Network error uploading plate (Attempt {attempt + 1}): {e}")
            
            # Exponential backoff
            if attempt < self.retries:
                wait_time = (2 ** attempt)
                logging.info(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
        
        return False

class BeanstalkdQueue:
    """Robust Beanstalkd queue with connection management and retry logic."""
    
    def __init__(self, remote_uploader: RemoteServerUploader):
        self.remote_uploader = remote_uploader
        self.connection = None
        self.connect()
    
    def connect(self) -> bool:
        """Establish connection to Beanstalkd with robust error handling."""
        try:
            self.connection = BeanstalkConnection(
                host=BEANSTALKD_HOST, 
                port=BEANSTALKD_PORT
            )
            self.connection.use(BEANSTALKD_TUBE)
            logging.info(f"Connected to Beanstalkd at {BEANSTALKD_HOST}:{BEANSTALKD_PORT}")
            return True
        except Exception as e:
            logging.error(f"Beanstalkd connection failed: {e}")
            self.connection = None
            return False
    
    def put_plate(self, plate_data: Dict) -> bool:
        """Intelligent plate queuing with fallback mechanisms."""
        # Attempt direct upload first if enabled
        if REMOTE_UPLOAD_ENABLED:
            if self.remote_uploader.upload_plate_data(plate_data):
                return True
        
        # Fallback to Beanstalkd
        if not self.connection and not self.connect():
            return False
        
        try:
            self.connection.put(json.dumps(plate_data))
            logging.info(f"Queued plate to Beanstalkd: {plate_data.get('plate', 'Unknown')}")
            return True
        except Exception as e:
            logging.error(f"Failed to queue plate: {e}")
            self.connection = None
            return False

class PlateTracker:
    """Advanced plate tracking with machine learning-inspired tracking."""
    
    def __init__(self, queue: BeanstalkdQueue):
        self.plate_history: Dict[str, List[Tuple]] = defaultdict(list)
        self.confirmed_plates: set = set()
        self.queue = queue
    
    def _sanitize_plate_text(self, plate_text: str) -> Optional[str]:
        """Clean and validate plate text."""
        plate_text = ''.join(c for c in plate_text if c.isalnum()).upper()
        return plate_text if len(plate_text) >= 3 else None
    
    def update(self, plate_text: str, position: Tuple[int, int, int, int], 
               frame_num: int, frame: np.ndarray, video_path: str) -> bool:
        """Intelligent plate tracking and confirmation."""
        plate_text = self._sanitize_plate_text(plate_text)
        if not plate_text:
            return False
        
        detection_id = str(uuid.uuid4())
        x, y, w, h = position
        
        # Check for similar existing plates with proximity
        for plate_id, history in list(self.plate_history.items()):
            if not history:
                continue
                
            last_pos = history[-1][1]
            distance = np.linalg.norm(np.array(position[:2]) - np.array(last_pos[:2]))
            
            # Advanced plate matching
            if (plate_text == plate_id.split('_')[1] and 
                distance < TRACKING_PARAMS['MAX_MOVEMENT_PIXELS']):
                
                self.plate_history[plate_id].append((plate_text, position, frame_num))
                
                # Confident plate detection
                if len(self.plate_history[plate_id]) >= TRACKING_PARAMS['MIN_REPEATED_DETECTIONS']:
                    return self._process_confirmed_plate(
                        plate_text, position, frame_num, frame, video_path, detection_id
                    )
        
        # New plate detection
        self.plate_history[f"plate_{plate_text}"].append((plate_text, position, frame_num))
        return False
    
    def _process_confirmed_plate(self, plate_text: str, position: Tuple[int, int, int, int], 
                                  frame_num: int, frame: np.ndarray, 
                                  video_path: str, detection_id: str) -> bool:
        """Process and save confirmed license plates."""
        x, y, w, h = position
        image_path = self._save_plate_image(frame, position, plate_text, detection_id)
        self.confirmed_plates.add(plate_text)
        
        plate_data = {
            'uuid': detection_id,
            'plate': plate_text,
            'timestamp': datetime.datetime.now().isoformat(),
            'position': position,
            'frame_num': frame_num,
            'video_source': os.path.basename(video_path),
            'image_path': image_path,
            'image_url': f"/images/{os.path.basename(image_path)}",
            'confidence': len(self.plate_history[f"plate_{plate_text}"]) / TRACKING_PARAMS['MIN_REPEATED_DETECTIONS'],
            'system_time': time.time()
        }
        
        if self.queue.put_plate(plate_data):
            logging.info(f"Processed plate: {plate_text} (ID: {detection_id})")
            return True
        
        return False
    
    def _save_plate_image(self, frame: np.ndarray, position: Tuple[int, int, int, int], 
                           plate_text: str, detection_id: str) -> str:
        """Advanced image preprocessing and saving."""
        x, y, w, h = position
        plate_img = frame[y:y+h, x:x+w]
        
        today = datetime.date.today().strftime("%Y-%m-%d")
        day_folder = os.path.join(OUTPUT_FOLDER)
        os.makedirs(day_folder, exist_ok=True)
        
        # Enhanced image preprocessing
        plate_img = cv2.resize(plate_img, (0,0), fx=2.0, fy=2.0)
        plate_img = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        plate_img = cv2.threshold(plate_img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        plate_img = cv2.GaussianBlur(plate_img, (3, 3), 0)
        
        filename = f"{detection_id}.jpg"
        image_path = os.path.join(day_folder, filename)
        cv2.imwrite(image_path, plate_img)
        
        return image_path

def process_video(video_path: str, queue: BeanstalkdQueue) -> None:
    """Robust video processing with comprehensive error handling."""
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logging.error(f"Error opening video: {video_path}")
            return

        tracker = PlateTracker(queue)
        frame_count, fps = 0, cap.get(cv2.CAP_PROP_FPS)
        start_time = time.time()
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_count += 1
            
            # Process every Nth frame
            if frame_count % PROCESS_EVERY_N_FRAMES == 0:
                current_time = frame_count / fps
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                mser = cv2.MSER_create()
                regions, _ = mser.detectRegions(gray)
                
                for region in regions:
                    x, y, w, h = cv2.boundingRect(region.reshape(-1, 1, 2))
                    aspect_ratio = w / h
                    
                    # Dynamic region filtering
                    if (PLATE_DETECTION_PARAMS['MIN_ASPECT_RATIO'] < aspect_ratio < PLATE_DETECTION_PARAMS['MAX_ASPECT_RATIO'] and 
                        PLATE_DETECTION_PARAMS['MIN_WIDTH'] < w < PLATE_DETECTION_PARAMS['MAX_WIDTH'] and 
                        PLATE_DETECTION_PARAMS['MIN_HEIGHT'] < h < PLATE_DETECTION_PARAMS['MAX_HEIGHT']):
                        
                        plate_roi = gray[y:y+h, x:x+w]
                        plate_roi = cv2.threshold(plate_roi, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
                        plate_roi = cv2.medianBlur(plate_roi, 3)
                        
                        plate_text = pytesseract.image_to_string(plate_roi, config=TESSERACT_CONFIG).strip()
                        if plate_text:
                            if SHOW_LIVE_PROGRESS:
                                logging.info(f"Frame {frame_count} ({current_time:.1f}s): Detected - {plate_text} at ({x},{y})")
                            
                            tracker.update(plate_text, (x, y, w, h), frame_count, frame, video_path)

        cap.release()
        processing_time = time.time() - start_time
        logging.info(f"Completed processing: {os.path.basename(video_path)} in {processing_time:.1f} seconds")
    
    except Exception as e:
        logging.error(f"Unexpected error processing video {video_path}: {e}")

def main():
    """Main execution point with comprehensive startup logging."""
    logging.info("🚀 Starting Enhanced License Plate Detection")
    logging.info(f"Configuration Summary:\n"
                 f"- Processing every {PROCESS_EVERY_N_FRAMES} frames\n"
                 f"- Plate size: {PLATE_DETECTION_PARAMS['MIN_WIDTH']}x{PLATE_DETECTION_PARAMS['MIN_HEIGHT']} pixels\n"
                 f"- Confirmations required: {TRACKING_PARAMS['MIN_REPEATED_DETECTIONS']}\n"
                 f"- Remote upload: {'ENABLED' if REMOTE_UPLOAD_ENABLED else 'DISABLED'}\n"
                 f"- Remote server: {REMOTE_SERVER_URL if REMOTE_UPLOAD_ENABLED else 'Not configured'}")

    # Initialize components
    remote_uploader = RemoteServerUploader(
        REMOTE_SERVER_URL, 
        REMOTE_SERVER_API_KEY, 
        REMOTE_UPLOAD_RETRIES
    )
    queue = BeanstalkdQueue(remote_uploader)

    # Process videos
    for video_file in os.listdir(VIDEOS_FOLDER):
        if video_file.lower().endswith(('.mp4', '.avi', '.mov')):
            video_path = os.path.join(VIDEOS_FOLDER, video_file)
            logging.info(f"🔍 Processing: {video_file}")
            process_video(video_path, queue)

    logging.info(f"All done! Plate images saved to: {os.path.abspath(OUTPUT_FOLDER)}")

if __name__ == "__main__":
    main()