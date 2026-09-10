let currentDocumentId = null;
let currentDocument = null;
let manifestData = null;
let currentPage = 1;

const docSelector = document.getElementById('doc-selector');
const contentArea = document.getElementById('reconstructed-content');
const pdfImage = document.getElementById('pdf-image');
const noDocMsg = document.getElementById('no-doc-msg');

async function loadDocuments() {
    try {
        const res = await fetch('/documents');
        const docs = await res.json();
        
        docs.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.id;
            opt.textContent = `ID ${d.id}: ${d.filename} (${d.status})`;
            docSelector.appendChild(opt);
        });
    } catch (e) {
        console.error("Failed to load documents", e);
    }
}

window.selectDocument = async function(docId) {
    if (!docId) return;
    currentDocumentId = docId;
    
    contentArea.innerHTML = '<div class="empty-state">Loading manifest data…</div>';

    try {
        const resDoc = await fetch(`/documents/${docId}`);
        currentDocument = await resDoc.json();

        loadPageImage(currentPage);

        const res = await fetch(`/download-manifest/${docId}`);
        if (!res.ok) {
            contentArea.innerHTML = '<div class="empty-state" style="color: var(--bad);">Manifest not generated. Please process the document first.</div>';
            return;
        }
        manifestData = await res.json();

        renderManifest();
    } catch (e) {
        console.error(e);
        contentArea.innerHTML = '<div class="empty-state" style="color: var(--bad);">Error loading data.</div>';
    }
}

function loadPageImage(page) {
    if (!currentDocument) return;
    const fn = currentDocument.filename.replace(/\.[^/.]+$/, "");
    const pageStr = String(page).padStart(3, '0');
    pdfImage.src = `/uploads/${fn}_piply/pages/page_${pageStr}.png`;
    pdfImage.style.display = 'block';
    noDocMsg.style.display = 'none';
    document.getElementById('current-page').textContent = page;
}

window.prevPage = function() {
    if (currentPage > 1) {
        currentPage--;
        loadPageImage(currentPage);
    }
}

window.nextPage = function() {
    currentPage++;
    loadPageImage(currentPage);
}

function renderManifest() {
    if (!manifestData) return;
    
    let allComponents = [];
    
    if (manifestData.tables) manifestData.tables.forEach(t => allComponents.push({...t, _category: 'Table'}));
    if (manifestData.borderless_tables) manifestData.borderless_tables.forEach(t => allComponents.push({...t, _category: 'Borderless Table'}));
    if (manifestData.key_values) manifestData.key_values.forEach(kv => allComponents.push({...kv, _category: 'Key-Value'}));
    if (manifestData.paragraphs) manifestData.paragraphs.forEach(p => allComponents.push({...p, _category: 'Paragraph'}));
    if (manifestData.sentences) manifestData.sentences.forEach(s => allComponents.push({...s, _category: 'Sentence'}));
    if (manifestData.list_items) manifestData.list_items.forEach(li => allComponents.push({...li, _category: 'ListItem'}));
    if (manifestData.headers) manifestData.headers.forEach(h => allComponents.push({...h, _category: 'Header'}));
    if (manifestData.footers) manifestData.footers.forEach(f => allComponents.push({...f, _category: 'Footer'}));
    
    if (allComponents.length === 0) {
        contentArea.innerHTML = '<div class="empty-state">No layout structures found.</div>';
        return;
    }
    
    const parseBBox = (bbox) => {
        if (!bbox) return null;
        if (Array.isArray(bbox) && bbox.length >= 4) return bbox;
        if (bbox.y !== undefined) return [bbox.x || 0, bbox.y, (bbox.x||0)+100, bbox.y+20];
        return null;
    };

    const renderTableGroup = (t, styleStr) => {
        let out = `<div style="${styleStr}" class="overflow-hidden">`;
        out += `<table class="reconstructed-table" style="margin-bottom: 0;">`;
        
        const allCells = t.children ? t.children.filter(c => c.type === 'CELL') : [];
        const rowMap = {};
        allCells.forEach(c => {
            let rIdx = 0;
            if (c.manifest_path) {
                const match = c.manifest_path.match(/_r(\d+)_/);
                if (match) rIdx = parseInt(match[1], 10);
            }
            if (c.parent_type === 'ROW' && c.row_idx !== undefined) rIdx = c.row_idx;
            if (!rowMap[rIdx]) rowMap[rIdx] = [];
            rowMap[rIdx].push(c);
        });
        
        const rowIndices = Object.keys(rowMap).map(Number).sort((a, b) => a - b);
        
        if (rowIndices.length === 0) {
             out += `<tr><td class="text-muted-2 italic text-center">No cells detected.</td></tr>`;
        } else {
             rowIndices.forEach((rIdx, i) => {
                 out += `<tr>`;
                 let cells = rowMap[rIdx];
                 cells.sort((a, b) => {
                     const ma = a.manifest_path ? a.manifest_path.match(/_c(\d+)\\.png/) : null;
                     const mb = b.manifest_path ? b.manifest_path.match(/_c(\d+)\\.png/) : null;
                     return (ma ? parseInt(ma[1], 10) : 0) - (mb ? parseInt(mb[1], 10) : 0);
                 });
                 cells.forEach(cell => {
                     let text = cell.ocr ? cell.ocr.text : '';
                     if (!text || text.trim() === '') text = '&nbsp;';
                     
                     let confClass = '';
                     if (cell.ocr && cell.ocr.confidence < 0.8 && !cell.ocr.is_human) confClass = 'cell-low-conf';
                     else if (cell.ocr && cell.ocr.confidence < 0.95 && !cell.ocr.is_human) confClass = 'cell-med-conf';

                     out += `<td class="${confClass}">${text}</td>`;
                 });
                 out += `</tr>`;
             });
        }
        
        out += `</table></div>`;
        return out;
    };
    
    let html = ``;
    const pagesMap = {};
    allComponents.forEach(c => {
        if (!pagesMap[c.page]) pagesMap[c.page] = [];
        pagesMap[c.page].push(c);
    });
    
    const pageIndices = Object.keys(pagesMap).map(Number).sort((a, b) => a - b);

    // Reading order, laid out as a document rather than pinned to the original
    // coordinates.
    //
    // Absolute positioning was setting left/top/width from the bbox but never a
    // height, and rendering at a fixed font size regardless of how much the
    // page had been scaled down. Text taller than its original region then ran
    // straight over whatever sat below it, so every block collided. Flow makes
    // that impossible, and matches the decision recorded for HTML output: a
    // semantic, searchable document.
    const readingOrder = (a, b) => {
        const ba = parseBBox(a.bbox), bb = parseBBox(b.bbox);
        if (!ba || !bb) return 0;
        // Same visual line if their vertical spans overlap; then left to right.
        const overlap = Math.min(ba[3], bb[3]) - Math.max(ba[1], bb[1]);
        const shorter = Math.min(ba[3] - ba[1], bb[3] - bb[1]) || 1;
        if (overlap > shorter * 0.5) return ba[0] - bb[0];
        return ba[1] - bb[1];
    };

    const textOf = (comp) => {
        if (comp.words && comp.words.length) {
            const words = comp.words.map(w => (w.ocr ? w.ocr.text : w.text)).filter(Boolean);
            if (words.length) return words.join(" ");
        }
        return comp.ocr ? comp.ocr.text : (comp.text || "");
    };

    const confidenceClass = (comp) => {
        if (!comp.ocr || comp.ocr.is_human) return comp.ocr && comp.ocr.is_human ? "rc-human" : "";
        if (comp.ocr.confidence < 0.8) return "rc-low";
        if (comp.ocr.confidence < 0.95) return "rc-medium";
        return "";
    };

    pageIndices.forEach(p => {
        const comps = [...pagesMap[p]].sort(readingOrder);

        html += `<article class="rc-page paper">`;
        html += `<div class="rc-page-label label-micro">Page ${p}</div>`;

        comps.forEach(comp => {
            const cls = confidenceClass(comp);

            if (comp._category === "Table" || comp._category === "Borderless Table") {
                html += renderTableGroup(comp, "");
                return;
            }

            const text = textOf(comp);
            if (!text) return;                       // nothing read yet: skip

            if (comp._category === "Header") {
                html += `<header class="rc-header ${cls}">${text}</header>`;
            } else if (comp._category === "Footer") {
                html += `<footer class="rc-footer ${cls}">${text}</footer>`;
            } else if (comp._category === "Title") {
                html += `<h2 class="rc-title ${cls}">${text}</h2>`;
            } else if (comp._category === "Key-Value") {
                html += `<div class="rc-kv ${cls}">${text}</div>`;
            } else if (comp._category === "ListItem") {
                html += `<li class="rc-list-item ${cls}">${text}</li>`;
            } else {
                html += `<p class="rc-text ${cls}">${text}</p>`;
            }
        });

        html += `</article>`;
    });

    contentArea.innerHTML = html;
}

window.downloadJSON = function() {
    if (!currentDocumentId) return;
    window.open(`/download-manifest/${currentDocumentId}`, '_blank');
}

window.downloadCSV = function() {
    if (!manifestData) return;
    
    let csvContent = "";
    
    const allTables = (manifestData.tables || []).concat(manifestData.borderless_tables || []);
    
    allTables.forEach((t, i) => {
        csvContent += `TABLE ${i+1} (Page ${t.page})\n`;
        
        // Extract all cells
        const allCells = t.children ? t.children.filter(c => c.type === 'CELL') : [];
        if (allCells.length === 0) {
            csvContent += "No cells detected\n\n";
            return;
        }

        const rowMap = {};
        allCells.forEach(c => {
            let rIdx = 0;
            if (c.manifest_path) {
                const match = c.manifest_path.match(/_r(\d+)_/);
                if (match) rIdx = parseInt(match[1], 10);
            }
            if (c.parent_type === 'ROW' && c.row_idx !== undefined) rIdx = c.row_idx;
            
            if (!rowMap[rIdx]) rowMap[rIdx] = [];
            rowMap[rIdx].push(c);
        });
        
        const rowIndices = Object.keys(rowMap).map(Number).sort((a, b) => a - b);
        
        rowIndices.forEach(rIdx => {
            let cells = rowMap[rIdx];
            cells.sort((a, b) => {
                const ma = a.manifest_path ? a.manifest_path.match(/_c(\d+)\.png/) : null;
                const mb = b.manifest_path ? b.manifest_path.match(/_c(\d+)\.png/) : null;
                const ca = ma ? parseInt(ma[1], 10) : 0;
                const cb = mb ? parseInt(mb[1], 10) : 0;
                return ca - cb;
            });
            
            const rowData = cells.map(c => {
                let text = c.ocr ? c.ocr.text : '';
                if (text.includes(',') || text.includes('\n') || text.includes('"')) {
                    text = '"' + text.replace(/"/g, '""') + '"';
                }
                return text;
            });
            csvContent += rowData.join(",") + "\n";
        });
        csvContent += "\n";
    });
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `reconstructed_${currentDocumentId}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

window.downloadPDF = function() {
    if (!manifestData) return;
    const element = document.getElementById('reconstructed-content');
    
    // Temporarily apply styles for PDF generation to prevent right-side cropping
    const originalWidth = element.style.width;
    const originalMaxWidth = element.style.maxWidth;
    element.style.width = '1200px';
    element.style.maxWidth = '1200px';
    element.classList.add('text-xs');
    
    const opt = {
      margin:       0.3,
      filename:     `reconstructed_${currentDocumentId}.pdf`,
      image:        { type: 'jpeg', quality: 0.98 },
      html2canvas:  { scale: 2, windowWidth: 1200 },
      jsPDF:        { unit: 'in', format: 'letter', orientation: 'landscape' }
    };
    
    html2pdf().set(opt).from(element).save().then(() => {
        // Restore original styles after export
        element.style.width = originalWidth;
        element.style.maxWidth = originalMaxWidth;
        element.classList.remove('text-xs');
    });
}

// Init
loadDocuments();
