let currentDocumentId = null;
let components = [];
let currentScale = 1.0;
let currentPage = 1;
let totalPages = 1;

// Elements
const fileUpload = document.getElementById('file-upload');
const processBtn = document.getElementById('process-btn');
const statusBadge = document.getElementById('status-badge');
const documentImage = document.getElementById('document-image');
const pageWrapper = document.getElementById('page-wrapper');
const bboxContainer = document.getElementById('bbox-container');
const componentList = document.getElementById('component-list');
const ocrPanel = document.getElementById('ocr-panel');
const currentPageSpan = document.getElementById('current-page');
const docSelector = document.getElementById('doc-selector');

async function loadDocuments() {
    try {
        const res = await fetch('/documents');
        const docs = await res.json();
        
        docSelector.innerHTML = '<option value="">-- Select Document --</option>';
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

window.downloadManifest = function() {
    if (!currentDocumentId) return;
    window.open(`/download-manifest/${currentDocumentId}`, '_blank');
};

window.selectDocument = async function(docId) {
    if (!docId) return;
    
    const dlBtn = document.getElementById('download-manifest-btn');
    if (dlBtn) dlBtn.classList.remove('hidden');

    try {
        const res = await fetch(`/documents/${docId}`);
        const doc = await res.json();
        
        currentDocumentId = doc.id;
        window.currentFilename = doc.filename;
        statusBadge.textContent = doc.status.charAt(0).toUpperCase() + doc.status.slice(1);
        statusBadge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-blue-500 text-white";
        processBtn.disabled = false;
        
        // Load original view by default
        const originalEmbed = document.getElementById('original-embed');
        document.getElementById('view-mode').value = 'original';
        
        originalEmbed.src = `/uploads/${doc.filename}`;
        originalEmbed.style.display = 'block';
        pageWrapper.style.display = 'none';
        
        if (doc.status === 'completed') {
            totalPages = doc.page_count || 1;
            loadComponents();
        } else {
            components = [];
            renderComponentList('TABLE');
        }
    } catch (e) {
        console.error("Failed to select document", e);
    }
}

// Initial load
loadDocuments();

// File Upload
fileUpload.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    statusBadge.textContent = "Uploading...";
    statusBadge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-yellow-500 text-white";

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        currentDocumentId = data.id;
        window.currentFilename = data.filename;
        statusBadge.textContent = "Uploaded";
        statusBadge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-blue-500 text-white";
        processBtn.disabled = false;
        
        // Reload document list
        await loadDocuments();
        docSelector.value = data.id;
        
        // Show original file embed immediately
        const originalEmbed = document.getElementById('original-embed');
        document.getElementById('view-mode').value = 'original';
        
        originalEmbed.src = `/uploads/${data.filename}`;
        originalEmbed.style.display = 'block';
        pageWrapper.style.display = 'none';
        
    } catch (err) {
        console.error(err);
        statusBadge.textContent = "Upload Failed";
        statusBadge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-red-500 text-white";
    }
});

// Process Document
processBtn.addEventListener('click', async () => {
    if (!currentDocumentId) return;

    statusBadge.textContent = "Processing...";
    statusBadge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-yellow-500 text-white";
    processBtn.disabled = true;

    try {
        const res = await fetch(`/process/${currentDocumentId}`, {
            method: 'POST'
        });
        const data = await res.json();
        
        // Poll for completion
        pollStatus();
    } catch (err) {
        console.error(err);
        statusBadge.textContent = "Process Failed";
        statusBadge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-red-500 text-white";
        processBtn.disabled = false;
    }
});

async function pollStatus() {
    try {
        const res = await fetch(`/documents/${currentDocumentId}`);
        const doc = await res.json();
        
        if (doc.status === 'completed') {
            statusBadge.textContent = "Completed";
            statusBadge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-green-500 text-white";
            totalPages = doc.page_count || 1;
            document.getElementById('view-mode').value = 'enhanced';
            window.updateViewer();
            loadComponents();
            loadDocuments(); // Update dropdown status
        } else if (doc.status === 'error') {
            statusBadge.textContent = "Error";
            statusBadge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-red-500 text-white";
            processBtn.disabled = false;
            loadDocuments(); // Update dropdown status
        } else {
            setTimeout(pollStatus, 2000);
        }
    } catch (err) {
        console.error("Polling error", err);
    }
}

function loadPageImage() {
    const paddedPageNum = String(currentPage).padStart(3, '0');
    fetch(`/documents/${currentDocumentId}`).then(res => res.json()).then(doc => {
        const baseName = doc.filename.split('.').slice(0, -1).join('.');
        const viewMode = document.getElementById('view-mode').value;
        const pagesDir = viewMode === 'enhanced' ? 'pages_enhanced' : 'pages';
        const imgSrc = `/outputs/uploads/${baseName}_piply/${pagesDir}/page_${paddedPageNum}.png`;
        
        documentImage.src = imgSrc;
        documentImage.style.display = 'block';
        
        documentImage.onload = () => {
            fitWidth();
            drawBBoxes();
        };
    });
}

window.updateViewer = function() {
    const viewMode = document.getElementById('view-mode').value;
    const originalEmbed = document.getElementById('original-embed');
    const pageWrapper = document.getElementById('page-wrapper');
    const zoomControls = document.getElementById('zoom-controls');
    
    if (viewMode === 'original') {
        originalEmbed.style.display = 'block';
        pageWrapper.style.display = 'none';
        if (zoomControls) zoomControls.style.opacity = '0.5';
    } else {
        originalEmbed.style.display = 'none';
        pageWrapper.style.display = 'inline-block';
        if (zoomControls) zoomControls.style.opacity = '1';
        if (currentDocumentId) {
            loadPageImage();
        }
    }
}

function applyScale() {
    const scaleWrapper = document.getElementById('scale-wrapper');
    scaleWrapper.style.transform = `scale(${currentScale})`;
    
    // Adjust outer container to allow proper scrolling
    const imgWidth = documentImage.naturalWidth || 800;
    const imgHeight = documentImage.naturalHeight || 1000;
    pageWrapper.style.width = `${imgWidth * currentScale}px`;
    pageWrapper.style.height = `${imgHeight * currentScale}px`;
}

function zoom(delta) {
    currentScale += delta;
    if (currentScale < 0.2) currentScale = 0.2;
    if (currentScale > 5.0) currentScale = 5.0;
    applyScale();
}

function fitWidth() {
    const containerWidth = document.getElementById('viewer-container').clientWidth;
    const imgWidth = documentImage.naturalWidth || 800;
    currentScale = (containerWidth - 40) / imgWidth;
    applyScale();
}

function prevPage() {
    if (currentPage > 1) {
        currentPage--;
        currentPageSpan.textContent = currentPage;
        loadPageImage();
    }
}

function nextPage() {
    if (currentPage < totalPages) {
        currentPage++;
        currentPageSpan.textContent = currentPage;
        loadPageImage();
    }
}

async function loadComponents() {
    const res = await fetch(`/components/${currentDocumentId}`);
    components = await res.json();
    
    // Auto-select a tab that has components
    const types = ['TABLE', 'BORDERLESS_TABLE', 'HEADER', 'FOOTER'];
    let selectedType = 'TABLE';
    for (let t of types) {
        if (components.some(c => c.component_type === t)) {
            selectedType = t;
            break;
        }
    }
    
    // Update active tab button visually
    document.querySelectorAll('.tab-btn').forEach(b => {
        if (b.dataset.type === selectedType) {
            b.className = "tab-btn px-3 py-1 bg-blue-100 text-blue-800 rounded whitespace-nowrap";
        } else {
            b.className = "tab-btn px-3 py-1 hover:bg-gray-200 text-gray-600 rounded whitespace-nowrap";
        }
    });

    renderComponentList(selectedType);
    drawBBoxes();
}

// Tabs
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        document.querySelectorAll('.tab-btn').forEach(b => {
            b.className = "tab-btn px-3 py-1 hover:bg-gray-200 text-gray-600 rounded whitespace-nowrap";
        });
        e.target.className = "tab-btn px-3 py-1 bg-blue-100 text-blue-800 rounded whitespace-nowrap";
        renderComponentList(e.target.dataset.type);
    });
});

function renderComponentList(type) {
    componentList.innerHTML = '';
    const filtered = components.filter(c => c.component_type === type);
    
    if (filtered.length === 0) {
        componentList.innerHTML = '<div class="text-gray-500 text-sm text-center mt-10">No components of this type found.</div>';
        return;
    }

    filtered.forEach(c => {
        let displayTitle = `${c.component_type} ${c.id}`;
        if (c.component_type === 'CELL' && c.manifest_path) {
            const match = c.manifest_path.match(/_r(\d+)_c(\d+)\.png$/);
            if (match) {
                displayTitle = `CELL ${match[1]}-${match[2]}`;
            }
        }

        const div = document.createElement('div');
        div.className = "p-3 border border-gray-200 rounded hover:bg-blue-50 cursor-pointer transition";
        div.innerHTML = `
            <div class="font-semibold text-sm text-gray-800">${displayTitle}</div>
            <div class="text-xs text-gray-500 mt-1">Page: ${c.page_no} | Conf: ${(c.confidence * 100).toFixed(1)}%</div>
        `;
        div.addEventListener('click', () => {
            // Auto switch to Enhanced mode so bbox is visible
            const viewModeSelect = document.getElementById('view-mode');
            if (viewModeSelect.value !== 'enhanced') {
                viewModeSelect.value = 'enhanced';
                window.updateViewer();
            }

            highlightBBox(c.id);
            if(c.page_no !== currentPage) {
                currentPage = c.page_no;
                currentPageSpan.textContent = currentPage;
                loadPageImage();
            }
            renderOCRPanel(c);
        });
        componentList.appendChild(div);
    });
}

function drawBBoxes() {
    bboxContainer.innerHTML = '';
    const pageComponents = components.filter(c => c.page_no === currentPage);
    
    // Scale factor between original image and displayed image
    // Actually our scale transform handles it, so we just use natural coords
    
    pageComponents.forEach(c => {
        try {
            const bbox = JSON.parse(c.bbox);
            if (!bbox || bbox.length < 4) return;
            
            const div = document.createElement('div');
            div.className = `bbox bbox-${c.id}`;
            // If bbox is [x0, y0, x1, y1]
            let x0, y0, x1, y1;
            if (bbox.length === 4) {
                [x0, y0, x1, y1] = bbox;
            } else { return; }

            div.style.left = `${x0}px`;
            div.style.top = `${y0}px`;
            div.style.width = `${x1 - x0}px`;
            div.style.height = `${y1 - y0}px`;
            
            bboxContainer.appendChild(div);
        } catch(e) {}
    });
}

function highlightBBox(id) {
    document.querySelectorAll('.bbox').forEach(el => el.classList.remove('active'));
    const el = document.querySelector(`.bbox-${id}`);
    if (el) {
        el.classList.add('active');
        el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
    }
}

function renderOCRPanel(component) {
    // Cell image section (always show for CELL components)
    let imageCropHtml = '';
    if (component.component_type === 'CELL') {
        imageCropHtml = `
        <div class="mb-4">
            <span class="text-xs font-semibold text-gray-500 uppercase">Cell Image</span>
            <div class="mt-1 border border-gray-300 rounded shadow-sm overflow-hidden bg-gray-100 flex justify-center p-2">
                <img src="/cell-image/${component.id}" style="max-width: 100%; max-height: 150px; object-fit: contain;"
                     onerror="this.parentElement.innerHTML='<span class=\\'text-xs text-gray-400\\'>Image not available</span>'">
            </div>
        </div>`;
    }

    if (!component.predictions || component.predictions.length === 0) {
        // No OCR data yet - show image and offer to run OCR
        let runOcrBtn = '';
        if (component.component_type === 'CELL') {
            runOcrBtn = `
            <button class="mt-3 w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded shadow text-sm font-bold transition"
                    onclick="runOcrOnCell(${component.id})">
                🔍 Run OCR on this Cell
            </button>`;
        }
        ocrPanel.innerHTML = `
            ${imageCropHtml}
            <div class="text-gray-500 text-sm text-center mt-4">No OCR data for this component.</div>
            ${runOcrBtn}
        `;
        return;
    }

    // Display first prediction
    const pred = component.predictions[0];
    const isAccepted = pred.feedback && pred.feedback.length > 0 && pred.feedback[0].is_accepted;
    const userValue = (pred.feedback && pred.feedback.length > 0) ? pred.feedback[0].user_value : pred.predicted_text;

    ocrPanel.innerHTML = `
        ${imageCropHtml}
        <div class="mb-4">
            <span class="text-xs font-semibold text-gray-500 uppercase">Predicted Text</span>
            <div class="mt-1 p-2 bg-white border border-gray-300 rounded shadow-sm text-sm">
                ${pred.predicted_text}
            </div>
        </div>
        
        <div class="mb-4">
            <span class="text-xs font-semibold text-gray-500 uppercase">Confidence</span>
            <div class="mt-1 text-sm font-bold ${pred.confidence > 0.9 ? 'text-green-600' : 'text-red-600'}">
                ${(pred.confidence * 100).toFixed(2)}%
            </div>
        </div>

        <div class="mt-auto">
            <label class="text-xs font-semibold text-gray-500 uppercase">Correction</label>
            <textarea id="correction-input" class="w-full mt-1 p-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" rows="3">${userValue}</textarea>
            
            <div class="flex space-x-2 mt-4">
                <button class="flex-1 bg-green-600 hover:bg-green-700 text-white py-2 rounded shadow text-sm font-bold transition" onclick="submitFeedback(${pred.id}, true)">
                    ${isAccepted ? '✓ Accepted' : 'Accept'}
                </button>
            </div>
        </div>
    `;
}

async function runOcrOnCell(componentId) {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '⏳ Running OCR...';
    try {
        const res = await fetch(`/ocr-cell/${componentId}`, { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.text !== undefined) {
            // Reload components to get updated predictions
            const docId = document.getElementById('doc-selector').value;
            if (docId) {
                const compRes = await fetch(`/components/${docId}`);
                components = await compRes.json();
                const updated = components.find(c => c.id === componentId);
                if (updated) {
                    renderOCRPanel(updated);
                    renderComponents();
                }
            }
        } else {
            btn.textContent = '❌ OCR Failed';
            setTimeout(() => { btn.textContent = '🔍 Run OCR on this Cell'; btn.disabled = false; }, 2000);
        }
    } catch (e) {
        console.error('OCR request failed', e);
        btn.textContent = '❌ Error';
        setTimeout(() => { btn.textContent = '🔍 Run OCR on this Cell'; btn.disabled = false; }, 2000);
    }
}

async function submitFeedback(predictionId, isAccepted) {
    const val = document.getElementById('correction-input').value;
    try {
        await fetch(`/feedback/${predictionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_value: val, is_accepted: isAccepted })
        });
        
        // Update local state
        const comp = components.find(c => c.predictions.some(p => p.id === predictionId));
        if (comp) {
            const pred = comp.predictions.find(p => p.id === predictionId);
            pred.feedback = [{ user_value: val, is_accepted: isAccepted }];
            renderOCRPanel(comp);
        }
    } catch (e) {
        console.error(e);
        alert('Failed to submit feedback');
    }
}

async function acceptHighConfidence() {
    const predsToAccept = [];
    components.forEach(c => {
        c.predictions.forEach(p => {
            if (p.confidence >= 0.95 && (!p.feedback || p.feedback.length === 0 || !p.feedback[0].is_accepted)) {
                predsToAccept.push(p.id);
            }
        });
    });

    if (predsToAccept.length === 0) {
        alert("No pending high-confidence predictions found.");
        return;
    }

    try {
        await fetch('/feedback/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prediction_ids: predsToAccept, is_accepted: true })
        });
        alert(`Accepted ${predsToAccept.length} predictions.`);
        loadComponents(); // Reload state
    } catch (e) {
        console.error(e);
        alert('Bulk accept failed');
    }
}
