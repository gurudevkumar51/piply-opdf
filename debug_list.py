import os
from piply_opdf.detectors.list_item import ListItemDetector

detector = ListItemDetector()
path = r"uploads\2a030d19_sample11.pdf"
list_items = detector.detect_list_items(path, 1, [])

print("List items detected:", len(list_items))
for li in list_items:
    print(f"[{li['id']}] {li['text']}")
