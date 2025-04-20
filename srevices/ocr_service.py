import numpy as np  # Add this line at the top of the file
import pytesseract
import cv2
from ..config import TESSERACT_CONFIG

class OCRService:
    """Handles license plate text recognition"""
    
    @staticmethod
    def extract_text(image: np.ndarray) -> str:
        """Perform OCR on license plate image"""
        processed = OCRService._preprocess_image(image)
        text = pytesseract.image_to_string(processed, config=TESSERACT_CONFIG)
        return text.strip()
    
    @staticmethod
    def _preprocess_image(image: np.ndarray) -> np.ndarray:
        """Enhance image for better OCR results"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        return cv2.medianBlur(thresh, 3)