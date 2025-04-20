import cv2
import numpy as np
import logging
from pathlib import Path
from typing import Tuple, List

class LicensePlateDetector:
    def __init__(self, 
                 weights_path: str = "yolov4-tiny.weights",
                 config_path: str = "yolov4-tiny.cfg",
                 confidence_threshold: float = 0.5):
        self.confidence_threshold = confidence_threshold
        self.logger = self._setup_logging()  # Initialize logger first
        self._load_model(weights_path, config_path)

    def _setup_logging(self):
        """Set up logging configuration and return logger instance."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)

    def _load_model(self, weights_path: str, config_path: str):
        """Load the YOLO model with proper error handling."""
        try:
            # Validate paths
            weights_file = Path(weights_path)
            config_file = Path(config_path)
            
            if not weights_file.exists():
                raise FileNotFoundError(f"Weights file not found at: {weights_path}")
            if not config_file.exists():
                raise FileNotFoundError(f"Config file not found at: {config_path}")
            
            # Load the network
            self.net = cv2.dnn.readNet(str(weights_file), str(config_file))
            
            # Get output layers
            layer_names = self.net.getLayerNames()
            self.output_layers = [
                layer_names[i - 1] 
                for i in self.net.getUnconnectedOutLayers().flatten()
            ]
            
            self.logger.info(
                f"Model loaded successfully from:\n"
                f"  Weights: {weights_file}\n"
                f"  Config: {config_file}"
            )
            
        except Exception as e:
            self.logger.error(
                f"Failed to initialize model:\n"
                f"  Error type: {type(e).__name__}\n"
                f"  Details: {str(e)}",
                exc_info=True  # This will include full traceback in logs
            )
            raise RuntimeError("Failed to initialize the detector") from e

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect license plates in a frame."""
        try:
            print("Processing new frame...")
            height, width = frame.shape[:2]
            blob = cv2.dnn.blobFromImage(
                frame, 1/255.0, (416, 416), 
                swapRB=True, crop=False
            )
            
            print("Running inference with YOLO model...")
            self.net.setInput(blob)
            outputs = self.net.forward(self.output_layers)
            
            boxes = []
            detections_count = 0
            for output in outputs:
                for detection in output:
                    scores = detection[5:]
                    class_id = np.argmax(scores)
                    confidence = scores[class_id]
                    
                    if confidence > self.confidence_threshold and class_id == 0:
                        detections_count += 1
                        center_x = int(detection[0] * width)
                        center_y = int(detection[1] * height)
                        w = int(detection[2] * width)
                        h = int(detection[3] * height)
                        
                        x = int(center_x - w / 2)
                        y = int(center_y - h / 2)
                        boxes.append((x, y, w, h))
            
            print(f"Found {detections_count} license plates in frame")
            return boxes
            
        except Exception as e:
            print(f"Error during detection: {str(e)}")
            self.logger.error(
                f"Detection failed: {str(e)}",
                exc_info=True
            )
            return []

def main():
    try:
        print("Initializing License Plate Detector...")
        detector = LicensePlateDetector()
        video_path = "public/videos/alprVideo.mp4"
        
        if not Path(video_path).exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        print(f"Opening video file: {video_path}")
        cap = cv2.VideoCapture(video_path)
        frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                print("End of video stream")
                break

            frame_count += 1
            print(f"\nProcessing frame #{frame_count}")
            boxes = detector.detect(frame)
            
            for (x, y, w, h) in boxes:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(
                    frame, "License Plate", (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2
                )

            cv2.imshow("License Plate Detection", frame)
            if cv2.waitKey(1) == ord('q'):
                print("User requested to quit")
                break
                
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        logging.error(f"Application error: {str(e)}", exc_info=True)
    finally:
        if 'cap' in locals():
            cap.release()
        cv2.destroyAllWindows()
        print("Application terminated")

if __name__ == "__main__":
    main()