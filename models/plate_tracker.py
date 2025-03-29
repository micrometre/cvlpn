from ..config import TRACKING_PARAMS, OUTPUT_FOLDER  # Add this line
import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import cv2
import os
import uuid
import datetime
import time


class PlateTracker:
    """Advanced plate tracking with machine learning-inspired tracking"""
    
    def __init__(self, queue):
        self.plate_history = defaultdict(list)
        self.confirmed_plates = set()
        self.queue = queue
    
    def _sanitize_plate_text(self, plate_text: str) -> Optional[str]:
        plate_text = ''.join(c for c in plate_text if c.isalnum()).upper()
        return plate_text if len(plate_text) >= 3 else None
    
    def update(self, plate_text: str, position: Tuple[int, int, int, int], 
               frame_num: int, frame: np.ndarray, video_path: str) -> bool:
        plate_text = self._sanitize_plate_text(plate_text)
        if not plate_text:
            return False
        
        detection_id = str(uuid.uuid4())
        x, y, w, h = position
        
        for plate_id, history in list(self.plate_history.items()):
            if not history:
                continue
                
            last_pos = history[-1][1]
            distance = np.linalg.norm(np.array(position[:2]) - np.array(last_pos[:2]))
            
            if (plate_text == plate_id.split('_')[1] and 
                distance < TRACKING_PARAMS['MAX_MOVEMENT_PIXELS']):
                
                self.plate_history[plate_id].append((plate_text, position, frame_num))
                
                if len(self.plate_history[plate_id]) >= TRACKING_PARAMS['MIN_REPEATED_DETECTIONS']:
                    return self._process_confirmed_plate(
                        plate_text, position, frame_num, frame, video_path, detection_id
                    )
        
        self.plate_history[f"plate_{plate_text}"].append((plate_text, position, frame_num))
        return False
    
    def _process_confirmed_plate(self, plate_text: str, position: Tuple[int, int, int, int], 
                                frame_num: int, frame: np.ndarray, 
                                video_path: str, detection_id: str) -> bool:
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
        
        return self.queue.put_plate(plate_data)
    
    def _save_plate_image(self, frame: np.ndarray, position: Tuple[int, int, int, int], 
                         plate_text: str, detection_id: str) -> str:
        x, y, w, h = position
        plate_img = frame[y:y+h, x:x+w]
        
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        
        plate_img = cv2.resize(plate_img, (0,0), fx=2.0, fy=2.0)
        plate_img = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        plate_img = cv2.threshold(plate_img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        plate_img = cv2.GaussianBlur(plate_img, (3, 3), 0)
        
        filename = f"{detection_id}.jpg"
        image_path = os.path.join(OUTPUT_FOLDER, filename)
        cv2.imwrite(image_path, plate_img)
        
        return image_path