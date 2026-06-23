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
            
            // Extract rows
            const rows = t.children.filter(c => c.type === 'ROW');
            // If there are no rows explicitly, maybe just cells?
            if (rows.length === 0) {
                 const cells = t.children.filter(c => c.type === 'CELL');
                 out += `<tr>`;
                 cells.forEach(cell => {
                     out += renderCell(cell);
                 });
                 out += `</tr>`;
            } else {
                 rows.forEach((r, idx) => {
                     const isHeader = (idx === 0);
                     out += `<tr>`;
                     const cells = r.children.filter(c => c.type === 'CELL');
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
        const text = cell.ocr ? cell.ocr.text : '';
        const conf = cell.ocr ? cell.ocr.confidence : 0;
        
        let confClass = '';
        if (cell.ocr && conf < 0.8) {
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
    
    // Simple export: iterate tables and rows
    const allTables = (manifestData.tables || []).concat(manifestData.borderless_tables || []);
    
    allTables.forEach((t, i) => {
        csvContent += `TABLE ${i+1} (Page ${t.page})\n`;
        const rows = t.children.filter(c => c.type === 'ROW');
        rows.forEach(r => {
            const cells = r.children.filter(c => c.type === 'CELL');
            const rowData = cells.map(c => {
                let text = c.ocr ? c.ocr.text : '';
                // escape quotes and wrap in quotes
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
    const opt = {
      margin:       0.5,
      filename:     `reconstructed_${currentDocumentId}.pdf`,
      image:        { type: 'jpeg', quality: 0.98 },
      html2canvas:  { scale: 2 },
      jsPDF:        { unit: 'in', format: 'letter', orientation: 'portrait' }
    };
    html2pdf().set(opt).from(element).save();
}

// Init
loadDocuments();
