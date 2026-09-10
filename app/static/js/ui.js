/* Shared UI behaviour: theme and toasts.
 *
 * Loaded on every page from base.html, before the page-specific scripts, so
 * they can call `toast(...)` without each one carrying its own copy.
 */

// ── Theme ───────────────────────────────────────────────────────────────────
//
// Applied before first paint (see the inline snippet in base.html) so the page
// never flashes light before switching to dark.

(function theme() {
    const KEY = 'piply-theme';

    function apply(name) {
        document.documentElement.setAttribute('data-theme', name);
        try { localStorage.setItem(KEY, name); } catch (e) { /* private mode */ }
    }

    window.toggleTheme = function () {
        const now = document.documentElement.getAttribute('data-theme');
        apply(now === 'dark' ? 'light' : 'dark');
    };

    // If the user has never chosen, follow the operating system.
    let stored = null;
    try { stored = localStorage.getItem(KEY); } catch (e) { /* ignore */ }
    if (!stored && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        apply('dark');
    }
})();

// ── Toasts ──────────────────────────────────────────────────────────────────
//
// window.alert() blocks the page and cannot be styled. A modal stop sign for
// "accepted 14 predictions" is the wrong shape of feedback — the operator
// should be able to keep working while it fades.

window.toast = function (message, kind = 'info', ms = 3500) {
    let stack = document.getElementById('toast-stack');
    if (!stack) {
        stack = document.createElement('div');
        stack.id = 'toast-stack';
        document.body.appendChild(stack);
    }

    const el = document.createElement('div');
    el.className = `toast toast-${kind}`;
    el.setAttribute('role', kind === 'bad' ? 'alert' : 'status');
    el.textContent = message;
    stack.appendChild(el);

    const remove = () => {
        el.classList.add('is-leaving');
        setTimeout(() => el.remove(), 200);
    };
    el.addEventListener('click', remove);
    setTimeout(remove, ms);
};

// ── Loading skeletons ───────────────────────────────────────────────────────
//
// Shown while a list is being fetched. A skeleton says "content is coming and
// roughly this shape"; a spinner says only "wait".

window.skeletonCards = function (container, count = 8) {
    if (!container) return;
    container.innerHTML = '';
    const grid = document.createElement('div');
    grid.className = 'review-card-grid';
    for (let i = 0; i < count; i++) {
        const card = document.createElement('div');
        card.className = 'skeleton';
        card.innerHTML = `
            <div class="skeleton-line skeleton-block"></div>
            <div class="skeleton-line"></div>
            <div class="skeleton-line"></div>`;
        grid.appendChild(card);
    }
    container.appendChild(grid);
};
