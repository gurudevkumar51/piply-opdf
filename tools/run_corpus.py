"""Run the pipeline over a folder of real documents and report what happens.

    python tools/run_corpus.py [folder]

Writes _corpus_results.json. Use this to check a change against real
documents, not only the generated ones in the test suite.
"""

import sys
import json, time, traceback, warnings, logging
from pathlib import Path
from collections import Counter
warnings.filterwarnings("ignore"); logging.disable(logging.WARNING)

from piply_opdf import Document
from piply_opdf.core import PageContext
from piply_opdf.utils.pdf import iter_pages

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Gurudev\Desktop\Git_test\Sample PDFs")
OUT = Path("_corpus_out"); OUT.mkdir(exist_ok=True)
results = []

files = [f for f in sorted(SRC.iterdir())
         if f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg")]

for f in files:
    rec = {"file": f.name}
    t0 = time.perf_counter()
    try:
        d = Document(f, work_dir=OUT / f.stem)
        d.process_layout()
        rec.update({
            "ok": True,
            "secs": round(time.perf_counter() - t0, 1),
            "panels": len(d.panels), "tables": len(d.tables),
            "borderless": len(d.borderless_tables),
            "titles": len(d.titles), "headers": len(d.headers), "footers": len(d.footers),
            "key_values": len(d.key_values), "paragraphs": len(d.paragraphs),
            "sentences": len(d.sentences), "list_items": len(d.list_items),
            "graphics": len(d.graphics),
            "cells": sum(len(t.cells) for t in d.tables)
                     + sum(len(getattr(bt, "cells", [])) for bt in d.borderless_tables),
        })
        rec["graphic_types"] = dict(Counter(g["type"] for g in d.graphics))
        rec["panel_children"] = sum(len(p.get("children", [])) for p in d.panels)
        rec["total"] = sum(rec[k] for k in
            ("panels","tables","borderless","titles","headers","footers",
             "key_values","paragraphs","sentences","list_items","graphics"))
    except Exception as e:
        rec.update({"ok": False, "secs": round(time.perf_counter()-t0,1),
                    "error": f"{type(e).__name__}: {e}",
                    "trace": traceback.format_exc()[-600:]})
    results.append(rec)
    status = "ok " if rec.get("ok") else "ERR"
    print(f"{status} {f.name[:42]:42} {rec['secs']:6.1f}s  "
          f"{rec.get('total','-'):>5} components", flush=True)

Path("_corpus_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print("\nwrote _corpus_results.json")
