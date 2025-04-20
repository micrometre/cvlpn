import datetime
import cv2
import numpy as np
import pytesseract
import os
import uuid
import requests  # Add this import for HTTP requests
from collections import defaultdict
from beanstalkc import Connection as BeanstalkConnection

# ======================
# CONFIGURATION SECTION
# ======================
# Define folders for input videos and output images
VIDEOS_FOLDER = "videos"
OUTPUT_FOLDER = "public/images"

# Process every Nth frame to reduce computational load
PROCESS_EVERY_N_FRAMES = 300

# Display live progress in the console
SHOW_LIVE_PROGRESS = True

# Beanstalkd configuration for queuing detected plates
BEANSTALKD_HOST = 'localhost'
BEANSTALKD_PORT = 11300
BEANSTALKD_TUBE = 'license_plates'

# Plate detection parameters (size and aspect ratio constraints)
MIN_ASPECT_RATIO = 2.0
MAX_ASPECT_RATIO = 6.0
MIN_WIDTH = 50
MAX_WIDTH = 500
MIN_HEIGHT = 20
MAX_HEIGHT = 150

# Tracking parameters for plate detection
PLATE_MEMORY = 5  # Number of frames to remember a plate
MIN_REPEATED_DETECTIONS = 3  # Minimum detections to confirm a plate
MAX_MOVEMENT_PIXELS = 100  # Maximum movement allowed between frames

# OCR configuration for Tesseract
TESSERACT_CONFIG = '--psm 11 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
# ======================

# Ensure the output folder exists
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

class BeanstalkdQueue:
    """Handles connection and communication with Beanstalkd queue."""
    def __init__(self):
        self.connection = None
        self.connect()
    
    def connect(self):
        """Establish connection to Beanstalkd."""
        try:
            self.connection = BeanstalkConnection(host=BEANSTALKD_HOST, port=BEANSTALKD_PORT)
            self.connection.use(BEANSTALKD_TUBE)
            print(f"✅ Connected to Beanstalkd at {BEANSTALKD_HOST}:{BEANSTALKD_PORT}")
        except Exception as e:
            print(f"⚠️ Failed to connect to Beanstalkd: {str(e)}")
            self.connection = None
    
    def put_plate(self, plate_data):
        """Queue plate data to Beanstalkd."""
        if not self.connection:
            self.connect()
            if not self.connection:
                return False
        
        try:
            import json
            self.connection.put(json.dumps(plate_data))
            print(plate_data)
            return True
        except Exception as e:
            print(f"⚠️ Failed to queue plate: {str(e)}")
            self.connection = None
            return False

class PlateTracker:
    """Tracks detected plates and confirms valid ones."""
    def __init__(self, queue):
        self.plate_history = defaultdict(list)  # History of detected plates
        self.confirmed_plates = set()  # Set of confirmed plates
        self.queue = queue  # Beanstalkd queue instance
    
    def update(self, plate_text, position, frame_num, frame, video_path):
        """Update plate tracking and confirm valid plates."""
        if not plate_text or len(plate_text) < 3:
            return False
        
        # Generate a unique ID for this detection
        detection_id = str(uuid.uuid4())
        
        # Check against existing plates
        for plate_id, history in list(self.plate_history.items()):
            if not history:
                continue
                
            last_pos = history[-1][1]
            distance = np.linalg.norm(np.array(position[:2]) - np.array(last_pos[:2]))
            
            # Check if the plate matches and is within movement constraints
            if (plate_text == plate_id.split('_')[1] and 
                distance < MAX_MOVEMENT_PIXELS):
                self.plate_history[plate_id].append((plate_text, position, frame_num))
                
                # Confirm the plate if it has enough repeated detections
                if len(self.plate_history[plate_id]) >= MIN_REPEATED_DETECTIONS:
                    image_path = self._save_plate_image(frame, position, plate_text, detection_id)
                    self.confirmed_plates.add(plate_text)
                    
                    # Add plate data to the queue
                    plate_data = {
                        'uuid': detection_id,
                        'plate': plate_text,
                        'timestamp': datetime.datetime.now().isoformat(),
                        'position': position,
                        'frame_num': frame_num,
                        'video_source': os.path.basename(video_path),
                        'image_path': image_path,
                        'image_url': f"/images/{os.path.basename(image_path)}"  # Adjust based on web server config
                    }
                    
                    if self.queue.put_plate(plate_data):
                        print(f"📤 Queued plate: {plate_text} (ID: {detection_id})")
                    
                    return True
                return False
        
        # New plate detection
        plate_id = f"plate_{plate_text}"
        self.plate_history[plate_id].append((plate_text, position, frame_num))
        return False

    def _save_plate_image(self, frame, position, plate_text, detection_id):
        """Save the detected plate image to the output folder."""
        x, y, w, h = position
        plate_img = frame[y:y+h, x:x+w]
        
        # Create a dated subfolder
        today = datetime.date.today().strftime("%Y-%m-%d")
        day_folder = os.path.join(OUTPUT_FOLDER)
        os.makedirs(day_folder, exist_ok=True)
        
        # Enhance the image before saving
        plate_img = cv2.resize(plate_img, (0,0), fx=2.0, fy=2.0)
        plate_img = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        plate_img = cv2.threshold(plate_img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        
        # Generate a filename with the UUID
        filename = f"{detection_id}.jpg"
        image_path = os.path.join(day_folder, filename)
        cv2.imwrite(image_path, plate_img)
        
        return image_path



class BeanstalkdDrainer:
    """Drains the Beanstalkd queue and uploads data to a remote HTTP server with robust error handling."""
    def __init__(self, host, port, tube, server_url, max_retries=3, timeout=10):
        self.server_url = server_url
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()  # Use session for connection pooling
        self._setup_connection(host, port, tube)

    def _setup_connection(self, host, port, tube):
        """Setup connection to Beanstalkd with error handling."""
        try:
            self.connection = BeanstalkConnection(host=host, port=port)
            self.connection.watch(tube)
            print(f"✅ Connected to Beanstalkd for draining at {host}:{port}")
        except Exception as e:
            print(f"⚠️ Failed to connect to Beanstalkd for draining: {str(e)}")
            self.connection = None

    def drain_queue(self):
        """Drains the queue and sends data to the remote server with retry logic."""
        if not self.connection:
            print("⚠️ No connection to Beanstalkd. Exiting.")
            return

        print(f"🚀 Starting to drain the Beanstalkd queue to {self.server_url}...")
        while True:
            job = None
            try:
                job = self.connection.reserve(timeout=5)
                if not job:
                    print("✅ Queue is empty. Exiting.")
                    break

                plate_data = self._parse_job_data(job)
                if not plate_data:
                    job.delete()
                    continue

                success = self._process_job_with_retries(job, plate_data)
                if not success:
                    print(f"⚠️ Max retries reached for plate: {plate_data.get('plate', 'unknown')}")
                    job.bury()  # Bury the job after max retries

            except Exception as e:
                print(f"⚠️ Error while processing job: {str(e)}")
                if job:
                    job.release()  # Release the job back to the queue
                continue

    def _parse_job_data(self, job):
        """Parse and validate job data."""
        try:
            import json
            plate_data = json.loads(job.body)
            
            # Validate required fields
            required_fields = ['uuid', 'plate', 'timestamp', 'image_url']
            if not all(field in plate_data for field in required_fields):
                print("⚠️ Invalid plate data: missing required fields")
                return None
                
            return plate_data
        except json.JSONDecodeError:
            print("⚠️ Failed to parse job data as JSON")
            return None
        except Exception as e:
            print(f"⚠️ Error parsing job data: {str(e)}")
            return None

    def _process_job_with_retries(self, job, plate_data):
        """Process job with retry logic."""
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    self.server_url,
                    json=plate_data,
                    timeout=self.timeout,
                    headers={
                        'Content-Type': 'application/json',
                        'User-Agent': 'LicensePlateProcessor/1.0'
                    }
                )

                if response.status_code == 200:
                    print(f"✅ Successfully uploaded plate data: {plate_data['plate']} (Attempt {attempt + 1})")
                    job.delete()
                    return True
                else:
                    print(f"⚠️ Failed to upload plate data (Attempt {attempt + 1}): "
                          f"{response.status_code} - {response.text[:200]}")

            except requests.exceptions.RequestException as e:
                print(f"⚠️ Network error uploading plate data (Attempt {attempt + 1}): {str(e)}")

            # Exponential backoff before retry
            if attempt < self.max_retries:
                wait_time = (2 ** attempt) * 1  # Exponential backoff: 1, 2, 4 seconds
                print(f"⏳ Waiting {wait_time} seconds before retry...")
                import time
                time.sleep(wait_time)

        return False        

def process_video(video_path, queue):
    """Process a video file to detect and track license plates."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"⚠️ Error opening video: {video_path}")
        return

    tracker = PlateTracker(queue)
    frame_count = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_count += 1
        
        # Process every Nth frame
        if frame_count % PROCESS_EVERY_N_FRAMES == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mser = cv2.MSER_create()
            regions, _ = mser.detectRegions(gray)
            
            for region in regions:
                x, y, w, h = cv2.boundingRect(region.reshape(-1, 1, 2))
                aspect_ratio = w / h
                
                # Check if the region matches plate constraints
                if (MIN_ASPECT_RATIO < aspect_ratio < MAX_ASPECT_RATIO and 
                    MIN_WIDTH < w < MAX_WIDTH and 
                    MIN_HEIGHT < h < MAX_HEIGHT):
                    
                    plate_roi = gray[y:y+h, x:x+w]
                    plate_roi = cv2.threshold(plate_roi, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
                    plate_roi = cv2.medianBlur(plate_roi, 3)
                    
                    # Perform OCR to extract plate text
                    plate_text = pytesseract.image_to_string(plate_roi, config=TESSERACT_CONFIG).strip()
                    if plate_text:
                        if SHOW_LIVE_PROGRESS:
                            print(f"Frame {frame_count}: Detected - {plate_text} at ({x},{y})")
                        
                        # Update the tracker with the detected plate
                        if tracker.update(plate_text, (x, y, w, h), frame_count, frame, video_path):
                            print(f"✅ Saved and queued plate: {plate_text}")

    cap.release()
    print(f"Completed processing: {os.path.basename(video_path)}")

if __name__ == "__main__":
    print("🚀 Starting plate image extraction with Beanstalkd queue...")
    print(f"Configuration:\n"
         f"- Processing every {PROCESS_EVERY_N_FRAMES} frames\n"
         f"- Minimum plate size: {MIN_WIDTH}x{MIN_HEIGHT} pixels\n"
         f"- Require {MIN_REPEATED_DETECTIONS} confirmations\n"
         f"- Queue: {BEANSTALKD_HOST}:{BEANSTALKD_PORT}/{BEANSTALKD_TUBE}")

    queue = BeanstalkdQueue()

    # Iterate through all video files in the input folder
    for video_file in os.listdir(VIDEOS_FOLDER):
        if not video_file.lower().endswith('.mp4'):
            continue

        video_path = os.path.join(VIDEOS_FOLDER, video_file)
        print(f"\n🔍 Processing: {video_file}")
        process_video(video_path, queue)

    print(f"\nAll done! Plate images saved to: {os.path.abspath(OUTPUT_FOLDER)}")

    # Start draining the queue and uploading to the remote server
    REMOTE_SERVER_URL = "http://localhost:5000/api"  # Replace with your server URL
    drainer = BeanstalkdDrainer(BEANSTALKD_HOST, BEANSTALKD_PORT, BEANSTALKD_TUBE, REMOTE_SERVER_URL)
    drainer.drain_queue()