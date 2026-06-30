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
    
    contentArea.innerHTML = '<div class="text-center mt-20 text-gray-500">Loading manifest data...</div>';
    
    try {
        const resDoc = await fetch(`/documents/${docId}`);
        currentDocument = await resDoc.json();
        
        loadPageImage(currentPage);
        
        const res = await fetch(`/download-manifest/${docId}`);
        if (!res.ok) {
            contentArea.innerHTML = '<div class="text-center mt-20 text-red-500">Manifest not generated. Please process document.</div>';
            return;
        }
        manifestData = await res.json();
        
        renderManifest();
    } catch (e) {
        console.error(e);
        contentArea.innerHTML = '<div class="text-center mt-20 text-red-500">Error loading data.</div>';
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
    
    let html = ``;
    
    // Helper to render a generic table
    const renderTableGroup = (tables, title) => {
        if (!tables || tables.length === 0) return '';
        let out = `<h2 class="text-lg font-bold text-gray-800 mb-4 mt-6 border-b pb-2">${title}</h2>`;
        
        tables.forEach(t => {
            out += `<div class="mb-8">`;
            out += `<div class="text-sm text-gray-500 mb-2">Page ${t.page}</div>`;
            out += `<table class="reconstructed-table">`;
            
            // Extract all cells
            const allCells = t.children.filter(c => c.type === 'CELL');
            
            const rowMap = {};
            allCells.forEach(c => {
                let rIdx = 0;
                if (c.manifest_path) {
                    const match = c.manifest_path.match(/_r(\d+)_/);
                    if (match) rIdx = parseInt(match[1], 10);
                }
                // If it is already in a ROW child due to DB hierarchy (unlikely currently but future-proof)
                if (c.parent_type === 'ROW' && c.row_idx !== undefined) rIdx = c.row_idx;
                
                if (!rowMap[rIdx]) rowMap[rIdx] = [];
                rowMap[rIdx].push(c);
            });
            
            const rowIndices = Object.keys(rowMap).map(Number).sort((a, b) => a - b);
            
            if (rowIndices.length === 0) {
                 out += `<tr><td class="text-gray-400 italic text-sm py-2">No cells detected.</td></tr>`;
            } else {
                 rowIndices.forEach((rIdx, i) => {
                     const isHeader = (i === 0);
                     out += `<tr>`;
                     let cells = rowMap[rIdx];
                     
                     // Sort cells by column index
                     cells.sort((a, b) => {
                         const ma = a.manifest_path ? a.manifest_path.match(/_c(\d+)\.png/) : null;
                         const mb = b.manifest_path ? b.manifest_path.match(/_c(\d+)\.png/) : null;
                         const ca = ma ? parseInt(ma[1], 10) : 0;
                         const cb = mb ? parseInt(mb[1], 10) : 0;
                         return ca - cb;
                     });
                     
                     cells.forEach(cell => {
                         out += renderCell(cell, isHeader);
                     });
                     out += `</tr>`;
                 });
            }
            
            out += `</table></div>`;
        });
        
        return out;
    };
    
    function renderCell(cell, isHeader=false) {
        let text = cell.ocr ? cell.ocr.text : '';
        if (!text || text.trim() === '') {
            text = '&nbsp;';
        }
        const conf = cell.ocr ? cell.ocr.confidence : 0;
        
        let confClass = '';
        if (cell.ocr && cell.ocr.is_human) {
            confClass = 'bg-green-100 text-green-900 font-medium';
        } else if (cell.ocr && conf < 0.8) {
            confClass = 'cell-low-conf';
        } else if (cell.ocr && conf < 0.95) {
            confClass = 'cell-med-conf';
        }
        
        const tag = isHeader ? 'th' : 'td';
        return `<${tag} class="${confClass}">${text}</${tag}>`;
    }
    
    html += renderTableGroup(manifestData.tables, "Tables");
    html += renderTableGroup(manifestData.borderless_tables, "Borderless Tables");
    
    // We could render headers/footers too
    if (manifestData.headers && manifestData.headers.length > 0) {
        html += `<h2 class="text-lg font-bold text-gray-800 mb-4 mt-6 border-b pb-2">Headers</h2><ul>`;
        manifestData.headers.forEach(h => {
             html += `<li class="text-sm mb-2">Page ${h.page}: ${h.ocr ? h.ocr.text : (h.bbox ? 'Header Box' : 'Unknown')}</li>`;
        });
        html += `</ul>`;
    }
    
    if (manifestData.footers && manifestData.footers.length > 0) {
        html += `<h2 class="text-lg font-bold text-gray-800 mb-4 mt-6 border-b pb-2">Footers</h2><ul>`;
        manifestData.footers.forEach(f => {
             html += `<li class="text-sm mb-2">Page ${f.page}: ${f.ocr ? f.ocr.text : (f.bbox ? 'Footer Box' : 'Unknown')}</li>`;
        });
        html += `</ul>`;
    }
    
    if (html === '') {
        html = '<div class="text-center mt-20 text-gray-500">No layout structures found.</div>';
    }
    
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
