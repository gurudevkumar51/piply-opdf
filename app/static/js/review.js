let currentDocumentId = null;
let cells = [];
let currentPage = 1;
const itemsPerPage = 60;
// Every type that carries text a person can read and correct. Mirrors
// ComponentType.TEXTUAL in the library — the previous list here held only
// CELL, KEY_VALUE and WORD, so a document without a table showed nothing at
// all and headers and footers were never reviewable anywhere.
const REVIEWABLE_TYPES = [
    'CELL', 'KEY_VALUE', 'WORD', 'SENTENCE', 'PARAGRAPH',
    'LIST_ITEM', 'HEADER', 'FOOTER', 'TITLE',
];

const docSelector = document.getElementById('doc-selector');
const reviewList = document.getElementById('review-list');
const loading = document.getElementById('loading');

function isReviewableComponent(component) {
    return component && REVIEWABLE_TYPES.includes(component.component_type);
}

// A person checks the smallest unit, not the container around it: if a header
// was split into words, the words are what gets corrected and showing the
// header as well would ask the same question twice.
function isLeafForReview(component, byParent) {
    if (!isReviewableComponent(component)) return false;
    const children = byParent.get(component.id) || [];
    return !children.some(isReviewableComponent);
}

function collectReviewUnits(allComps) {
    const byParent = new Map();
    allComps.forEach(c => {
        if (c.parent_id == null) return;
        if (!byParent.has(c.parent_id)) byParent.set(c.parent_id, []);
        byParent.get(c.parent_id).push(c);
    });
    return allComps.filter(c => isLeafForReview(c, byParent));
}

function getDisplayTitle(component) {
    let displayTitle = `${component.component_type} ${component.id}`;
    if (component.component_type === 'KEY_VALUE') displayTitle = `KEY-VALUE ${component.id}`;
    if (component.component_type === 'WORD') displayTitle = `WORD ${component.id}`;

    if (component.component_type === 'CELL' && component.manifest_path) {
        const match = component.manifest_path.match(/_r(\d+)_c(\d+)\.png$/);
        if (match) displayTitle = `CELL ${match[1]}-${match[2]}`;
    }

    return displayTitle;
}

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

        // update review unit locally
        const cell = cells.find(c => c.id === componentId);
        if (cell) {
            cell.predictions = updatedComponent.predictions;
        }
        
        reloadStates[componentId] = nextState;

        const card = document.getElementById(`card-${componentId}`);
        if (card) {
            renderCard(card, cell);
            // Update the button text inside the new HTML
            const btn = card.querySelector(`button[onclick="reloadCell(${componentId})"]`);
            if (btn) btn.textContent = nextBtnText;
        }
    } catch (e) {
        console.error("Failed to run OCR for review unit", e);
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
            toast('Could not start processing.', 'bad');
        }
    } catch (e) {
        console.error(e);
        toast('Something went wrong.', 'bad');
    } finally {
        loading.classList.add('hidden');
    }
}

window.resumeOcr = async function() {
    if (!currentDocumentId) return;
    const btnResume = document.getElementById('btn-resume-ocr');
    if (btnResume) {
        btnResume.disabled = true;
        btnResume.innerHTML = `<span class="spinner spinner-sm spinner-on-ink"></span> Resuming…`;
    }
    try {
        const res = await fetch(`/resume-ocr/${currentDocumentId}`, { method: 'POST' });
        if (res.ok) {
            checkAndPollOcr();
        } else {
            toast('Could not resume OCR.', 'bad');
            if (btnResume) {
                btnResume.disabled = false;
                btnResume.innerHTML = 'Resume OCR';
            }
        }
    } catch (e) {
        console.error(e);
        toast('Something went wrong.', 'bad');
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
        cells = collectReviewUnits(allComps);

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
        btn.className = `chip${selectedPages.has(p) ? ' is-active' : ''}`;
        btn.textContent = `Page ${p}`;
        btn.onclick = () => {
            if (selectedPages.has(p)) selectedPages.delete(p);
            else selectedPages.add(p);
            btn.className = `chip${selectedPages.has(p) ? ' is-active' : ''}`;
            window.renderReviewList();
        };
        pageFilters.appendChild(btn);
    });

    tableFilters.innerHTML = '';
    Array.from(allTables).sort().forEach(t => {
        const btn = document.createElement('button');
        const displayT = t.replace('borderless_', 'B-').replace('_', ' ');
        btn.className = `chip${selectedTables.has(t) ? ' is-active-accent' : ''}`;
        btn.textContent = displayT;
        btn.onclick = () => {
            if (selectedTables.has(t)) selectedTables.delete(t);
            else selectedTables.add(t);
            btn.className = `chip${selectedTables.has(t) ? ' is-active-accent' : ''}`;
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
                const newCells = collectReviewUnits(allComps);
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
                        if (cardEl) renderCard(cardEl, newC);
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
            let displayTitle = getDisplayTitle(c);
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
                if (fb.source === 'knowledge_base') {
                    // Keep the original pred.source (exact_match or near_match)
                } else if (fb.user_value !== pred.predicted_text) {
                    source = 'human';
                } else {
                    source = 'human_verified';
                }
            }
            
            if (sourceVal === 'ocr') {
                return ['ocr', 'paddle', 'tesseract', 'paddleocr'].includes(source);
            }
            if (sourceVal === 'knowledge_base') {
                return ['exact_match', 'near_match'].includes(source);
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
        reviewList.innerHTML = '<div class="col-span-full empty-state">No review units match your filters.</div>';
        const pagControls = document.getElementById('pagination-controls');
        if (pagControls) pagControls.classList.add('hidden');
        return;
    }

    const totalPages = Math.ceil(filtered.length / itemsPerPage);
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const startIdx = (currentPage - 1) * itemsPerPage;
    const paginated = filtered.slice(startIdx, startIdx + itemsPerPage);

    renderGrouped(paginated);

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

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

/* Single source of truth for a review unit's display state, so the card
   element's tone class and its inner markup can never drift apart. */
function describeCard(c) {
    const pred = (c.predictions && c.predictions.length > 0) ? c.predictions[0] : null;

    const state = {
        pred,
        isAccepted: false,
        isHuman: false,
        userValue: '',
        originalOcr: '',
        confText: 'No OCR data',
        confClass: 'conf-muted',
        tone: '',
        valueClass: '',
        sourceBadge: '',
    };

    if (!pred) return state;

    const fb = (pred.feedback && pred.feedback.length > 0) ? pred.feedback[0] : null;
    state.isAccepted = fb && fb.is_accepted && fb.source !== 'hash_match';
    state.originalOcr = pred.predicted_text;
    state.userValue = state.isAccepted ? fb.user_value : state.originalOcr;
    state.isHuman = state.isAccepted && (state.userValue !== state.originalOcr);

    let normalizedConf = pred.confidence;
    if (normalizedConf > 1.0) normalizedConf = normalizedConf / 100.0;
    const confPct = Math.round(normalizedConf * 100);

    const source = pred.source || 'ocr';
    let sourceDisplay = source.toUpperCase();
    if (source === 'exact_match') sourceDisplay = 'Exact hash match';
    else if (source.startsWith('ml_')) sourceDisplay = `ML · ${source.replace('ml_', '')}`;
    else if (source === 'paddle' || source === 'paddleocr') sourceDisplay = 'OCR · Paddle';
    else if (source === 'tesseract') sourceDisplay = 'OCR · Tesseract';
    else if (source === 'ocr') sourceDisplay = 'OCR';

    if (state.isHuman) {
        state.confText = '100% · Human';
        state.confClass = 'conf-ok';
        state.tone = 'tone-ok';
        state.valueClass = 'is-human';
        state.sourceBadge = `<span class="badge badge-ok">Human</span>`;
    } else if (state.isAccepted) {
        if (fb.source === 'knowledge_base') {
            state.confText = '100% · KB match';
            state.confClass = 'conf-accent';
            state.tone = 'tone-accent';
            state.valueClass = 'is-kb';
            state.sourceBadge = `<span class="badge badge-accent">Knowledge base</span>`;
        } else {
            state.confText = '100% · Verified';
            state.confClass = 'conf-info';
            state.tone = 'tone-info';
            state.valueClass = 'is-verified';
            state.sourceBadge = `<span class="badge badge-info">Verified OCR</span>`;
        }
    } else {
        state.confText = `${confPct}%`;
        const badgeTone = (source === 'exact_match') ? 'badge-accent' : '';
        state.sourceBadge = `<span class="badge ${badgeTone}">${escapeHtml(sourceDisplay)}</span>`;

        if (confPct >= 90) { state.confClass = 'conf-ok'; state.tone = 'tone-ok'; }
        else if (confPct >= 80) { state.confClass = 'conf-warn'; state.tone = 'tone-warn'; }
        else { state.confClass = 'conf-bad'; state.tone = 'tone-bad'; }
    }

    return state;
}

/* Renders a review unit into an existing card element — sets both the tone
   class and the inner markup. Use this everywhere instead of assigning
   innerHTML directly, otherwise a re-rendered card keeps a stale tone. */
// A table cell belongs to a row, and a person checks a row at a time — reading
// across "Name | GAJENDRA NARAYAN" makes sense in a way that a wall of loose
// cells does not. The database does not link a cell to its row (a cell's parent
// is the TABLE), but the crop path records it: `table_001_r0_c3.png`.
function cellRowKey(c) {
    if (c.component_type !== 'CELL' || !c.manifest_path) return null;
    const path = c.manifest_path.replace(/\\/g, '/');
    const table = path.match(/(borderless_table_\d+|table_\d+)/i);
    const row = path.match(/_r(\d+)_/);
    if (!row) return null;
    return {
        key: `${table ? table[1].toLowerCase() : 'table'}|${row[1].padStart(4, '0')}`,
        table: table ? table[1].toLowerCase() : 'table',
        row: parseInt(row[1], 10),
        col: (path.match(/_c(\d+)\./) || [null, '0'])[1],
    };
}

function groupForReview(units) {
    const groups = new Map();
    const loose = [];

    units.forEach(c => {
        const info = cellRowKey(c);
        if (!info) { loose.push(c); return; }
        if (!groups.has(info.key)) {
            groups.set(info.key, { table: info.table, row: info.row, cells: [] });
        }
        groups.get(info.key).cells.push({ unit: c, col: parseInt(info.col, 10) });
    });

    groups.forEach(g => g.cells.sort((a, b) => a.col - b.col));
    return { groups: [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0])), loose };
}

function worstConfidence(units) {
    let worst = null;
    units.forEach(c => {
        const p = c.predictions && c.predictions.length ? c.predictions[0] : null;
        if (!p) return;
        if (worst === null || p.confidence < worst) worst = p.confidence;
    });
    return worst;
}

function renderGrouped(units) {
    const { groups, loose } = groupForReview(units);

    const cardGrid = () => {
        const grid = document.createElement('div');
        grid.className = 'review-card-grid';
        return grid;
    };

    if (loose.length) {
        const grid = cardGrid();
        loose.forEach(c => {
            const card = document.createElement('div');
            card.id = `card-${c.id}`;
            renderCard(card, c);
            grid.appendChild(card);
        });
        reviewList.appendChild(grid);
    }

    groups.forEach(([, group]) => {
        const block = document.createElement('section');
        block.className = 'review-row-group';

        const units = group.cells.map(c => c.unit);
        const worst = worstConfidence(units);
        const unread = units.filter(u => !u.predictions || !u.predictions.length).length;

        const head = document.createElement('header');
        head.className = 'review-row-head';
        head.innerHTML = `
            <span class="review-row-title">
                Row ${group.row + 1}
                <span class="review-row-table">${escapeHtmlSafe(group.table.replace(/_/g, ' '))}</span>
            </span>
            <span class="review-row-meta">
                <span class="label-micro num">${units.length} cells</span>
                ${unread ? `<span class="label-micro num">${unread} unread</span>` : ''}
                ${worst !== null ? `<span class="badge ${worst < 0.8 ? 'badge-bad' : worst < 0.95 ? 'badge-warn' : ''} num">${Math.round(worst * 100)}%</span>` : ''}
            </span>`;
        block.appendChild(head);

        const grid = cardGrid();
        group.cells.forEach(({ unit }) => {
            const card = document.createElement('div');
            card.id = `card-${unit.id}`;
            renderCard(card, unit);
            grid.appendChild(card);
        });
        block.appendChild(grid);
        reviewList.appendChild(block);
    });
}

function escapeHtmlSafe(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderCard(cardEl, c) {
    const state = describeCard(c);
    cardEl.className = `rcard ${state.tone}`.trim();
    cardEl.innerHTML = getCardInnerHtml(c, state);
}

function getCardInnerHtml(c, state) {
    if (!state) state = describeCard(c);

    const displayTitle = getDisplayTitle(c);
    const { pred, isAccepted, isHuman, userValue, originalOcr, confText, confClass, valueClass, sourceBadge } = state;

    const safeUser = escapeHtml(userValue);
    const safeOcr = escapeHtml(originalOcr);

    const editBox = (withSave) => `
        <div id="edit-box-${c.id}" class="hidden">
            <input type="text" id="input-${c.id}" value="${safeUser}" class="field field-sm">
            ${withSave ? `
            <button id="btn-${c.id}" onclick="submitFeedback(${pred.id}, ${c.id})" class="btn btn-primary btn-sm btn-block mt-2">
                Save changes
            </button>` : ''}
        </div>`;

    let valueHtml = '';
    if (pred) {
        if (isHuman) {
            valueHtml = `
                <div>
                    <div class="label-micro mb-1">OCR original</div>
                    <div class="text-xs rcard-strike mb-2">${safeOcr}</div>
                    <div class="label-micro mb-1">Human value</div>
                    <div id="display-val-${c.id}" class="rcard-value ${valueClass}">
                        ${safeUser}
                        <button onclick="toggleEdit(${c.id})" class="icon-btn" title="Edit text">✎</button>
                    </div>
                </div>
                ${editBox(true)}`;
        } else if (isAccepted) {
            valueHtml = `
                <div>
                    <div class="label-micro mb-1">Verified value</div>
                    <div id="display-val-${c.id}" class="rcard-value ${valueClass}">
                        ${safeOcr}
                        <button onclick="toggleEdit(${c.id})" class="icon-btn" title="Edit text">✎</button>
                    </div>
                </div>
                ${editBox(true)}`;
        } else {
            valueHtml = `
                <div>
                    <div class="label-micro mb-1">OCR value</div>
                    <div id="display-val-${c.id}" class="rcard-value">
                        ${safeOcr}
                        <button onclick="toggleEdit(${c.id})" class="icon-btn" title="Edit text">✎</button>
                    </div>
                </div>
                ${editBox(false)}`;
        }
    } else {
        valueHtml = `
            <div class="flex-1 flex flex-col items-center justify-center gap-2 py-5 surface-2" style="border-radius: var(--r-sm);">
                <div class="spinner"></div>
                <div class="label-micro">Processing OCR…</div>
            </div>`;
    }

    let actionButtonsHtml = '';
    if (pred) {
        const currentState = reloadStates[c.id] || 'default';
        let reloadBtnText = 'Reload OCR';
        if (currentState === 'salt') reloadBtnText = 'Reload · Tesseract';
        else if (currentState === 'tesseract') reloadBtnText = 'Reload · Paddle';
        else if (currentState === 'paddle') reloadBtnText = 'Reload · Salt';

        if (!(isHuman || isAccepted)) {
            actionButtonsHtml = `
            <div class="flex gap-2 mt-2">
                <button id="btn-${c.id}" onclick="submitFeedback(${pred.id}, ${c.id})" class="btn btn-primary btn-sm flex-1">Accept</button>
                <button onclick="reloadCell(${c.id})" class="btn btn-sm flex-1">${reloadBtnText}</button>
            </div>`;
        } else {
            actionButtonsHtml = `
            <button onclick="reloadCell(${c.id})" class="btn btn-sm btn-block mt-2">${reloadBtnText}</button>`;
        }
    }

    return `
        <div id="loader-${c.id}" class="hidden overlay">
            <div class="spinner"></div>
            <span class="label-micro">Processing…</span>
        </div>

        <div class="rcard-head">
            <span class="rcard-title" title="${escapeHtml(c.component_type)} ${c.id}">${escapeHtml(displayTitle)}</span>
            ${sourceBadge}
        </div>

        <div class="rcard-body">
            <div class="rcard-thumb">
                <img src="/cell-image/${c.id}" alt="Component crop"
                     onclick="window.open('/cell-image/${c.id}', '_blank')">
            </div>

            <div class="flex-1 min-w-0 flex flex-col gap-2">
                ${valueHtml}
            </div>

            <div class="rcard-foot">
                <span class="label-micro">Confidence</span>
                <span class="conf ${confClass}">${confText}</span>
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

        // Refresh visible review units silently after feedback.
        if (currentDocumentId) {
            const freshRes = await fetch(`/components/${currentDocumentId}?t=${new Date().getTime()}`);
            if (freshRes.ok) {
                const allComps = await freshRes.json();
                cells = collectReviewUnits(allComps);
                
                const sourceVal = document.getElementById('filter-source') ? document.getElementById('filter-source').value : 'all';
                const filterVal = document.getElementById('filter-confidence') ? document.getElementById('filter-confidence').value : 'all';
                
                // Re-render ONLY the cards currently visible on the page without clearing the container!
                cells.forEach(c => {
                    const cardEl = document.getElementById(`card-${c.id}`);
                    if (cardEl) {
                        renderCard(cardEl, c);

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
    if (!confirm("Are you sure you want to accept the current values for all displayed review units?")) return;

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
    const userValues = {};
    filtered.forEach(c => {
        if (c.predictions && c.predictions.length > 0) {
            const p = c.predictions[0];
            const isAcc = p.feedback && p.feedback.length > 0 && p.feedback[0].is_accepted;
            if (!isAcc) {
                predsToAccept.push(p.id);
                // Try to get the user-typed value if the input exists
                const inputEl = document.getElementById(`input-${c.id}`);
                if (inputEl) {
                    userValues[p.id] = inputEl.value;
                }
            }
        }
    });

    if (predsToAccept.length === 0) {
        toast('Everything shown is already accepted or has no data.', 'info');
        return;
    }

    loading.classList.remove('hidden');
    try {
        await fetch('/feedback/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prediction_ids: predsToAccept, is_accepted: true, user_values: userValues })
        });

        // Reload all data
        await window.selectDocument(currentDocumentId);
    } catch (e) {
        console.error(e);
        toast('Bulk accept failed.', 'bad');
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
