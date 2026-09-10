import sqlite3

conn = sqlite3.connect("piply_opdf.db")
cur = conn.cursor()
lines = []
cur.execute("""
  select c.component_type, p.component_type, count(*)
  from components c left join components p on c.parent_id = p.id
  group by c.component_type, p.component_type
""")
for child, parent, n in cur.fetchall():
    lines.append(f"{child:12} -> parent {str(parent):12} x{n}")
cur.execute("select id, component_type, parent_id, manifest_path from components where component_type='CELL' limit 3")
lines.append("")
for r in cur.fetchall():
    lines.append(str(r))
conn.close()
open("_cellparents.txt", "w", encoding="utf-8").write("\n".join(lines))
