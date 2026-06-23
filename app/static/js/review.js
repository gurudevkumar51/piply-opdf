let currentDocumentId = null;
let cells = [];

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
    } catch (e) {
        console.error("Failed to load documents", e);
    }
}

window.reloadCell = async function (compId) {
    const loader = document.getElementById(`loader-${compId}`);
    if (loader) loader.classList.remove('hidden');

    try {
        const res = await fetch(`/ocr-cell/${compId}/reload`, {
            method: 'POST'
        });

        if (res.ok) {
            const updatedComp = await res.json();
            // Replace cell in state
            const idx = cells.findIndex(c => c.id === compId);
            if (idx !== -1) {
                cells[idx] = updatedComp;
                window.renderReviewList();
            }
        } else {
            console.error("Reload failed");
        }
    } catch (e) {
        console.error(e);
    } finally {
        if (loader) loader.classList.add('hidden');
    }
}

window.selectDocument = async function (docId) {
    if (!docId) return;
    currentDocumentId = docId;
    loading.classList.remove('hidden');

    try {
        const res = await fetch(`/components/${docId}`);
        const allComps = await res.json();
        cells = allComps.filter(c => c.component_type === 'CELL');

        // Auto run OCR for cells missing predictions? 
        // For now, we assume they should already be processed by backend.

        window.renderReviewList();
    } catch (e) {
        console.error("Failed to load components", e);
    } finally {
        loading.classList.add('hidden');
    }
}

window.renderReviewList = function () {
    reviewList.innerHTML = '';

    const filterVal = document.getElementById('filter-confidence').value;
    const sortVal = document.getElementById('sort-confidence').value;
    const searchVal = document.getElementById('search-input') ? document.getElementById('search-input').value.toLowerCase() : '';
    const showOnlyUnreviewed = document.getElementById('filter-unreviewed') ? document.getElementById('filter-unreviewed').checked : false;

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

    // Unreviewed Filter
    if (showOnlyUnreviewed) {
        filtered = filtered.filter(c => {
            const pred = (c.predictions && c.predictions.length > 0) ? c.predictions[0] : null;
            if (!pred) return true; // No prediction = unreviewed
            return !(pred.feedback && pred.feedback.length > 0 && pred.feedback[0].is_accepted);
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
    } // default is id order
    const countEl = document.getElementById('card-count');
    if (countEl) countEl.textContent = filtered.length;

    if (filtered.length === 0) {
        reviewList.innerHTML = '<div class="col-span-full text-center text-gray-500 mt-10">No cells match your filters.</div>';
        return;
    }

    filtered.forEach(c => {
        let displayTitle = `CELL ${c.id}`;
        if (c.manifest_path) {
            const match = c.manifest_path.match(/_r(\d+)_c(\d+)\.png$/);
            if (match) {
                displayTitle = `CELL ${match[1]}-${match[2]}`;
            }
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
            isAccepted = pred.feedback && pred.feedback.length > 0 && pred.feedback[0].is_accepted;
            originalOcr = pred.predicted_text;
            userValue = (pred.feedback && pred.feedback.length > 0) ? pred.feedback[0].user_value : originalOcr;

            // Check if human edited the value
            isHuman = isAccepted && (userValue !== originalOcr);

            const confPct = Math.round(pred.confidence * 100);

            if (isHuman) {
                confText = '100% (Human)';
                confColor = 'text-green-600';
                borderColor = 'border-green-300 shadow-green-100 shadow-sm';
                sourceBadge = `<span class="bg-green-100 text-green-800 text-[10px] font-bold px-1.5 py-0.5 rounded ml-2 uppercase">Source: Human</span>`;
            } else if (isAccepted) {
                confText = `${confPct}% (Verified)`;
                confColor = 'text-blue-600';
                borderColor = 'border-blue-300 shadow-blue-100 shadow-sm';
                sourceBadge = `<span class="bg-blue-100 text-blue-800 text-[10px] font-bold px-1.5 py-0.5 rounded ml-2 uppercase">Source: OCR</span>`;
            } else {
                confText = `${confPct}%`;
                sourceBadge = `<span class="bg-gray-100 text-gray-600 text-[10px] font-bold px-1.5 py-0.5 rounded ml-2 uppercase">Source: OCR</span>`;

                if (confPct >= 90) {
                    confColor = 'text-green-600';
                    borderColor = 'border-green-200';
                } else if (confPct >= 80) {
                    confColor = 'text-yellow-600';
                    borderColor = 'border-yellow-200';
                } else {
                    confColor = 'text-red-600';
                    borderColor = 'border-red-300 bg-red-50';
                }
            }
        }

        const card = document.createElement('div');
        card.className = `flex flex-col bg-white border ${borderColor} rounded-lg overflow-hidden transition hover:shadow-md`;

        let ocrBtnHtml = '';
        if (!pred) {
            ocrBtnHtml = `<button onclick="runOcr(${c.id})" class="text-xs bg-blue-100 hover:bg-blue-200 text-blue-800 px-2 py-1 rounded">Run OCR</button>`;
        }

        // Value Display Section
        let valueHtml = '';
        if (pred) {
            if (isHuman || isAccepted) {
                // Display both values if it's human modified
                valueHtml = `
                    <div class="text-xs text-gray-500 mb-1">OCR Original: <span class="line-through">${originalOcr}</span></div>
                    <div class="text-sm font-semibold text-gray-900 mb-2">Human Value: <span class="text-green-700">${userValue}</span></div>
                    <button onclick="toggleEdit(${c.id})" class="text-xs text-blue-600 hover:underline">✏️ Edit</button>
                    
                    <div id="edit-box-${c.id}" class="hidden mt-2">
                        <input type="text" id="input-${c.id}" value="${userValue}" class="w-full text-sm border border-gray-300 rounded px-2 py-1 focus:ring-1 focus:ring-blue-500 focus:outline-none">
                        <button id="btn-${c.id}" onclick="submitFeedback(${pred.id}, ${c.id})" class="w-full mt-2 py-1 rounded text-sm font-semibold transition bg-blue-600 hover:bg-blue-700 text-white shadow-sm">
                            Save Changes
                        </button>
                    </div>
                `;
            } else {
                // Default unverified view
                valueHtml = `
                    <div class="text-xs text-gray-500 flex justify-between items-center mb-1">
                        <span>OCR Value: </span>
                        <div id="display-val-${c.id}" class="text-sm font-semibold text-gray-800 mb-2">${originalOcr}</div>
                        <button onclick="toggleEdit(${c.id})" class="text-blue-600 hover:text-blue-800">✏️</button>
                    </div>
                    
                    
                    <div id="edit-box-${c.id}" class="hidden mt-2">
                        <input type="text" id="input-${c.id}" value="${userValue}" class="w-full text-sm border border-gray-300 rounded px-2 py-1 focus:ring-1 focus:ring-blue-500 focus:outline-none mb-2">
                    </div>
                    
                    <button id="btn-${c.id}" onclick="submitFeedback(${pred.id}, ${c.id})" class="w-full mt-auto py-1 rounded text-sm font-semibold transition bg-blue-600 hover:bg-blue-700 text-white shadow-sm">
                        Accept
                    </button>
                `;
            }
        } else {
            valueHtml = `
                <div class="text-xs text-gray-400 text-center italic flex-1 flex items-center justify-center">No predictions available.</div>
                ${ocrBtnHtml}
            `;
        }

        card.innerHTML = `
            <div class="bg-gray-100 px-3 py-2 flex justify-between items-center border-b border-gray-200">
                <div class="flex items-center">
                    <span class="font-bold text-gray-700 text-xs">${displayTitle}</span>
                    ${sourceBadge}
                </div>
                <div class="flex items-center space-x-2">
                    <span class="font-bold text-xs ${confColor}">${confText}</span>
                </div>
            </div>
            <div class="p-3 flex justify-center items-center bg-gray-50 h-24 overflow-hidden border-b border-gray-200 relative">
                <div id="loader-${c.id}" class="hidden absolute inset-0 bg-white bg-opacity-70 flex justify-center items-center">
                    <div class="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                </div>
                <img src="/cell-image/${c.id}" class="max-h-full max-w-full object-contain" onerror="this.style.display='none'">
            </div>
            <div class="p-3 flex-1 flex flex-col space-y-2 relative">
                ${valueHtml}
                ${pred ? `<button onclick="reloadCell(${c.id})" class="mt-2 text-xs w-full py-1 border border-gray-300 text-gray-600 hover:bg-gray-100 rounded transition font-medium">↻ Reload OCR</button>` : ''}
            </div>
        `;
        reviewList.appendChild(card);
    });
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

window.submitFeedback = async function (predictionId, cellId) {
    const inputEl = document.getElementById(`input-${cellId}`);
    const btnEl = document.getElementById(`btn-${cellId}`);
    const val = inputEl.value;

    btnEl.textContent = '...';

    try {
        await fetch(`/feedback/${predictionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_value: val, is_accepted: true })
        });

        // Update local state to reflect accepted status
        const cell = cells.find(c => c.id === cellId);
        if (cell && cell.predictions && cell.predictions.length > 0) {
            if (!cell.predictions[0].feedback) cell.predictions[0].feedback = [];
            cell.predictions[0].feedback[0] = { user_value: val, is_accepted: true };
        }

        // Re-render just the button/color logic
        window.renderReviewList();
    } catch (e) {
        console.error(e);
        alert('Failed to submit feedback');
        btnEl.textContent = 'Error';
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
loadDocuments();
