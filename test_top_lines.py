import cv2
import numpy as np

img = cv2.imread("test_grid_mask.png", cv2.IMREAD_GRAYSCALE)
h, w = img.shape

# Look at top 20% of the image
top_part = img[0:int(h*0.2), :]

contours, _ = cv2.findContours(top_part, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

print(f"Total contours in top 20%: {len(contours)}")
for i, c in enumerate(contours):
    x, y, w_c, h_c = cv2.boundingRect(c)
    if w_c > 50 and h_c > 10:
        print(f"Contour {i}: x={x}, y={y}, w={w_c}, h={h_c}")
