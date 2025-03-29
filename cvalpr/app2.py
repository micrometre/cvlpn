import cv2
import pytesseract
import matplotlib.pyplot as plt

# Load image
image = cv2.imread("test.jpg")
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Edge detection and contour finding
edges = cv2.Canny(gray, 30, 200)
contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

plate_text = None
plate_roi = None

# Contour filtering
for contour in contours:
    x, y, w, h = cv2.boundingRect(contour)
    aspect_ratio = w / float(h)
    
    # Basic license plate aspect ratio check
    if 2.0 < aspect_ratio < 6.0 and 100 < w < 500 and 50 < h < 200:
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
        
        # Extract the potential license plate region
        plate_roi = gray[y:y+h, x:x+w]
        
        # Apply some preprocessing for better OCR results
        plate_roi = cv2.threshold(plate_roi, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        plate_roi = cv2.medianBlur(plate_roi, 3)
        
        # Use Tesseract to extract text
        config = '--psm 11 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        plate_text = pytesseract.image_to_string(plate_roi, config=config).strip()
        
        # Print and display the result
        print(f"Detected plate: {plate_text}")
        cv2.putText(image, plate_text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

# Display the result
plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
plt.show()