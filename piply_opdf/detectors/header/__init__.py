import fitz
from typing import List, Dict, Any

class HeaderDetector:
    """
    Detects header components (Page Headers, Document Titles, Company Info)
    in the top 10-20% of the page using PyMuPDF.
    """
    def __init__(self):
        # Top 15% of the page
        self.top_margin_ratio = 0.15
        
        # We output coordinates in 300 DPI to match the rest of the pipeline
        self.target_dpi = 300
        self.scale = self.target_dpi / 72.0

    def detect_headers(self, doc_path: str, page_num: int) -> List[Dict[str, Any]]:
        """
        Detects header text blocks.
        """
        doc = fitz.open(doc_path)
        page = doc[page_num - 1]
        
        # PyMuPDF coords
        h_72 = page.rect.height
        header_y_limit = h_72 * self.top_margin_ratio
        
        headers = []
        blocks = page.get_text("blocks")
        
        header_idx = 1
        for b in blocks:
            x0, y0, x1, y1, text, block_type, block_no = b
            if block_type == 0: # text block
                if y1 <= header_y_limit:
                    # Valid header
                    tx0 = int(x0 * self.scale)
                    ty0 = int(y0 * self.scale)
                    tx1 = int(x1 * self.scale)
                    ty1 = int(y1 * self.scale)
                    
                    headers.append({
                        "id": f"header_{header_idx:03d}",
                        "type": "header",
                        "page": page_num,
                        "bbox": [tx0, ty0, tx1 - tx0, ty1 - ty0],
                        "confidence": 0.95
                    })
                    header_idx += 1
                    
        return headers
