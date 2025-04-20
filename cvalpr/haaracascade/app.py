import cv2
import numpy as np
import os
import pytesseract
import json
import csv
from datetime import datetime

# Create directory to save plates if it doesn't exist
if not os.path.exists('detected_plates'):
    os.makedirs('detected_plates')

# Initialize lists to store plate data
plate_records = []  # Renamed from plate_data

carPlatesCascade = cv2.CascadeClassifier('haarcascade_russian_plate_number.xml')

cap = cv2.VideoCapture('public/videos/alprVideo.mp4')

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 80)

if (cap.isOpened()==False):
    print('Error Reading video')

count = 0  # Counter for saving plates

def preprocess_plate(plate):
    plate = cv2.resize(plate, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)
    # Sharpen
    kernel = np.array([[0, -1, 0], [-1, 5,-1], [0, -1, 0]])
    sharp = cv2.filter2D(gray, -1, kernel)
    # Otsu threshold
    _, thresh = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Morphology
    kernel = np.ones((3,3), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    thresh = cv2.copyMakeBorder(thresh, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=(255,255,255))
    thresh = cv2.fastNlMeansDenoising(thresh)
    return thresh

def validate_plate(text):
    # Remove any non-alphanumeric characters
    text = ''.join(c for c in text if c.isalnum())
    
    # Check minimum length
    if len(text) < 5 or len(text) > 8:
        return False
    
    # Check if contains both letters and numbers
    has_letters = any(c.isalpha() for c in text)
    has_numbers = any(c.isdigit() for c in text)
    
    return has_letters and has_numbers

while True:
    ret,frame = cap.read()
    if ret == True:
        gray = cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        car_plates = carPlatesCascade.detectMultiScale(
            gray,
            scaleFactor=1.1,  # Smaller scale factor for more detections
            minNeighbors=4,   # Reduced to detect more potential plates
            minSize=(60,20),  # Minimum size of a license plate
            maxSize=(300,100) # Maximum size of a license plate
        )

        for (x, y, w, h) in car_plates:
            aspect_ratio = w / float(h)
            if aspect_ratio < 2 or aspect_ratio > 6:
                continue  # Skip unlikely plate shapes

            # Draw rectangle around plate
            cv2.rectangle(frame,(x,y),(x+w,y+h),(255,0,0),2)
            
            # Extract plate
            plate = frame[y: y+h, x:x+w]
            
            # Preprocess the plate for OCR
            processed_plate = preprocess_plate(plate)
            
            # Use image_to_data to get confidence scores
            ocr_data = pytesseract.image_to_data(
                processed_plate, 
                output_type=pytesseract.Output.DICT,
                config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
            )
            confidences = [int(conf) for conf in ocr_data['conf'] if conf != '-1']
            if confidences and sum(confidences)/len(confidences) > 60:  # Only accept if average confidence > 60%
                text = ''.join([word for word in ocr_data['text'] if word.strip()])
            
                if text and validate_plate(text):
                    if not any(rec['plate_number'] == text for rec in plate_records):
                        plate_info = {
                            "plate_number": text,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "image_path": f'detected_plates/plate_{count}.jpg'
                        }
                        plate_records.append(plate_info)
                        print(f"Detected plate {count}: {text}")
            
            # Save the original plate image
            cv2.imwrite(f'detected_plates/plate_{count}.jpg', plate)
            count += 1
            
            # Blur the plate in the video display
            plate_blur = cv2.blur(plate,ksize=(20,20))
            frame[y:y+h, x:x+w] = plate_blur

        cv2.imshow('Video',frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    else:
        break

# Save to JSON
with open('detected_plates.json', 'w') as f:
    json.dump(plate_records, f, indent=4)

# Save to CSV
with open('detected_plates.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["plate_number", "timestamp", "image_path"])
    writer.writeheader()
    writer.writerows(plate_records)

cap.release()
cv2.destroyAllWindows()
print(f"Total plates detected and saved: {count}")
print(f"Results saved to detected_plates.json and detected_plates.csv")