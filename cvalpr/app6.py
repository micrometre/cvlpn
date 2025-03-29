import cv2
import numpy as np
import pytesseract
import os
import csv
from glob import glob

# Initialize MSER detector
mser = cv2.MSER_create()
tess_config = '--psm 11 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

# Setup folders
images_folder = "images"
output_folder = "results"
os.makedirs(output_folder, exist_ok=True)

# CSV file setup
csv_file = os.path.join(output_folder, "plates.csv")
with open(csv_file, mode='w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["Image", "License Plate"])  # Header

for img_path in glob(os.path.join(images_folder, "*.jpg")):
    image = cv2.imread(img_path)
    if image is None:
        print(f"⚠️ Could not read {img_path}")
        continue

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    regions, _ = mser.detectRegions(gray)
    plate_text = None

    for region in regions:
        x, y, w, h = cv2.boundingRect(region.reshape(-1, 1, 2))
        aspect_ratio = w / h
        
        if 2.0 < aspect_ratio < 6.0 and 50 < w < 500 and 20 < h < 150:
            plate_roi = gray[y:y+h, x:x+w]
            plate_roi = cv2.threshold(plate_roi, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            plate_roi = cv2.medianBlur(plate_roi, 3)
            
            plate_text = pytesseract.image_to_string(plate_roi, config=tess_config).strip()
            if plate_text:
                cv2.rectangle(image, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(image, plate_text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                break

    # Save processed image
    filename = os.path.basename(img_path)
    output_path = os.path.join(output_folder, f"processed_{filename}")
    cv2.imwrite(output_path, image)

    # Write to CSV
    with open(csv_file, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([filename, plate_text if plate_text else "Not detected"])

    print(f"Processed: {filename} → Plate: {plate_text if plate_text else 'Not detected'}")

print(f"\n✅ Results saved to {csv_file}")