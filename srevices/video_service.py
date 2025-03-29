import cv2
import pytesseract
from ..models.plate_tracker import PlateTracker
from ..config import *

def process_video(video_path: str, queue) -> None:
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError(f"Error opening video: {video_path}")

        tracker = PlateTracker(queue)
        frame_count, fps = 0, cap.get(cv2.CAP_PROP_FPS)
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_count += 1
            
            if frame_count % PROCESS_EVERY_N_FRAMES == 0:
                current_time = frame_count / fps
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                mser = cv2.MSER_create()
                regions, _ = mser.detectRegions(gray)
                
                for region in regions:
                    x, y, w, h = cv2.boundingRect(region.reshape(-1, 1, 2))
                    aspect_ratio = w / h
                    
                    if (PLATE_DETECTION_PARAMS['MIN_ASPECT_RATIO'] < aspect_ratio < PLATE_DETECTION_PARAMS['MAX_ASPECT_RATIO'] and 
                        PLATE_DETECTION_PARAMS['MIN_WIDTH'] < w < PLATE_DETECTION_PARAMS['MAX_WIDTH'] and 
                        PLATE_DETECTION_PARAMS['MIN_HEIGHT'] < h < PLATE_DETECTION_PARAMS['MAX_HEIGHT']):
                        
                        plate_roi = gray[y:y+h, x:x+w]
                        plate_roi = cv2.threshold(plate_roi, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
                        plate_roi = cv2.medianBlur(plate_roi, 3)
                        
                        plate_text = pytesseract.image_to_string(plate_roi, config=TESSERACT_CONFIG).strip()
                        if plate_text:
                            tracker.update(plate_text, (x, y, w, h), frame_count, frame, video_path)

        cap.release()
    except Exception as e:
        raise RuntimeError(f"Error processing video {video_path}: {e}")