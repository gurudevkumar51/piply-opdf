import cv2
import numpy as np
from piply_opdf.utils.pdf import pdf_page_to_image
from piply_opdf.phases.phase2_enhance import DocumentEnhancer

img = pdf_page_to_image('sample.pdf', page_index=0, dpi=300)
enhancer = DocumentEnhancer()

# Apply enhancement
img_denoised = enhancer.denoise(img)
img_contrast = enhancer.enhance_contrast(img_denoised)

gray = cv2.cvtColor(img_contrast, cv2.COLOR_BGR2GRAY)
binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 10)

h, w = gray.shape
v_kernel_h = max(40, h // 60)
v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_h)))

v_proj = v_lines.sum(axis=0)
pixels = np.where(v_proj > (h * 255 * 0.10))[0]

print("Vertical line pixels in enhanced image:")
print(pixels[:100])
