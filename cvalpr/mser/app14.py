import os
import sys
import uuid
import json
import time
import logging
import datetime
from typing import Dict, List, Tuple, Optional, Any

# Abstract base classes for extensibility
from abc import ABC, abstractmethod

# Third-party library imports
import cv2
import numpy as np
import pytesseract
import requests
from beanstalkc import Connection as BeanstalkConnection
from collections import defaultdict

class ConfigurationError(Exception):
    """Custom exception for configuration-related errors."""
    pass

class Configuration:
    """
    Centralized configuration management with multiple sources support.
    Supports configuration from environment variables, config files, and default values.
    """
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration from multiple sources with priority:
        1. Environment Variables
        2. Configuration File
        3. Default Values
        """
        config = {}
        
        # Load from environment variables
        config.update(cls._load_env_config())
        
        # Load from config file if provided
        if config_path and os.path.exists(config_path):
            config.update(cls._load_file_config(config_path))
        
        # Apply default configurations
        config = cls._apply_defaults(config)
        
        return config
    
    @staticmethod
    def _load_env_config() -> Dict[str, str]:
        """Load configuration from environment variables."""
        return {
            key[5:].lower(): value 
            for key, value in os.environ.items() 
            if key.startswith('PLATE_')
        }
    
    @staticmethod
    def _load_file_config(config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON or YAML file."""
        try:
            if config_path.endswith('.json'):
                with open(config_path, 'r') as f:
                    return json.load(f)
            elif config_path.endswith('.yaml') or config_path.endswith('.yml'):
                import yaml
                with open(config_path, 'r') as f:
                    return yaml.safe_load(f)
        except (ImportError, json.JSONDecodeError, yaml.YAMLError) as e:
            logging.error(f"Error loading configuration file: {e}")
        return {}
    
    @staticmethod
    def _apply_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply default configuration values."""
        defaults = {
            'videos_folder': 'public/videos',
            'output_folder': 'public/images',
            'process_frames_interval': 60,
            'remote_server_url': 'http://localhost:5000/alprd',
            'remote_upload_enabled': True,
            'remote_upload_retries': 3,
            'beanstalkd_host': 'localhost',
            'beanstalkd_port': 11300,
            'beanstalkd_tube': 'license_plates',
            'plate_detection': {
                'min_aspect_ratio': 2.0,
                'max_aspect_ratio': 6.0,
                'min_width': 50,
                'max_width': 500,
                'min_height': 20,
                'max_height': 150
            },
            'tracking': {
                'plate_memory': 5,
                'min_repeated_detections': 3,
                'max_movement_pixels': 100
            }
        }
        
        def deep_merge(base, update):
            for key, value in update.items():
                if isinstance(value, dict):
                    base[key] = deep_merge(base.get(key, {}), value)
                else:
                    base[key] = value
            return base
        
        return deep_merge(defaults, config)

class LoggerFactory:
    """Centralized logging configuration and management."""
    
    @staticmethod
    def create_logger(name: str = 'plate_detection', 
                      log_level: str = 'INFO', 
                      log_file: Optional[str] = 'plate_detection.log') -> logging.Logger:
        """
        Create a logger with console and file output.
        Supports different log levels and optional file logging.
        """
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, log_level.upper()))
        
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s: %(message)s'
        ))
        logger.addHandler(console_handler)
        
        # File Handler (optional)
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s: %(message)s'
            ))
            logger.addHandler(file_handler)
        
        return logger

class DataUploader(ABC):
    """Abstract base class for data uploaders."""
    
    @abstractmethod
    def upload(self, data: Dict[str, Any]) -> bool:
        """Upload method to be implemented by concrete classes."""
        pass

class RemoteServerUploader(DataUploader):
    """Concrete implementation of remote server data uploader."""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create a configured requests session."""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'LicensePlateProcessor/3.0',
            'Content-Type': 'application/json'
        })
        return session
    
    def upload(self, data: Dict[str, Any]) -> bool:
        """
        Upload data with exponential backoff and comprehensive error handling.
        """
        if not self.config.get('remote_upload_enabled', False):
            self.logger.info("Remote upload is disabled")
            return False
        
        retries = self.config.get('remote_upload_retries', 3)
        url = self.config.get('remote_server_url')
        
        for attempt in range(retries + 1):
            try:
                response = self.session.post(url, json=data, timeout=10)
                
                if response.status_code in (200, 201):
                    self.logger.info(f"Successfully uploaded data: {data.get('plate', 'Unknown')}")
                    return True
                
                self.logger.warning(f"Upload failed (Attempt {attempt + 1}): "
                                    f"{response.status_code} - {response.text[:200]}")
            
            except requests.RequestException as e:
                self.logger.error(f"Network error uploading data (Attempt {attempt + 1}): {e}")
            
            # Exponential backoff
            if attempt < retries:
                wait_time = 2 ** attempt
                self.logger.info(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
        
        return False

class MessageQueue(ABC):
    """Abstract base class for message queues."""
    
    @abstractmethod
    def send(self, message: Dict[str, Any]) -> bool:
        """Send method to be implemented by concrete classes."""
        pass

class BeanstalkdMessageQueue(MessageQueue):
    """Concrete implementation of Beanstalkd message queue."""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.connection = None
        self._connect()
    
    def _connect(self):
        """Establish connection to Beanstalkd."""
        try:
            self.connection = BeanstalkConnection(
                host=self.config.get('beanstalkd_host', 'localhost'),
                port=self.config.get('beanstalkd_port', 11300)
            )
            self.connection.use(self.config.get('beanstalkd_tube', 'license_plates'))
            self.logger.info("Connected to Beanstalkd successfully")
        except Exception as e:
            self.logger.error(f"Beanstalkd connection failed: {e}")
            self.connection = None
    
    def send(self, message: Dict[str, Any]) -> bool:
        """Send message to queue with error handling."""
        if not self.connection:
            self._connect()
        
        if not self.connection:
            return False
        
        try:
            self.connection.put(json.dumps(message))
            self.logger.info(f"Message sent to queue: {message.get('plate', 'Unknown')}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send message to queue: {e}")
            return False

class PlateDetector:
    """Advanced license plate detection and tracking system."""
    
    def __init__(self, config: Dict[str, Any], 
                 logger: logging.Logger, 
                 uploader: DataUploader, 
                 queue: MessageQueue):
        self.config = config
        self.logger = logger
        self.uploader = uploader
        self.queue = queue
        self.plate_history = defaultdict(list)
        self.confirmed_plates = set()
    
    def process_video(self, video_path: str):
        """Process video for license plate detection."""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.logger.error(f"Error opening video: {video_path}")
                return

            frame_count = 0
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_count += 1
                
                # Process every N frames based on configuration
                if frame_count % self.config['process_frames_interval'] == 0:
                    self._detect_plates(frame, frame_count, video_path)

            cap.release()
        except Exception as e:
            self.logger.error(f"Video processing error: {e}")
    
    def _detect_plates(self, frame: np.ndarray, frame_count: int, video_path: str):
        """Detect plates in a single frame."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mser = cv2.MSER_create()
        regions, _ = mser.detectRegions(gray)
        
        for region in regions:
            x, y, w, h = cv2.boundingRect(region.reshape(-1, 1, 2))
            
            if self._is_valid_plate_region(w, h):
                plate_roi = self._preprocess_plate_roi(gray[y:y+h, x:x+w])
                plate_text = self._ocr_plate(plate_roi)
                
                if plate_text:
                    self._track_plate(plate_text, (x, y, w, h), frame_count, frame, video_path)
    
    def _is_valid_plate_region(self, width: int, height: int) -> bool:
        """Check if a region matches plate detection parameters."""
        aspect_ratio = width / height
        plate_config = self.config['plate_detection']
        return (plate_config['min_aspect_ratio'] < aspect_ratio < plate_config['max_aspect_ratio'] and
                plate_config['min_width'] < width < plate_config['max_width'] and
                plate_config['min_height'] < height < plate_config['max_height'])
    
    def _preprocess_plate_roi(self, plate_roi: np.ndarray) -> np.ndarray:
        """Preprocess plate region of interest."""
        plate_roi = cv2.threshold(plate_roi, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        plate_roi = cv2.medianBlur(plate_roi, 3)
        return plate_roi
    
    def _ocr_plate(self, plate_roi: np.ndarray) -> Optional[str]:
        """Perform OCR on plate region."""
        config = '--psm 11 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        plate_text = pytesseract.image_to_string(plate_roi, config=config).strip()
        return plate_text if len(plate_text) >= 3 else None
    
    def _track_plate(self, plate_text: str, position: Tuple[int, int, int, int], 
                     frame_count: int, frame: np.ndarray, video_path: str):
        """Track and confirm license plates."""
        plate_id = f"plate_{plate_text}"
        x, y, w, h = position
        
        self.plate_history[plate_id].append((plate_text, position, frame_count))
        
        # Check if plate meets confirmation criteria
        if len(self.plate_history[plate_id]) >= self.config['tracking']['min_repeated_detections']:
            self._process_confirmed_plate(plate_text, position, frame_count, frame, video_path)
    
    def _process_confirmed_plate(self, plate_text: str, position: Tuple[int, int, int, int], 
                                  frame_count: int, frame: np.ndarray, video_path: str):
        """Process and save confirmed license plate."""
        x, y, w, h = position
        image_path = self._save_plate_image(frame, position, plate_text)
        
        plate_data = {
            'uuid': str(uuid.uuid4()),
            'plate': plate_text,
            'timestamp': datetime.datetime.now().isoformat(),
            'frame_num': frame_count,
            'video_source': os.path.basename(video_path),
            'image_path': image_path
        }
        
        self.uploader.upload(plate_data)
        self.queue.send(plate_data)
        self.logger.info(f"Processed plate: {plate_text}")
    
    def _save_plate_image(self, frame: np.ndarray, position: Tuple[int, int, int, int], 
                           plate_text: str) -> str:
        """Save detected plate image."""
        x, y, w, h = position
        plate_img = frame[y:y+h, x:x+w]
        plate_img = cv2.resize(plate_img, (0, 0), fx=2.0, fy=2.0)
        plate_img = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        plate_img = cv2.threshold(plate_img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        
        output_folder = self.config.get('output_folder', 'public/images')
        os.makedirs(output_folder, exist_ok=True)
        
        filename = f"{plate_text}_{uuid.uuid4()}.jpg"
        image_path = os.path.join(output_folder, filename)
        cv2.imwrite(image_path, plate_img)
        
        return image_path

class LicensePlateDetectionSystem:
    """Main application orchestrator."""
    
    def __init__(self, config_path: Optional[str] = None):
        # Load configuration
        self.config = Configuration.load(config_path)
        
        # Setup logging
        self.logger = LoggerFactory.create_logger(
            log_level=self.config.get('log_level', 'INFO')
        )
        
        # Initialize components
        self.uploader = RemoteServerUploader(self.config, self.logger)
        self.queue = BeanstalkdMessageQueue(self.config, self.logger)
        self.detector = PlateDetector(
            self.config, self.logger, self.uploader, self.queue
        )
    
    def run(self, videos_folder: Optional[str] = None):
        """Run license plate detection on videos."""
        folder = videos_folder or self.config.get('videos_folder', 'public/videos')
        
        self.logger.info(f"Starting license plate detection in {folder}")
        
        for filename in os.listdir(folder):
            if filename.lower().endswith(('.mp4', '.avi', '.mov')):
                video_path = os.path.join(folder, filename)
                self.logger.info(f"Processing video:  {self.config}")
                self.detector.process_video(video_path)
        
        self.logger.info("License plate detection completed")

def main():
    """Entry point for the application."""
    try:
        detection_system = LicensePlateDetectionSystem()
        detection_system.run()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()