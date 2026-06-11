import cv2
import numpy as np

def check(pdf_img):
    img = cv2.imread(pdf_img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 20))
    dilated = cv2.dilate(binary, kernel, iterations=1)
    
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (60, 1)))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 30)))
    
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for c in contours:
        x,y,w,h = cv2.boundingRect(c)
        if w < 50 or h < 50: continue
        
        h_thick = cv2.dilate(h_lines[y:y+h, x:x+w], np.ones((5, 5), np.uint8))
        v_thick = cv2.dilate(v_lines[y:y+h, x:x+w], np.ones((5, 5), np.uint8))
        intersections = cv2.bitwise_and(h_thick, v_thick)
        
        if cv2.countNonZero(intersections) == 0: continue
        
        tx, ty, tw, th = cv2.boundingRect(cv2.findNonZero(intersections))
        
        print(f"Table in {pdf_img}: Dilated width={w}, Intersection width={tw}, tx={tx}")

check('134242485947340351_piply/page_001.png')
try:
    check('sample_piply/page_001.png')
except:
    pass
