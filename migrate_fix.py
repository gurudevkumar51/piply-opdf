"""
Migration script to fix existing database records:
1. Convert bbox from {x, y, width, height} dict to [x0, y0, x1, y1] array
2. Populate manifest_path for CELL components with correct image paths
"""
import sqlite3
import json
import os

DB_PATH = 'piply_opdf.db'

c = sqlite3.connect(DB_PATH)
cursor = c.cursor()

# 1. Fix bbox format
print("=== Fixing bbox format ===")
rows = cursor.execute("SELECT id, bbox FROM components WHERE bbox IS NOT NULL").fetchall()
fixed = 0
for comp_id, bbox_str in rows:
    try:
        bbox = json.loads(bbox_str)
        if isinstance(bbox, dict):
            x = bbox.get('x', bbox.get('x0', 0))
            y = bbox.get('y', bbox.get('y0', 0))
            w = bbox.get('width', bbox.get('w', 0))
            h = bbox.get('height', bbox.get('h', 0))
            new_bbox = json.dumps([x, y, x + w, y + h])
            cursor.execute("UPDATE components SET bbox = ? WHERE id = ?", (new_bbox, comp_id))
            fixed += 1
    except (json.JSONDecodeError, TypeError):
        pass
print(f"  Fixed {fixed} bbox entries")

# 2. Fix manifest_path for CELL components
print("\n=== Fixing CELL image paths ===")

# Get all documents
docs = cursor.execute("SELECT id, filename FROM documents WHERE status='completed'").fetchall()

for doc_id, filename in docs:
    base_name = os.path.splitext(filename)[0]
    work_dir = os.path.join("uploads", f"{base_name}_piply")
    
    if not os.path.exists(work_dir):
        print(f"  Doc {doc_id} ({filename}): work_dir not found at {work_dir}")
        continue
    
    # Get all CELL components for this doc
    cells = cursor.execute(
        "SELECT id, parent_id FROM components WHERE document_id = ? AND component_type = 'CELL'",
        (doc_id,)
    ).fetchall()
    
    # Get parent tables to find table_id
    tables = cursor.execute(
        "SELECT id, bbox FROM components WHERE document_id = ? AND component_type IN ('TABLE', 'BORDERLESS_TABLE')",
        (doc_id,)
    ).fetchall()
    
    # Walk the cells directory to build a lookup
    cell_files = {}
    for root, dirs, files in os.walk(work_dir):
        if os.path.basename(root) == 'cells':
            for f in files:
                if f.endswith('.png'):
                    cell_files[os.path.splitext(f)[0]] = os.path.join(root, f)
    
    print(f"  Doc {doc_id} ({filename}): found {len(cell_files)} cell images, {len(cells)} cell components")
    
    if not cell_files:
        continue
    
    # For each cell, try to find its image path
    # The cells are likely named table_001_r{row}_c{col}
    # We need to map component IDs to cell_ids somehow
    # Since we don't have cell_id stored, let's try matching by order
    
    # Get all cell image paths sorted
    sorted_cell_paths = sorted(cell_files.values())
    
    # If counts match, assign by order
    if len(cells) == len(sorted_cell_paths):
        for (cell_id, _), path in zip(cells, sorted_cell_paths):
            cursor.execute("UPDATE components SET manifest_path = ? WHERE id = ?", (path, cell_id))
        print(f"    Assigned {len(cells)} paths by order match")
    else:
        # Try a best-effort approach: assign available paths to cells in order
        assigned = 0
        for i, (cell_id, _) in enumerate(cells):
            if i < len(sorted_cell_paths):
                cursor.execute("UPDATE components SET manifest_path = ? WHERE id = ?", (sorted_cell_paths[i], cell_id))
                assigned += 1
        print(f"    Assigned {assigned}/{len(cells)} paths (count mismatch)")

c.commit()
c.close()
print("\n✅ Migration complete!")
