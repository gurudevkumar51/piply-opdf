import fitz
from typing import List, Dict, Any

class FooterDetector:
    """
    Detects footer components (Page Numbers, Disclaimers, Signatures)
    in the bottom 10-20% of the page using PyMuPDF.
    """
    def __init__(self):
        # Bottom 15% of the page
        self.bottom_margin_ratio = 0.85
        
        # We output coordinates in 300 DPI to match the rest of the pipeline
        self.target_dpi = 300
        self.scale = self.target_dpi / 72.0

    def detect_footers(self, doc_path: str, page_num: int) -> List[Dict[str, Any]]:
        """
        Detects footer text blocks.
        """
        doc = fitz.open(doc_path)
        page = doc[page_num - 1]
        
        # PyMuPDF coords
        h_72 = page.rect.height
        footer_y_limit = h_72 * self.bottom_margin_ratio
        
        footer_blocks = []
        blocks = page.get_text("blocks")
        for b in blocks:
            if b[6] == 0 and b[1] >= footer_y_limit:
                footer_blocks.append(b)
                
        footers = []
        if footer_blocks:
            x0 = min(b[0] for b in footer_blocks)
            y0 = min(b[1] for b in footer_blocks)
            x1 = max(b[2] for b in footer_blocks)
            y1 = max(b[3] for b in footer_blocks)
            text = "\n".join(b[4].strip() for b in footer_blocks)
            
            tx0 = int(x0 * self.scale)
            ty0 = int(y0 * self.scale)
            tx1 = int(x1 * self.scale)
            ty1 = int(y1 * self.scale)
            
            footers.append({
                "id": "footer_001",
                "type": "footer",
                "page": page_num,
                "bbox": [tx0, ty0, tx1 - tx0, ty1 - ty0],
                "text": text,
                "confidence": 0.95
            })
                    
        return footers
