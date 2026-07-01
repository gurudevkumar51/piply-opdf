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
        
        header_blocks = []
        blocks = page.get_text("blocks")
        for b in blocks:
            if b[6] == 0 and b[3] <= header_y_limit:
                header_blocks.append(b)
                
        headers = []
        if header_blocks:
            x0 = min(b[0] for b in header_blocks)
            y0 = min(b[1] for b in header_blocks)
            x1 = max(b[2] for b in header_blocks)
            y1 = max(b[3] for b in header_blocks)
            text = "\n".join(b[4].strip() for b in header_blocks)
            
            tx0 = int(x0 * self.scale)
            ty0 = int(y0 * self.scale)
            tx1 = int(x1 * self.scale)
            ty1 = int(y1 * self.scale)
            
            headers.append({
                "id": "header_001",
                "type": "header",
                "page": page_num,
                "bbox": [tx0, ty0, tx1 - tx0, ty1 - ty0],
                "text": text,
                "confidence": 0.95
            })
                    
        return headers
