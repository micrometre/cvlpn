import cv2
import numpy as np
import pytesseract
import os
from glob import glob

# Initialize MSER detector
mser = cv2.MSER_create()

# Tesseract config (optimized for license plates)
tess_config = '--psm 11 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

# Process all JPG files in the 'images' folder
images_folder = "images"
output_folder = "results"
os.makedirs(output_folder, exist_ok=True)

for img_path in glob(os.path.join(images_folder, "*.jpg")):
    # Read image
    image = cv2.imread(img_path)
    if image is None:
        print(f"⚠️ Could not read {img_path}")
        continue
    
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Detect MSER regions
    regions, _ = mser.detectRegions(gray)
    
    plate_text = None
    plate_roi = None
    
    for region in regions:
        x, y, w, h = cv2.boundingRect(region.reshape(-1, 1, 2))
        aspect_ratio = w / h
        
        # License plate filters (adjust as needed)
        if 2.0 < aspect_ratio < 6.0 and 50 < w < 500 and 20 < h < 150:
            # Extract ROI and preprocess
            plate_roi = gray[y:y+h, x:x+w]
            plate_roi = cv2.threshold(plate_roi, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            plate_roi = cv2.medianBlur(plate_roi, 3)
            
            # OCR
            plate_text = pytesseract.image_to_string(plate_roi, config=tess_config).strip()
            
            if plate_text:  # Only draw if text was detected
                cv2.rectangle(image, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(image, plate_text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                break  # Stop after first valid detection
    
    # Save and print results
    filename = os.path.basename(img_path)
    output_path = os.path.join(output_folder, f"processed_{filename}")
    cv2.imwrite(output_path, image)
    
    print(f"📄 {filename} → Plate: {plate_text if plate_text else 'Not detected'}")
    print(f"   Saved to: {output_path}")