import cv2
import numpy as np
import pytesseract
import json
import os
from datetime import datetime

def load_yolo():
    """Load YOLO model and configuration"""
    net = cv2.dnn.readNet("yolov4-tiny.weights", "yolov4-tiny.cfg")
    classes = []
    with open("coco.names", "r") as f:
        classes = [line.strip() for line in f.readlines()]
    layers_names = net.getLayerNames()
    output_layers = [layers_names[i-1] for i in net.getUnconnectedOutLayers()]
    return net, classes, output_layers

def load_plate_cascade():
    """Load license plate cascade classifier"""
    plate_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_russian_plate_number.xml')
    return plate_cascade

def detect_objects(img, net, output_layers):
    """Detect objects in the image using YOLO"""
    height, width, _ = img.shape
    blob = cv2.dnn.blobFromImage(img, 0.00392, (416, 416), (0, 0, 0), True, crop=False)
    
    net.setInput(blob)
    outs = net.forward(output_layers)
    
    class_ids = []
    confidences = []
    boxes = []
    
    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > 0.5:
                # Object detected
                center_x = int(detection[0] * width)
                center_y = int(detection[1] * height)
                w = int(detection[2] * width)
                h = int(detection[3] * height)

                # Rectangle coordinates
                x = int(center_x - w / 2)
                y = int(center_y - h / 2)

                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
                class_ids.append(class_id)
    
    return boxes, confidences, class_ids

def detect_plates(img, plate_cascade):
    """Detect license plates in the image"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    plates = plate_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    return plates

def draw_labels(boxes, confidences, class_ids, classes, img):
    """Draw bounding boxes and labels on the image"""
    indexes = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
    font = cv2.FONT_HERSHEY_PLAIN
    for i in range(len(boxes)):
        if i in indexes:
            x, y, w, h = boxes[i]
            label = str(classes[class_ids[i]])
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(img, label, (x, y + 30), font, 2, (0, 255, 0), 2)

def enhance_plate_image(plate_roi):
    """Enhance plate image for better OCR"""
    gray = cv2.cvtColor(plate_roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5,5), 0)
    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    return opening

def process_plate(img, x, y, w, h):
    """Process license plate and extract text"""
    # Convert numpy int32 to regular Python int
    x = int(x)
    y = int(y)
    w = int(w)
    h = int(h)
    
    plate_roi = img[y:y+h, x:x+w]
    enhanced_roi = enhance_plate_image(plate_roi)
    text = pytesseract.image_to_string(enhanced_roi, config='--psm 7')
    
    # Save plate image
    filename = f"plate_{x}_{y}.jpg"
    cv2.imwrite(filename, plate_roi)
    
    # Extract text
    text = text.strip()
    
    return {
        "plate_text": text,
        "coordinates": {
            "x": x,
            "y": y,
            "width": w,
            "height": h
        },
        "image_file": filename,
        "timestamp": datetime.now().isoformat()
    }

def draw_plates(img, plates):
    """Draw rectangles around detected license plates and save data"""
    plates_data = []
    
    for (x, y, w, h) in plates:
        # Draw rectangle and label
        cv2.rectangle(img, (x, y), (x+w, y+h), (0, 0, 255), 2)
        cv2.putText(img, "License Plate", (x, y-10), cv2.FONT_HERSHEY_PLAIN, 1, (0, 0, 255), 2)
        
        # Process plate and collect data
        plate_info = process_plate(img, x, y, w, h)
        plates_data.append(plate_info)
    
    # Save to JSON file
    with open("detected_plates.json", "w") as f:
        json.dump({
            "plates": plates_data,
            "total_plates": len(plates_data)
        }, f, indent=4)

def main():
    # Load YOLO model
    net, classes, output_layers = load_yolo()
    
    # Load plate cascade classifier
    plate_cascade = load_plate_cascade()
    
    # Load image
    img = cv2.imread("test_image.jpg")
    img = cv2.resize(img, None, fx=0.4, fy=0.4)
    
    # Detect general objects
    boxes, confidences, class_ids = detect_objects(img, net, output_layers)
    draw_labels(boxes, confidences, class_ids, classes, img)
    
    # Detect license plates
    plates = detect_plates(img, plate_cascade)
    draw_plates(img, plates)
    
    # Show image
    cv2.imshow("Image", img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()