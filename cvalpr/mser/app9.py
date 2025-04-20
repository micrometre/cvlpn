import datetime
import cv2
import numpy as np
import pytesseract
import os
from collections import defaultdict
from beanstalkc import Connection as BeanstalkConnection  # Requires beanstalkc package

# ======================
# CONFIGURATION SECTION
# ======================
VIDEOS_FOLDER = "videos"            # Folder containing input videos
OUTPUT_FOLDER = "plate_images"      # Where to save plate images
PROCESS_EVERY_N_FRAMES = 30         # Process every Nth frame (1 = all frames)
SHOW_LIVE_PROGRESS = True           # Print detection progress to console

# Beanstalkd configuration
BEANSTALKD_HOST = 'localhost'       # Beanstalkd server host
BEANSTALKD_PORT = 11300             # Beanstalkd server port
BEANSTALKD_TUBE = 'license_plates'  # Queue tube name

# Plate detection parameters
MIN_ASPECT_RATIO = 2.0              # Minimum width/height ratio for plates
MAX_ASPECT_RATIO = 6.0              # Maximum width/height ratio
MIN_WIDTH = 50                      # Minimum plate width (pixels)
MAX_WIDTH = 500                     # Maximum plate width
MIN_HEIGHT = 20                     # Minimum plate height
MAX_HEIGHT = 150                    # Maximum plate height

# Tracking parameters
PLATE_MEMORY = 5                    # Remember plates for N frames
MIN_REPEATED_DETECTIONS = 3         # Confirm plate after N detections
MAX_MOVEMENT_PIXELS = 100           # Max movement between frames to count as same plate

# OCR configuration
TESSERACT_CONFIG = '--psm 11 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
# ======================

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

class BeanstalkdQueue:
    def __init__(self):
        self.connection = None
        self.connect()
    
    def connect(self):
        try:
            self.connection = BeanstalkConnection(host=BEANSTALKD_HOST, port=BEANSTALKD_PORT)
            self.connection.use(BEANSTALKD_TUBE)
            print(f"✅ Connected to Beanstalkd at {BEANSTALKD_HOST}:{BEANSTALKD_PORT}")
        except Exception as e:
            print(f"⚠️ Failed to connect to Beanstalkd: {str(e)}")
            self.connection = None
    
    def put_plate(self, plate_data):
        """Add a license plate detection to the queue"""
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
    def __init__(self, queue):
        self.plate_history = defaultdict(list)
        self.confirmed_plates = set()
        self.queue = queue
    
    def update(self, plate_text, position, frame_num, frame):
        if not plate_text or len(plate_text) < 3:  # Minimum 3 characters
            return False
        
        # Check against existing plates
        for plate_id, history in list(self.plate_history.items()):
            if not history:
                continue
                
            last_pos = history[-1][1]
            distance = np.linalg.norm(np.array(position[:2]) - np.array(last_pos[:2]))
            
            if (plate_text == plate_id.split('_')[1] and 
                distance < MAX_MOVEMENT_PIXELS):
                self.plate_history[plate_id].append((plate_text, position, frame_num))
                
                if len(self.plate_history[plate_id]) >= MIN_REPEATED_DETECTIONS:
                    self._save_plate_image(frame, position, plate_text)
                    self.confirmed_plates.add(plate_text)
                    
                    # Add to queue
                    plate_data = {
                        'plate_text': plate_text,
                        'timestamp': datetime.datetime.now().isoformat(),
                        'position': position,
                        'frame_num': frame_num,
                        'video_source': os.path.basename(video_path)
                    }
                    if self.queue.put_plate(plate_data):
                        print(f"📤 Queued plate: {plate_text}")
                    
                    return True
                return False
        
        # New plate detection
        plate_id = f"plate_{plate_text}"
        self.plate_history[plate_id].append((plate_text, position, frame_num))
        return False

    def _save_plate_image(self, frame, position, plate_text):
        x, y, w, h = position
        plate_img = frame[y:y+h, x:x+w]
        
        # Enhance image before saving
        plate_img = cv2.resize(plate_img, (0,0), fx=2.0, fy=2.0)  # 2x upscale
        plate_img = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        plate_img = cv2.threshold(plate_img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        
        filename = f"{plate_text}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        cv2.imwrite(os.path.join(OUTPUT_FOLDER, filename), plate_img)

def process_video(video_path, queue):
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
        
        if frame_count % PROCESS_EVERY_N_FRAMES == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mser = cv2.MSER_create()
            regions, _ = mser.detectRegions(gray)
            
            for region in regions:
                x, y, w, h = cv2.boundingRect(region.reshape(-1, 1, 2))
                aspect_ratio = w / h
                
                if (MIN_ASPECT_RATIO < aspect_ratio < MAX_ASPECT_RATIO and 
                    MIN_WIDTH < w < MAX_WIDTH and 
                    MIN_HEIGHT < h < MAX_HEIGHT):
                    
                    plate_roi = gray[y:y+h, x:x+w]
                    plate_roi = cv2.threshold(plate_roi, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
                    plate_roi = cv2.medianBlur(plate_roi, 3)
                    
                    plate_text = pytesseract.image_to_string(plate_roi, config=TESSERACT_CONFIG).strip()
                    if plate_text:
                        if SHOW_LIVE_PROGRESS:
                            print(f"Frame {frame_count}: Detected - {plate_text} at ({x},{y})")
                        
                        if tracker.update(plate_text, (x, y, w, h), frame_count, frame):
                            print(f"✅ Saved and queued plate: {plate_text}")

    cap.release()
    print(f"Completed processing: {os.path.basename(video_path)}")

# Main execution
if __name__ == "__main__":
    print("🚀 Starting plate image extraction with Beanstalkd queue...")
    print(f"Configuration:\n"
         f"- Processing every {PROCESS_EVERY_N_FRAMES} frames\n"
         f"- Minimum plate size: {MIN_WIDTH}x{MIN_HEIGHT} pixels\n"
         f"- Require {MIN_REPEATED_DETECTIONS} confirmations\n"
         f"- Queue: {BEANSTALKD_HOST}:{BEANSTALKD_PORT}/{BEANSTALKD_TUBE}")

    # Initialize Beanstalkd queue
    queue = BeanstalkdQueue()

    for video_file in os.listdir(VIDEOS_FOLDER):
        if not video_file.lower().endswith('.mp4'):
            continue

        video_path = os.path.join(VIDEOS_FOLDER, video_file)
        print(f"\n🔍 Processing: {video_file}")
        process_video(video_path, queue)

    print(f"\nAll done! Plate images saved to: {os.path.abspath(OUTPUT_FOLDER)}")