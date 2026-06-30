let currentDocumentId = null;
let cells = [];
let currentPage = 1;
const itemsPerPage = 60;

const docSelector = document.getElementById('doc-selector');
const reviewList = document.getElementById('review-list');
const loading = document.getElementById('loading');

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

        if (docs.length > 0) {
            const currentDocStr = new URLSearchParams(window.location.search).get('document_id');
            if (currentDocStr) {
                docSelector.value = currentDocStr;
                window.selectDocument(currentDocStr);
            } else if (!currentDocumentId) {
                docSelector.value = docs[0].id;
                window.selectDocument(docs[0].id);
            }
        }
    } catch (e) {
        console.error("Failed to load documents", e);
    }
}

const reloadStates = {};

window.reloadCell = async function (componentId) {
    const loaderEl = document.getElementById(`loader-${componentId}`);
    if (loaderEl) loaderEl.classList.remove('hidden');

    const currentState = reloadStates[componentId] || 'default';
    let nextState = 'salt';
    let nextBtnText = '↻ Reload (Tesseract)';
    
    if (currentState === 'salt') {
        nextState = 'tesseract';
        nextBtnText = '↻ Reload (Paddle)';
    } else if (currentState === 'tesseract') {
        nextState = 'paddle';
        nextBtnText = '↻ Reload (Salt)';
    } else if (currentState === 'paddle') {
        nextState = 'salt';
        nextBtnText = '↻ Reload (Tesseract)';
    }

    try {
        const res = await fetch(`/ocr-cell/${componentId}/reload?strategy=${nextState}`, { method: 'POST' });
        const updatedComponent = await res.json();

        // update cells locally
        const cell = cells.find(c => c.id === componentId);
        if (cell) {
            cell.predictions = updatedComponent.predictions;
        }
        
        reloadStates[componentId] = nextState;

        const card = document.getElementById(`card-${componentId}`);
        if (card) {
            card.innerHTML = getCardInnerHtml(cell);
            // Update the button text inside the new HTML
            const btn = card.querySelector(`button[onclick="reloadCell(${componentId})"]`);
            if (btn) btn.textContent = nextBtnText;
        }
    } catch (e) {
        console.error("Failed to run OCR for cell", e);
        if (loaderEl) loaderEl.classList.add('hidden');
    }
}

let selectedPages = new Set();
let selectedTables = new Set();
let allPages = new Set();
let allTables = new Set();
let pollInterval = null;

window.reprocessDocument = async function() {
    if (!currentDocumentId) return;
    if (!confirm("Are you sure you want to re-process this document? All current predictions will be cleared and re-extracted from the images.")) return;
    
    loading.classList.remove('hidden');
    try {
        const res = await fetch(`/process/${currentDocumentId}`, { method: 'POST' });
        if (res.ok) {
            // Re-select document to kick off polling and load empty state
            await window.selectDocument(currentDocumentId);
        } else {
            alert("Failed to start processing.");
        }
    } catch (e) {
        console.error(e);
        alert("An error occurred.");
    } finally {
        loading.classList.add('hidden');
    }
}

window.resumeOcr = async function() {
    if (!currentDocumentId) return;
    const btnResume = document.getElementById('btn-resume-ocr');
    if (btnResume) {
        btnResume.disabled = true;
        btnResume.innerHTML = `<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Resuming...`;
    }
    try {
        const res = await fetch(`/resume-ocr/${currentDocumentId}`, { method: 'POST' });
        if (res.ok) {
            checkAndPollOcr();
        } else {
            alert("Failed to resume OCR.");
            if (btnResume) {
                btnResume.disabled = false;
                btnResume.innerHTML = '▶ Resume OCR';
            }
        }
    } catch (e) {
        console.error(e);
        alert("An error occurred.");
        if (btnResume) {
            btnResume.disabled = false;
            btnResume.innerHTML = '▶ Resume OCR';
        }
    }
}

window.selectDocument = async function (docId) {
    if (!docId) return;
    currentDocumentId = docId;
    loading.classList.remove('hidden');

    try {
        const res = await fetch(`/components/${docId}?t=${new Date().getTime()}`);
        const allComps = await res.json();
        cells = allComps.filter(c => c.component_type === 'CELL');

        allPages.clear();
        allTables.clear();
        selectedPages.clear();
        selectedTables.clear();

        cells.forEach(c => {
            if (c.manifest_path) {
                const normPath = c.manifest_path.replace(/\\/g, '/');
                const pageMatch = normPath.match(/page_(\d+)/i);
                if (pageMatch) allPages.add(pageMatch[1]);

                const tableMatch = normPath.match(/(borderless_table_\d+|table_\d+)/i);
                if (tableMatch) allTables.add(tableMatch[1].toLowerCase());
            }
        });

        const btnReprocess = document.getElementById('btn-reprocess');
        if (btnReprocess) btnReprocess.classList.remove('hidden');

        renderAdvancedFilters();
        window.renderReviewList();

        // Start polling if missing predictions
        checkAndPollOcr();
    } catch (e) {
        console.error("Failed to load components", e);
    } finally {
        loading.classList.add('hidden');
    }
}

function renderAdvancedFilters() {
    const advFilters = document.getElementById('advanced-filters');
    const pageFilters = document.getElementById('page-filters');
    const tableFilters = document.getElementById('table-filters');

    if (!advFilters) return;

    if (allPages.size === 0 && allTables.size === 0) {
        advFilters.classList.add('hidden');
        return;
    }

    advFilters.classList.remove('hidden');

    pageFilters.innerHTML = '';
    Array.from(allPages).sort((a, b) => parseInt(a) - parseInt(b)).forEach(p => {
        const btn = document.createElement('button');
        btn.className = `px-2 py-1 text-xs border rounded transition ${selectedPages.has(p) ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`;
        btn.textContent = `Page ${p}`;
        btn.onclick = () => {
            if (selectedPages.has(p)) selectedPages.delete(p);
            else selectedPages.add(p);
            btn.className = `px-2 py-1 text-xs border rounded transition ${selectedPages.has(p) ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`;
            window.renderReviewList();
        };
        pageFilters.appendChild(btn);
    });

    tableFilters.innerHTML = '';
    Array.from(allTables).sort().forEach(t => {
        const btn = document.createElement('button');
        const displayT = t.replace('borderless_', 'B-').replace('_', ' ');
        btn.className = `px-2 py-1 text-xs border rounded transition ${selectedTables.has(t) ? 'bg-green-600 text-white border-green-600' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`;
        btn.textContent = displayT;
        btn.onclick = () => {
            if (selectedTables.has(t)) selectedTables.delete(t);
            else selectedTables.add(t);
            btn.className = `px-2 py-1 text-xs border rounded transition ${selectedTables.has(t) ? 'bg-green-600 text-white border-green-600' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`;
            window.renderReviewList();
        };
        tableFilters.appendChild(btn);
    });
}

function checkAndPollOcr() {
    if (pollInterval) clearInterval(pollInterval);

    const missingCount = cells.filter(c => !c.predictions || c.predictions.length === 0).length;
    const btnResume = document.getElementById('btn-resume-ocr');
    
    if (missingCount > 0) {
        if (btnResume) btnResume.classList.remove('hidden');
        pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/components/${currentDocumentId}?t=${new Date().getTime()}`);
                const allComps = await res.json();
                const newCells = allComps.filter(c => c.component_type === 'CELL');
                const newMissingCount = newCells.filter(c => !c.predictions || c.predictions.length === 0).length;

                if (newMissingCount < cells.filter(c => !c.predictions || c.predictions.length === 0).length) {
                    const changedCells = newCells.filter(newC => {
                        const oldC = cells.find(c => c.id === newC.id);
                        if (!oldC) return true;
                        const oldPreds = oldC.predictions ? oldC.predictions.length : 0;
                        const newPreds = newC.predictions ? newC.predictions.length : 0;
                        return oldPreds !== newPreds;
                    });
                    
                    cells = newCells;
                    
                    changedCells.forEach(newC => {
                        const cardEl = document.getElementById(`card-${newC.id}`);
                        if (cardEl) {
                            cardEl.innerHTML = getCardInnerHtml(newC);
                        }
                    });

                    if (newMissingCount === 0) {
                        clearInterval(pollInterval);
                        if (btnResume) btnResume.classList.add('hidden');
                    }
                }
            } catch (e) { }
        }, 5000);
    } else {
        if (btnResume) btnResume.classList.add('hidden');
    }
}

window.renderReviewList = function (resetPage = true, targetPage = 1) {
    if (resetPage) currentPage = 1;
    else currentPage = targetPage;

    reviewList.innerHTML = '';

    const filterVal = document.getElementById('filter-confidence').value;
    const sortVal = document.getElementById('sort-confidence').value;
    const searchVal = document.getElementById('search-input') ? document.getElementById('search-input').value.toLowerCase() : '';
    const sourceVal = document.getElementById('filter-source') ? document.getElementById('filter-source').value : 'all';

    // Update URL state
    const url = new URL(window.location);
    url.searchParams.set('page', currentPage);
    url.searchParams.set('sort', sortVal);
    url.searchParams.set('source', sourceVal);
    if (searchVal) url.searchParams.set('search', searchVal);
    else url.searchParams.delete('search');
    window.history.replaceState(null, '', url);

    let filtered = [...cells];

    // Search Filter
    if (searchVal) {
        filtered = filtered.filter(c => {
            let displayTitle = `CELL ${c.id}`;
            if (c.manifest_path) {
                const match = c.manifest_path.match(/_r(\d+)_c(\d+)\.png$/);
                if (match) displayTitle = `CELL ${match[1]}-${match[2]}`;
            }
            const predText = (c.predictions && c.predictions.length > 0) ? c.predictions[0].predicted_text.toLowerCase() : '';
            return displayTitle.toLowerCase().includes(searchVal) || c.id.toString() === searchVal || predText.includes(searchVal);
        });
    }

    // Advanced Filters
    if (selectedPages.size > 0 || selectedTables.size > 0) {
        filtered = filtered.filter(c => {
            if (!c.manifest_path) return false;

            // Fix Windows path matching by replacing backslashes with forward slashes for the regex
            const normPath = c.manifest_path.replace(/\\/g, '/');
            const pageMatch = normPath.match(/page_(\d+)/i);
            const tableMatch = normPath.match(/(?:borderless_table|table)_(\d+)/i);

            const pageOk = selectedPages.size === 0 || (pageMatch && selectedPages.has(pageMatch[1]));
            // tableMatch[0] matches the full "table_001" or "borderless_table_001" which is exactly what we stored in allTables
            const tableOk = selectedTables.size === 0 || (tableMatch && selectedTables.has(tableMatch[0].toLowerCase()));

            return pageOk && tableOk;
        });
    }

    // Source Filter
    if (sourceVal !== 'all') {
        filtered = filtered.filter(c => {
            const pred = (c.predictions && c.predictions.length > 0) ? c.predictions[0] : null;
            if (!pred) return false;
            
            let source = pred.source || 'ocr';
            
            const fb = (pred.feedback && pred.feedback.length > 0) ? pred.feedback[0] : null;
            const isAccepted = fb && fb.is_accepted && fb.source !== 'hash_match';
            if (isAccepted) {
                if (fb.user_value !== pred.predicted_text) {
                    source = 'human';
                } else {
                    source = 'human_verified';
                }
            }
            
            if (sourceVal === 'ocr') {
                return ['ocr', 'paddle', 'tesseract', 'paddleocr'].includes(source);
            }
            if (sourceVal === 'ml') {
                return source.startsWith('ml_');
            }
            
            return source === sourceVal;
        });
    }

    // Confidence Filter
    if (filterVal !== 'all') {
        const threshold = parseInt(filterVal) / 100.0;
        filtered = filtered.filter(c => {
            const pred = (c.predictions && c.predictions.length > 0) ? c.predictions[0] : null;
            const conf = pred ? pred.confidence : 0;
            return conf < threshold;
        });
    }

    // Sort
    if (sortVal === 'asc') {
        filtered.sort((a, b) => {
            const confA = (a.predictions && a.predictions.length > 0) ? a.predictions[0].confidence : 0;
            const confB = (b.predictions && b.predictions.length > 0) ? b.predictions[0].confidence : 0;
            return confA - confB;
        });
    } else if (sortVal === 'desc') {
        filtered.sort((a, b) => {
            const confA = (a.predictions && a.predictions.length > 0) ? a.predictions[0].confidence : 0;
            const confB = (b.predictions && b.predictions.length > 0) ? b.predictions[0].confidence : 0;
            return confB - confA;
        });
    } else {
        // default is id order, but push ready predictions to the front
        filtered.sort((a, b) => {
            const aReady = (a.predictions && a.predictions.length > 0) ? 1 : 0;
            const bReady = (b.predictions && b.predictions.length > 0) ? 1 : 0;
            if (aReady !== bReady) return bReady - aReady;
            return a.id - b.id;
        });
    }
    const countEl = document.getElementById('card-count');
    if (countEl) countEl.textContent = filtered.length;

    if (filtered.length === 0) {
        reviewList.innerHTML = '<div class="col-span-full text-center text-gray-500 mt-10">No cells match your filters.</div>';
        const pagControls = document.getElementById('pagination-controls');
        if (pagControls) pagControls.classList.add('hidden');
        return;
    }

    const totalPages = Math.ceil(filtered.length / itemsPerPage);
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const startIdx = (currentPage - 1) * itemsPerPage;
    const paginated = filtered.slice(startIdx, startIdx + itemsPerPage);

    paginated.forEach(c => {
        let borderColor = 'border-gray-200';
        const pred = (c.predictions && c.predictions.length > 0) ? c.predictions[0] : null;
        if (pred) {
            let normalizedConf = pred.confidence;
            if (normalizedConf > 1.0) normalizedConf = normalizedConf / 100.0;
            const confPct = Math.round(normalizedConf * 100);
            const fb = (pred.feedback && pred.feedback.length > 0) ? pred.feedback[0] : null;
            const isAccepted = fb && fb.is_accepted && fb.source !== 'hash_match';
            const userValue = isAccepted ? fb.user_value : pred.predicted_text;
            const isHuman = isAccepted && (userValue !== pred.predicted_text);
            
            if (isHuman) borderColor = 'border-green-300 shadow-green-100 shadow-sm';
            else if (isAccepted) borderColor = 'border-blue-300 shadow-blue-100 shadow-sm';
            else {
                if (confPct >= 90) borderColor = 'border-green-200';
                else if (confPct >= 80) borderColor = 'border-yellow-200';
                else borderColor = 'border-red-300 bg-red-50';
            }
        }

        const card = document.createElement('div');
        card.id = `card-${c.id}`;
        card.className = `relative flex flex-col bg-white border ${borderColor} rounded-lg overflow-hidden transition hover:shadow-md`;
        card.innerHTML = getCardInnerHtml(c);
        reviewList.appendChild(card);
    });

    const pagControls = document.getElementById('pagination-controls');
    if (pagControls) {
        if (totalPages > 1) {
            pagControls.classList.remove('hidden');
            pagControls.classList.add('flex');
            document.getElementById('page-indicator').textContent = `Page ${currentPage} of ${totalPages}`;
            document.getElementById('btn-prev-page').disabled = currentPage === 1;
            document.getElementById('btn-next-page').disabled = currentPage === totalPages;
        } else {
            pagControls.classList.add('hidden');
            pagControls.classList.remove('flex');
        }
    }
}

function getCardInnerHtml(c) {
    let displayTitle = `CELL ${c.id}`;
    if (c.manifest_path) {
        const match = c.manifest_path.match(/_r(\d+)_c(\d+)\.png$/);
        if (match) displayTitle = `CELL ${match[1]}-${match[2]}`;
    }

    const pred = (c.predictions && c.predictions.length > 0) ? c.predictions[0] : null;
    let isAccepted = false;
    let userValue = '';
    let originalOcr = '';
    let confText = 'No OCR Data';
    let confColor = 'text-gray-500';
    let borderColor = 'border-gray-200';
    let sourceBadge = '';
    let isHuman = false;

    if (pred) {
        const fb = (pred.feedback && pred.feedback.length > 0) ? pred.feedback[0] : null;
        isAccepted = fb && fb.is_accepted && fb.source !== 'hash_match';
        originalOcr = pred.predicted_text;
        userValue = isAccepted ? fb.user_value : originalOcr;
        isHuman = isAccepted && (userValue !== originalOcr);

        let normalizedConf = pred.confidence;
        if (normalizedConf > 1.0) normalizedConf = normalizedConf / 100.0;
        const confPct = Math.round(normalizedConf * 100);

        let source = pred.source || 'ocr';
        let sourceDisplay = source.toUpperCase();
        if (source === 'exact_match') sourceDisplay = 'EXACT HASH MATCH';
        else if (source.startsWith('ml_')) sourceDisplay = `ML (${source.replace('ml_', '').toUpperCase()})`;
        else if (source === 'paddle' || source === 'paddleocr') sourceDisplay = 'OCR (PADDLE)';
        else if (source === 'tesseract') sourceDisplay = 'OCR (TESSERACT)';
        else if (source === 'ocr') sourceDisplay = 'OCR';

        if (isHuman) {
            confText = '100% (Human)';
            confColor = 'text-green-600';
            borderColor = 'border-green-300 shadow-green-100 shadow-sm';
            sourceBadge = `<span class="bg-green-100 text-green-800 text-[10px] font-bold px-1.5 py-0.5 rounded uppercase">Source: Human</span>`;
        } else if (isAccepted) {
            confText = '100% (Verified)';
            confColor = 'text-blue-600';
            borderColor = 'border-blue-300 shadow-blue-100 shadow-sm';
            sourceBadge = `<span class="bg-blue-100 text-blue-800 text-[10px] font-bold px-1.5 py-0.5 rounded uppercase">Source: VERIFIED OCR</span>`;
        } else {
            confText = `${confPct}%`;
            let badgeClass = "bg-gray-100 text-gray-600";
            if (source === 'exact_match') badgeClass = "bg-purple-100 text-purple-800";

            sourceBadge = `<span class="${badgeClass} text-[10px] font-bold px-1.5 py-0.5 rounded uppercase">Source: ${sourceDisplay}</span>`;

            if (confPct >= 90) { confColor = 'text-green-600'; borderColor = 'border-green-200'; }
            else if (confPct >= 80) { confColor = 'text-yellow-600'; borderColor = 'border-yellow-200'; }
            else { confColor = 'text-red-600'; borderColor = 'border-red-300 bg-red-50'; }
        }
    }

    let valueHtml = '';
    if (pred) {
        if (isHuman) {
            valueHtml = `
                <div class="text-xs text-gray-500 mb-1">OCR Original: <span class="line-through">${originalOcr}</span></div>
                <div class="text-sm font-semibold text-gray-900 mb-2 flex flex-row items-center flex-wrap gap-2">
                    <span>Human Value:</span>
                    <span class="text-green-700 font-bold whitespace-nowrap">${userValue} <button onclick="toggleEdit(${c.id})" class="text-xs text-blue-600 hover:text-blue-800" title="Edit text">✏️</button></span>
                </div>
                
                <div id="edit-box-${c.id}" class="hidden mt-2">
                    <input type="text" id="input-${c.id}" value="${userValue}" class="w-full text-sm border border-gray-300 rounded px-2 py-1 focus:ring-1 focus:ring-blue-500 focus:outline-none">
                    <button id="btn-${c.id}" onclick="submitFeedback(${pred.id}, ${c.id})" class="w-full mt-2 py-1 rounded text-sm font-semibold transition bg-blue-600 hover:bg-blue-700 text-white shadow-sm">
                        Save Changes
                    </button>
                </div>
            `;
        } else if (isAccepted) {
            valueHtml = `
                <div class="text-xs text-gray-500 flex justify-between items-center mb-1">
                    <span>Verified Value: </span>
                    <div id="display-val-${c.id}" class="text-sm font-semibold text-blue-700 mb-2 mr-2">${originalOcr} <button onclick="toggleEdit(${c.id})" class="text-blue-600 hover:text-blue-800 ml-1">✏️</button></div>
                </div>
                
                <div id="edit-box-${c.id}" class="hidden mt-2">
                    <input type="text" id="input-${c.id}" value="${userValue}" class="w-full text-sm border border-gray-300 rounded px-2 py-1 focus:ring-1 focus:ring-blue-500 focus:outline-none mb-2">
                    <button id="btn-${c.id}" onclick="submitFeedback(${pred.id}, ${c.id})" class="w-full mt-2 py-1 rounded text-sm font-semibold transition bg-blue-600 hover:bg-blue-700 text-white shadow-sm">
                        Save Changes
                    </button>
                </div>
            `;
        } else {
            valueHtml = `
                <div class="text-xs text-gray-500 flex justify-between items-center mb-1">
                    <span>OCR Value: </span>
                    <div id="display-val-${c.id}" class="text-sm font-semibold text-gray-800 mb-2 mr-2">${originalOcr} <button onclick="toggleEdit(${c.id})" class="text-blue-600 hover:text-blue-800 ml-1">✏️</button></div>
                </div>
                
                <div id="edit-box-${c.id}" class="hidden mt-2">
                    <input type="text" id="input-${c.id}" value="${userValue}" class="w-full text-sm border border-gray-300 rounded px-2 py-1 focus:ring-1 focus:ring-blue-500 focus:outline-none mb-2">
                </div>
            `;
        }
    } else {
        valueHtml = `
            <div class="flex-1 flex flex-col items-center justify-center py-4 bg-gray-50 rounded animate-pulse border border-gray-100">
                <svg class="animate-spin h-6 w-6 text-blue-500 mb-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <div class="text-xs text-gray-500 font-medium">Processing OCR...</div>
            </div>`;
    }

    let actionButtonsHtml = '';
    if (pred) {
        const currentState = reloadStates[c.id] || 'default';
        let reloadBtnText = '↻ Reload OCR';
        if (currentState === 'salt') reloadBtnText = '↻ Reload (Tesseract)';
        else if (currentState === 'tesseract') reloadBtnText = '↻ Reload (Paddle)';
        else if (currentState === 'paddle') reloadBtnText = '↻ Reload (Salt)';

        if (!(isHuman || isAccepted)) {
            actionButtonsHtml = `
            <div class="flex space-x-2 mt-auto pt-2">
                <button id="btn-${c.id}" onclick="submitFeedback(${pred.id}, ${c.id})" class="flex-1 py-1.5 rounded text-xs font-semibold transition bg-blue-600 hover:bg-blue-700 text-white shadow-sm">
                    Accept
                </button>
                <button onclick="reloadCell(${c.id})" class="flex-1 py-1.5 border border-gray-300 text-gray-700 hover:bg-gray-100 rounded transition text-xs font-semibold shadow-sm">
                    ${reloadBtnText}
                </button>
            </div>`;
        } else {
            actionButtonsHtml = `
            <button onclick="reloadCell(${c.id})" class="mt-2 w-full text-xs py-1.5 border border-gray-300 text-gray-700 hover:bg-gray-100 rounded transition font-semibold shadow-sm">
                ${reloadBtnText}
            </button>`;
        }
    }

    return `
        <div id="loader-${c.id}" class="hidden absolute inset-0 bg-white bg-opacity-80 flex flex-col justify-center items-center z-10 backdrop-blur-[1px]">
            <svg class="animate-spin h-6 w-6 text-blue-600 mb-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
            <span class="text-xs font-semibold text-blue-700">Processing...</span>
        </div>

        <div class="bg-gray-50 px-3 py-2 border-b ${borderColor} flex justify-between items-center">
            <span class="text-xs font-bold text-gray-700 break-all" title="CELL ${c.id}">${displayTitle}</span>
            ${sourceBadge}
        </div>
        
        <div class="p-3 flex-1 flex flex-col">
            <!-- Image -->
            <div class="w-full h-24 bg-gray-100 rounded border border-gray-200 mb-3 flex items-center justify-center overflow-hidden">
                <img src="/cell-image/${c.id}" alt="Cell Image" class="max-w-full max-h-full object-contain cursor-pointer hover:scale-105 transition transform" onclick="window.open('/cell-image/${c.id}', '_blank')">
            </div>
            <!-- Details -->
            <div class="flex-1 min-w-0 flex flex-col">
                ${valueHtml}
            </div>
            
            <div class="mt-auto pt-2 border-t ${borderColor} flex flex-col justify-between items-start">
                <div class="flex justify-between items-center w-full">
                    <span class="text-[10px] uppercase text-gray-500 font-semibold tracking-wider">Confidence</span>
                    <span class="text-xs font-bold ${confColor}">${confText}</span>
                </div>
            </div>
            ${actionButtonsHtml}
        </div>
    `;
}



window.changePage = function (delta) {
    window.renderReviewList(false, currentPage + delta);
    document.querySelector('main').scrollTo(0, 0);
}

window.toggleEdit = function (cellId) {
    const editBox = document.getElementById(`edit-box-${cellId}`);
    const displayVal = document.getElementById(`display-val-${cellId}`);

    if (editBox) {
        editBox.classList.toggle('hidden');
        if (displayVal) {
            displayVal.classList.toggle('hidden');
        }
    }
}

window.submitFeedback = async function (predId, componentId) {
    const inputEl = document.getElementById(`input-${componentId}`);
    const loaderEl = document.getElementById(`loader-${componentId}`);

    if (!inputEl) return;

    if (loaderEl) loaderEl.classList.remove('hidden');

    const value = inputEl.value;
    try {
        await fetch('/feedback/' + predId, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prediction_id: predId,
                component_id: componentId,
                is_accepted: true,
                user_value: value
            })
        });

        // Refresh all cells silently to grab cascading Hash Matches
        if (currentDocumentId) {
            const freshRes = await fetch(`/components/${currentDocumentId}?t=${new Date().getTime()}`);
            if (freshRes.ok) {
                const allComps = await freshRes.json();
                cells = allComps.filter(c => c.component_type === 'CELL');
                
                const sourceVal = document.getElementById('filter-source') ? document.getElementById('filter-source').value : 'all';
                const filterVal = document.getElementById('filter-confidence') ? document.getElementById('filter-confidence').value : 'all';
                
                // Re-render ONLY the cards currently visible on the page without clearing the container!
                cells.forEach(c => {
                    const cardEl = document.getElementById(`card-${c.id}`);
                    if (cardEl) {
                        cardEl.innerHTML = getCardInnerHtml(c);
                        
                        // Check if it still matches the filter
                        let matches = true;
                        if (sourceVal !== 'all') {
                            const pred = (c.predictions && c.predictions.length > 0) ? c.predictions[0] : null;
                            if (!pred) {
                                matches = false;
                            } else {
                                let source = pred.source || 'ocr';
                                const fb = (pred.feedback && pred.feedback.length > 0) ? pred.feedback[0] : null;
                                const isAccepted = fb && fb.is_accepted && fb.source !== 'hash_match';
                                if (isAccepted) {
                                    if (fb.user_value !== pred.predicted_text) source = 'human';
                                    else source = 'human_verified'; // Distinguish verified vs edited
                                }
                                
                                if (sourceVal === 'ocr') {
                                    matches = ['ocr', 'paddle', 'tesseract', 'paddleocr'].includes(source);
                                } else if (sourceVal === 'ml') {
                                    matches = source.startsWith('ml_');
                                } else {
                                    matches = (source === sourceVal);
                                }
                            }
                        }
                        
                        // Handle Confidence Filter
                        if (matches && filterVal !== 'all') {
                            const pred = (c.predictions && c.predictions.length > 0) ? c.predictions[0] : null;
                            const fb = (pred && pred.feedback && pred.feedback.length > 0) ? pred.feedback[0] : null;
                            const isAccepted = fb && fb.is_accepted && fb.source !== 'hash_match';
                            let conf = pred ? pred.confidence * 100 : 0;
                            if (isAccepted) conf = 100;
                            
                            if (filterVal === 'high' && conf < 90) matches = false;
                            else if (filterVal === 'medium' && (conf >= 90 || conf < 50)) matches = false;
                            else if (filterVal === 'low' && conf >= 50) matches = false;
                        }
                        
                        if (!matches) {
                            cardEl.style.transition = "opacity 0.4s ease-out, transform 0.4s ease-out";
                            cardEl.style.opacity = "0";
                            cardEl.style.transform = "scale(0.95)";
                            setTimeout(() => {
                                cardEl.remove();
                                const countEl = document.getElementById('card-count');
                                if (countEl) countEl.textContent = parseInt(countEl.textContent) - 1;
                            }, 400);
                        }
                    }
                });
            }
        }
    } catch (e) {
        console.error(e);
        if (loaderEl) loaderEl.classList.add('hidden');
    }
}

window.acceptAllFiltered = async function () {
    if (!confirm("Are you sure you want to accept the current values for all displayed cells?")) return;

    const filterVal = document.getElementById('filter-confidence').value;

    let filtered = [...cells];
    if (filterVal !== 'all') {
        const threshold = parseInt(filterVal) / 100.0;
        filtered = filtered.filter(c => {
            const pred = (c.predictions && c.predictions.length > 0) ? c.predictions[0] : null;
            return pred && pred.confidence < threshold;
        });
    }

    // Only accept those that are NOT already accepted
    const predsToAccept = [];
    filtered.forEach(c => {
        if (c.predictions && c.predictions.length > 0) {
            const p = c.predictions[0];
            const isAcc = p.feedback && p.feedback.length > 0 && p.feedback[0].is_accepted;
            if (!isAcc) {
                predsToAccept.push(p.id);
            }
        }
    });

    if (predsToAccept.length === 0) {
        alert("All displayed predictions are already accepted or have no data.");
        return;
    }

    loading.classList.remove('hidden');
    try {
        await fetch('/feedback/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prediction_ids: predsToAccept, is_accepted: true })
        });

        // Reload all data
        await window.selectDocument(currentDocumentId);
    } catch (e) {
        console.error(e);
        alert('Bulk accept failed');
    } finally {
        loading.classList.add('hidden');
    }
}

window.runOcr = async function (componentId) {
    try {
        const res = await fetch(`/ocr-cell/${componentId}`, { method: 'POST' });
        if (res.ok) {
            await window.selectDocument(currentDocumentId);
        }
    } catch (e) {
        console.error(e);
    }
}

// Init
;(function() {
    const urlParams = new URLSearchParams(window.location.search);
    
    if (urlParams.has('sort')) {
        const el = document.getElementById('sort-confidence');
        if (el) el.value = urlParams.get('sort');
    }
    
    if (urlParams.has('source')) {
        const el = document.getElementById('filter-source');
        if (el) el.value = urlParams.get('source');
    }
    
    if (urlParams.has('search')) {
        const el = document.getElementById('search-input');
        if (el) el.value = urlParams.get('search');
    }
    
    if (urlParams.has('page')) {
        currentPage = parseInt(urlParams.get('page')) || 1;
    }
    
    loadDocuments();
})();
