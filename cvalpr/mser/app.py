# Import required libraries
import cv2  # OpenCV library for image processing
import matplotlib.pyplot as plt  # Library for image display

# Read the input image file
image = cv2.imread("test2.jpg")
# Convert the image to grayscale (required for edge detection)
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
# Apply Canny edge detection
# Parameters: image, lower threshold=30, upper threshold=200
edges = cv2.Canny(gray, 49, 100)
# Find contours in the edge image
# RETR_TREE: retrieves all contours and reconstructs a full hierarchy of nested contours
# CHAIN_APPROX_SIMPLE: compresses horizontal, vertical, and diagonal segments
contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

# Iterate through each contour to find potential license plates
for contour in contours:
    # Get the bounding rectangle coordinates for the contour
    x, y, w, h = cv2.boundingRect(contour)
    # Calculate aspect ratio (width/height)
    aspect_ratio = w / float(h)
    # Filter contours based on license plate characteristics:
    # - Aspect ratio between 2.0 and 6.0 (typical for license plates)
    # - Width between 100 and 500 pixels
    # - Height between 50 and 200 pixels
    if 2.0 < aspect_ratio < 6.0 and 200 < w < 500 and 50 < h < 200:
        # Draw a green rectangle around potential license plates
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)

# Convert image from BGR to RGB color space (OpenCV uses BGR, matplotlib uses RGB)
plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
# Display the result
plt.show()