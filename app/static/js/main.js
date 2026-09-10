let currentDocumentId = null;
let components = [];
let currentScale = 1.0;
let currentPage = 1;
let totalPages = 1;
let activeComponentType = null;
const REVIEWABLE_TYPES = ['CELL', 'KEY_VALUE', 'LIST_ITEM', 'SENTENCE', 'PARAGRAPH'];

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

function isReviewableComponent(component) {
    return component && REVIEWABLE_TYPES.includes(component.component_type);
}

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
        statusBadge.className = "badge badge-info";
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
            renderComponentTree();
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

    statusBadge.textContent = "Uploading…";
    statusBadge.className = "badge badge-warn";

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
        statusBadge.className = "badge badge-info";
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
        statusBadge.textContent = "Upload failed";
        statusBadge.className = "badge badge-bad";
    }
});

// Process Document
window.processDocument = async function(engine = 'paddle') {
    if (!currentDocumentId) return;

    statusBadge.textContent = "Processing…";
    statusBadge.className = "badge badge-warn";
    processBtn.disabled = true;
    const processDropdownBtn = document.getElementById('process-dropdown-btn');
    if (processDropdownBtn) processDropdownBtn.disabled = true;
    
    // hide dropdown if open
    const dropdown = document.getElementById('process-dropdown');
    if (dropdown) dropdown.classList.add('hidden');

    try {
        const res = await fetch(`/process/${currentDocumentId}?ocr_engine=${engine}`, {
            method: 'POST'
        });
        const data = await res.json();
        
        // Poll for completion
        pollStatus();
    } catch (err) {
        console.error(err);
        statusBadge.textContent = "Process failed";
        statusBadge.className = "badge badge-bad";
        processBtn.disabled = false;
        if (processDropdownBtn) processDropdownBtn.disabled = false;
    }
};

window.toggleProcessDropdown = function(e) {
    if (e) e.stopPropagation();
    const dropdown = document.getElementById('process-dropdown');
    if (dropdown) {
        dropdown.classList.toggle('hidden');
    }
};

// Close dropdown if clicked outside
document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('process-dropdown');
    const dropdownBtn = document.getElementById('process-dropdown-btn');
    if (dropdown && !dropdown.classList.contains('hidden')) {
        if (e.target !== dropdown && e.target !== dropdownBtn && !dropdown.contains(e.target)) {
            dropdown.classList.add('hidden');
        }
    }
});
async function pollStatus() {
    try {
        const res = await fetch(`/documents/${currentDocumentId}`);
        const doc = await res.json();
        
        if (doc.status === 'completed') {
            statusBadge.textContent = "Completed";
            statusBadge.className = "badge badge-ok";
            totalPages = doc.page_count || 1;
            document.getElementById('view-mode').value = 'enhanced';
            window.updateViewer();
            loadComponents();
            loadDocuments(); // Update dropdown status
        } else if (doc.status === 'error') {
            statusBadge.textContent = "Error";
            statusBadge.className = "badge badge-bad";
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
    renderComponentTree();
}

// Groups the flat `components` array into a parent/child tree.
function buildComponentTree() {
    const compMap = new Map();
    const rootComps = [];

    components.forEach(c => {
        compMap.set(c.id, { ...c, children: [] });
    });

    components.forEach(c => {
        if (c.parent_id && compMap.has(c.parent_id)) {
            compMap.get(c.parent_id).children.push(compMap.get(c.id));
        } else {
            rootComps.push(compMap.get(c.id));
        }
    });

    return rootComps;
}

// Renders tabs + tree from whatever is already in `components`. Kept separate
// from loadComponents() so callers that have just fetched the components
// themselves can re-render without issuing a second request.
function renderComponentTree() {
    const rootComps = buildComponentTree();

    const availableRootTypes = [...new Set(rootComps.map(c => c.component_type))];
    const preferredOrder = ['TABLE', 'BORDERLESS_TABLE', 'KEY_VALUE', 'LIST_ITEM', 'PARAGRAPH', 'SENTENCE', 'HEADER', 'FOOTER'];

    const tabsContainer = document.getElementById('dynamic-tabs');
    tabsContainer.innerHTML = '';

    if (availableRootTypes.length === 0) {
        componentList.innerHTML = '<div class="empty-state">No components found.</div>';
        drawBBoxes();
        return;
    }

    availableRootTypes.sort((a, b) => {
        const ia = preferredOrder.indexOf(a);
        const ib = preferredOrder.indexOf(b);
        return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });

    // Stay on the tab the user is looking at across re-renders; fall back to
    // the first available type when it no longer exists (e.g. new document).
    const selectedType = availableRootTypes.includes(activeComponentType)
        ? activeComponentType
        : availableRootTypes[0];
    activeComponentType = selectedType;

    availableRootTypes.forEach(type => {
        const btn = document.createElement('button');
        btn.dataset.type = type;
        // Count on the tab: an operator picking what to work on next needs to
        // know how much is behind each one without clicking through them.
        const count = rootComps.filter(c => c.component_type === type).length;
        btn.innerHTML = `${escapeHtml(type.replace(/_/g, ' '))}`
            + `<span class="tab-count num">${count}</span>`;
        btn.className = (type === selectedType) ? "tab-btn tab is-active" : "tab-btn tab";

        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('is-active'));
            btn.classList.add('is-active');
            activeComponentType = type;
            renderComponentList(type, rootComps);
        });

        tabsContainer.appendChild(btn);
    });

    renderComponentList(selectedType, rootComps);
    updateReviewProgress(rootComps);
    drawBBoxes();
}

//: Below this a component is treated as needing a human look. Matches the
//: threshold the OCR panel already uses for its bulk-accept action.
const NEEDS_REVIEW_BELOW = 0.95;

function isChecked(c) {
    const pred = c.predictions && c.predictions.length ? c.predictions[0] : null;
    return !!(pred && pred.is_human);
}

function needsReview(c) {
    return !isChecked(c) && (c.confidence ?? 1) < NEEDS_REVIEW_BELOW;
}

// Walks the tree, because a table's cells are where the real work is and they
// live as children rather than at the root.
function walkAll(nodes, out = []) {
    nodes.forEach(c => {
        out.push(c);
        if (c.children && c.children.length) walkAll(c.children, out);
    });
    return out;
}

function updateReviewProgress(rootComps) {
    const box = document.getElementById('review-progress');
    if (!box) return;

    const all = walkAll(rootComps);
    if (!all.length) { box.hidden = true; return; }
    box.hidden = false;

    const checked = all.filter(isChecked).length;
    const low = all.filter(needsReview).length;

    document.getElementById('stat-checked').textContent = checked;
    document.getElementById('stat-total').textContent = all.length;
    document.getElementById('stat-low').textContent = low;
    document.getElementById('review-bar-fill').style.width =
        `${all.length ? (checked / all.length) * 100 : 0}%`;
}

function renderComponentList(type, rootComps) {
    componentList.innerHTML = '';
    let filtered = rootComps.filter(c => c.component_type === type);

    if (filtered.length === 0) {
        componentList.innerHTML = '<div class="empty-state">No components of this type found.</div>';
        return;
    }

    // Worst first, so the operator starts where the system is least sure
    // rather than reading down a list that is mostly already right.
    if (document.getElementById('sort-worst-first')?.checked) {
        filtered = [...filtered].sort((a, b) => (a.confidence ?? 1) - (b.confidence ?? 1));
    }

    filtered.forEach(c => {
        const rootDiv = renderComponentNode(c, 0);
        if (needsReview(c)) rootDiv.querySelector('.component-item')?.classList.add('needs-review');
        componentList.appendChild(rootDiv);
    });
}

function renderComponentNode(c, depth) {
    const wrapper = document.createElement('div');
    wrapper.className = `flex flex-col ml-${depth * 4}`;
    if (depth > 0) wrapper.style.marginLeft = `${depth}rem`;

    const itemDiv = document.createElement('div');
    itemDiv.className = 'component-item tree-item';
    itemDiv.dataset.id = c.id;
    
    let displayTitle = `${c.component_type} ${c.id}`;
    if (c.component_type === 'CELL' && c.manifest_path) {
        const match = c.manifest_path.match(/_r(\d+)_c(\d+)\.png$/);
        if (match) {
            displayTitle = `CELL ${match[1]}-${match[2]}`;
        }
    }
    
    const pred = (c.predictions && c.predictions.length > 0) ? c.predictions[0] : null;
    let confBadge = '';
    if (pred && pred.is_human) {
         confBadge = `<span class="badge badge-ok">Human</span>`;
    } else if (c.confidence) {
        const perc = Math.round(c.confidence * 100);
        let toneClass = '';
        if (perc < 80) toneClass = 'badge-bad';
        else if (perc < 95) toneClass = 'badge-warn';
        confBadge = `<span class="badge ${toneClass} num">${perc}%</span>`;
    }

    let toggleIcon = '';
    const hasChildren = c.children && c.children.length > 0;
    if (hasChildren) {
        toggleIcon = `<span class="toggle-icon tree-toggle" data-expanded="false">▶</span>`;
    }

    // Content first. The operator reads the value and decides; the type and
    // the database id are reference, not the headline. Leading with
    // "KEY_VALUE 4527" put the one meaningless string in the most prominent
    // position on every row.
    const readable = pred && pred.predicted_text ? escapeHtml(pred.predicted_text) : '';
    const heading = readable
        ? `<span class="item-text">${readable}</span>`
        : `<span class="item-text is-empty">${escapeHtml(displayTitle)}</span>`;

    itemDiv.title = `${displayTitle} · page ${c.page_no}`;
    itemDiv.innerHTML = `
        <div class="item-row">
            <span class="item-main">
                ${toggleIcon}
                ${heading}
            </span>
            <div class="item-meta">
                ${confBadge}
            </div>
        </div>
        <div class="item-sub">
            <span class="item-tag">${escapeHtml(c.component_type.replace(/_/g, ' '))}</span>
            <span class="label-micro num">Pg ${c.page_no}</span>
            ${hasChildren ? `<span class="label-micro num">${c.children.length} inside</span>` : ''}
        </div>
    `;

    itemDiv.addEventListener('click', (e) => {
        e.stopPropagation();
        
        // Remove active state from all items
        document.querySelectorAll('.component-item').forEach(el => el.classList.remove('is-selected'));
        itemDiv.classList.add('is-selected');
        
        renderOCRPanel(c);
        
        // Auto switch to Enhanced mode so bbox is visible
        const viewModeSelect = document.getElementById('view-mode');
        if (viewModeSelect && viewModeSelect.value !== 'enhanced') {
            viewModeSelect.value = 'enhanced';
            window.updateViewer();
        }
        
        highlightBBox(c.id);
        
        if (c.page_no !== currentPage) {
            currentPage = c.page_no;
            currentPageSpan.textContent = currentPage;
            loadPageImage();
        }
    });
    
    wrapper.appendChild(itemDiv);

    if (hasChildren) {
        const childrenWrapper = document.createElement('div');
        childrenWrapper.className = 'tree-children hidden';
        c.children.forEach(child => {
            childrenWrapper.appendChild(renderComponentNode(child, depth + 1));
        });
        wrapper.appendChild(childrenWrapper);
        
        const iconEl = itemDiv.querySelector('.toggle-icon');
        iconEl.addEventListener('click', (e) => {
            e.stopPropagation();
            const isExpanded = iconEl.dataset.expanded === "true";
            if (isExpanded) {
                childrenWrapper.classList.add('hidden');
                iconEl.dataset.expanded = "false";
                iconEl.textContent = "▶";
            } else {
                childrenWrapper.classList.remove('hidden');
                iconEl.dataset.expanded = "true";
                iconEl.textContent = "▼";
            }
        });
    }
    
    return wrapper;
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
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
    // Cropped image section for OCR/review units.
    let imageCropHtml = '';
    if (isReviewableComponent(component)) {
        imageCropHtml = `
        <div class="mb-4">
            <span class="label-micro">Component Image</span>
            <div class="rcard-thumb mt-1.5" style="height: 150px;">
                <img src="/cell-image/${component.id}" alt="Component crop"
                     onerror="this.parentElement.innerHTML='<span class=\\'text-muted-2 text-xs\\'>Image not available</span>'">
            </div>
        </div>`;
    }

    if (!component.predictions || component.predictions.length === 0) {
        // No OCR data yet - show image and offer to run OCR
        let runOcrBtn = '';
        if (isReviewableComponent(component)) {
            runOcrBtn = `
            <button class="btn btn-primary btn-block mt-3" onclick="runOcrOnCell(${component.id})">
                Run OCR on this component
            </button>`;
        }
        ocrPanel.innerHTML = `
            ${imageCropHtml}
            <div class="empty-state">No OCR data for this component.</div>
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
            <span class="label-micro">Predicted Text</span>
            <div class="panel mt-1.5 p-2.5 text-ink" style="border-radius: var(--r);">
                ${escapeHtml(pred.predicted_text)}
            </div>
        </div>

        <div class="mb-4">
            <span class="label-micro">Confidence</span>
            <div class="mt-1 conf ${pred.confidence > 0.9 ? 'conf-ok' : 'conf-bad'}" style="font-size: 1.125rem;">
                ${(pred.confidence * 100).toFixed(2)}%
            </div>
        </div>

        <div class="mt-auto">
            <label class="label-micro" for="correction-input">Correction</label>
            <textarea id="correction-input" class="field mt-1.5" rows="3">${escapeHtml(userValue)}</textarea>

            <button class="btn ${isAccepted ? 'btn-accent' : 'btn-primary'} btn-block mt-3" onclick="submitFeedback(${pred.id}, true)">
                ${isAccepted ? '✓ Accepted' : 'Accept'}
            </button>
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
                    // `components` was just refreshed above — re-render the tree
                    // from it rather than re-fetching via loadComponents().
                    renderComponentTree();
                }
            }
        } else {
            btn.textContent = '❌ OCR Failed';
        }
    } catch (e) {
        console.error('OCR request failed', e);
        btn.textContent = '❌ Error';
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
        toast('Could not save that correction.', 'bad');
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
        toast('Nothing above 95% is waiting to be accepted.', 'info');
        return;
    }

    try {
        await fetch('/feedback/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prediction_ids: predsToAccept, is_accepted: true })
        });
        toast(`Accepted ${predsToAccept.length} predictions.`, 'ok');
        loadComponents(); // Reload state
    } catch (e) {
        console.error(e);
        toast('Bulk accept failed.', 'bad');
    }
}


// ── Keyboard navigation ──────────────────────────────────────────────────────
//
// Data entry is keyboard work. Making an operator reach for the mouse for
// every one of a hundred components is the difference between a tool they can
// use all day and one they cannot.

function visibleItems() {
    return [...document.querySelectorAll('#component-list .component-item')]
        .filter(el => el.offsetParent !== null);
}

function moveSelection(step) {
    const items = visibleItems();
    if (!items.length) return;

    const current = items.findIndex(el => el.classList.contains('is-selected'));
    const next = current === -1
        ? (step > 0 ? 0 : items.length - 1)
        : Math.min(items.length - 1, Math.max(0, current + step));

    items[next].click();
    items[next].scrollIntoView({block: 'nearest'});
}

document.addEventListener('keydown', (e) => {
    // Never steal keys from someone correcting a value.
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    switch (e.key) {
        case 'ArrowDown': case 'j':
            e.preventDefault(); moveSelection(1); break;
        case 'ArrowUp': case 'k':
            e.preventDefault(); moveSelection(-1); break;
        case 'Enter': {
            const sel = document.querySelector('#component-list .component-item.is-selected');
            if (sel) { e.preventDefault(); sel.click(); }
            break;
        }
        case 'a': case 'A': {
            const accept = document.getElementById('accept-btn')
                || document.querySelector('#ocr-panel button[data-action="accept"]');
            if (accept && !accept.disabled) { e.preventDefault(); accept.click(); }
            break;
        }
    }
});

document.getElementById('sort-worst-first')?.addEventListener('change', () => {
    renderComponentTree();
});
