import cv2
import numpy as np
import pytesseract
from matplotlib import pyplot as plt

# Load image
image = cv2.imread("test2.jpg")
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Initialize MSER detector
mser = cv2.MSER_create()
regions, _ = mser.detectRegions(gray)

# Prepare a mask to draw detected regions
mask = np.zeros_like(gray)
plate_text = "No plate detected"  # Default text

for region in regions:
    x, y, w, h = cv2.boundingRect(region.reshape(-1, 1, 2))
    aspect_ratio = w / h
    
    # Filter based on aspect ratio and size (adjust as needed)
    if 2.0 < aspect_ratio < 6.0 and 50 < w < 500 and 20 < h < 150:
        # Draw rectangle around potential plate
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
        
        # Extract the plate region
        plate_roi = gray[y:y+h, x:x+w]
        
        # Preprocess for better OCR (binarization + blur)
        plate_roi = cv2.threshold(plate_roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        plate_roi = cv2.medianBlur(plate_roi, 3)
        
        # Use Tesseract to extract text
        config = '--psm 11 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        plate_text = pytesseract.image_to_string(plate_roi, config=config).strip()
        
        # Print the detected plate number
        print(f"Detected Plate: {plate_text}")
        
        # Overlay text on the image
        cv2.putText(image, plate_text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

# Display the result
plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
plt.title(f"Detected Plate: {plate_text}")
plt.axis('off')
plt.show()