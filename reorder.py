import sys

file_path = 'piply_opdf/document.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

stage2_start = -1
stage2_end = -1
stage3_start = -1
stage6_end = -1

for i, line in enumerate(lines):
    if '# --- STAGE 2: Borderless Table Detection (P2) ---' in line:
        stage2_start = i
    if '# --- STAGE 3: Header Detection (P3) ---' in line:
        stage3_start = i
        stage2_end = i
    if 'self.paragraphs.extend(paragraphs)' in line:
        stage6_end = i

if stage2_start == -1 or stage3_start == -1 or stage6_end == -1:
    print("Could not find markers")
    sys.exit(1)

stage2_lines = lines[stage2_start:stage2_end]

# Modify STAGE 2 to use all exclusions
new_stage2_lines = []
for line in stage2_lines:
    if 'borderless = borderless_detector.detect_tables(str(self.source_path), page_num, table_boxes)' in line:
        new_stage2_lines.append(line.replace('table_boxes', 'all_exclusions'))
    else:
        new_stage2_lines.append(line)

# Create the all_exclusions logic before STAGE 2
all_exclusions_logic = [
    '            # Build all exclusions for Borderless Table\n',
    '            from piply_opdf.models.grid import GridBoundingBox\n',
    '            all_exclusions = list(table_boxes)\n',
    '            for kv in key_values:\n',
    '                if kv.get("bbox"):\n',
    '                    x, y, w, h = kv["bbox"]\n',
    '                    all_exclusions.append(GridBoundingBox(x=x, y=y, width=w, height=h))\n',
    '            for p in paragraphs:\n',
    '                if p.get("bbox"):\n',
    '                    x, y, w, h = p["bbox"]\n',
    '                    all_exclusions.append(GridBoundingBox(x=x, y=y, width=w, height=h))\n',
    '\n'
]

# Reassemble
part1 = lines[:stage2_start]
part2 = lines[stage3_start:stage6_end+1]
part3 = all_exclusions_logic + new_stage2_lines
part4 = lines[stage6_end+1:]

# Fix table_bboxes for key-values and paragraphs since borderless is now at the end
# In part2, we need to change table_bboxes = self._component_bboxes(table_boxes, borderless)
# to table_bboxes = self._component_bboxes(table_boxes, [])
for i, line in enumerate(part2):
    if 'table_bboxes = self._component_bboxes(table_boxes, borderless)' in line:
        part2[i] = '            table_bboxes = self._component_bboxes(table_boxes, [])\n'

with open(file_path, 'w') as f:
    f.writelines(part1 + part2 + part3 + part4)
print('Success!')
