/* ═══════════════════════════════════════════════
   O SERIES PLATFORM — AUTH HELPERS
   ═══════════════════════════════════════════════ */

const API = 'https://ogenti-api-production.up.railway.app';

const Auth = {
    getToken: () => localStorage.getItem('og_token'),
    setToken: (t) => localStorage.setItem('og_token', t),
    clearToken: () => localStorage.removeItem('og_token'),
    getUser: () => {
        const u = localStorage.getItem('og_user');
        return u ? JSON.parse(u) : null;
    },
    setUser: (u) => localStorage.setItem('og_user', JSON.stringify(u)),
    clearUser: () => localStorage.removeItem('og_user'),

    isLoggedIn: () => !!localStorage.getItem('og_token'),

    logout: () => {
        localStorage.removeItem('og_token');
        localStorage.removeItem('og_user');
        window.location.href = '/platform/login.html';
    },

    // Redirect to login if not authenticated
    requireAuth: () => {
        if (!Auth.isLoggedIn()) {
            window.location.href = '/platform/login.html';
            return false;
        }
        return true;
    },

    // Redirect to account if already authenticated
    redirectIfAuth: () => {
        if (Auth.isLoggedIn()) {
            window.location.href = '/platform/account.html';
        }
    },

    headers: () => ({
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${Auth.getToken()}`
    }),

    // Fetch user info and cache it
    fetchUser: async () => {
        try {
            const res = await fetch(API + '/api/auth/me', {
                headers: Auth.headers()
            });
            if (!res.ok) {
                Auth.logout();
                return null;
            }
            const data = await res.json();
            Auth.setUser(data);
            return data;
        } catch {
            return null;
        }
    }
};

// ── API helper ──
async function api(method, path, body = null) {
    const opts = {
        method,
        headers: Auth.headers()
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(API + path, opts);
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.detail || 'Something went wrong');
    }
    return data;
}

// ── Message display ──
function showMsg(id, text, type = 'error') {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = `msg show msg-${type}`;
    el.textContent = text;
}
function hideMsg(id) {
    const el = document.getElementById(id);
    if (el) { el.className = 'msg'; el.textContent = ''; }
}

// ── Render nav bar ──
function renderNav(activePage = '') {
    const user = Auth.getUser();
    const loggedIn = Auth.isLoggedIn();

    const nav = document.getElementById('main-nav');
    if (!nav) return;

    let links = '';
    if (loggedIn) {
        // OGENTI sub-menu (text compression)
        links += `<div class="nav-group">
            <span class="nav-group-label" style="color:var(--pink)">OGENTI</span>
            <a href="/platform/training.html" class="nav-link${activePage === 'training' ? ' active' : ''}">TRAIN</a>
            <a href="/monitor" class="nav-link${activePage === 'monitor' ? ' active' : ''}" title="Training Monitor">MONITOR</a>
        </div>`;

        // OVISEN sub-menu (image embedding compression)
        links += `<div class="nav-group">
            <span class="nav-group-label" style="color:var(--cyan)">OVISEN</span>
            <a href="/platform/ovisen_training.html" class="nav-link${activePage === 'ovisen_training' ? ' active' : ''}">TRAIN</a>
            <a href="/platform/ovisen_adapters.html" class="nav-link${activePage === 'ovisen_adapters' ? ' active' : ''}">ADAPTERS</a>
        </div>`;

        // Shared platform pages
        links += `<div class="nav-group">
            <span class="nav-group-label" style="color:var(--text-dim)">PLATFORM</span>
            <a href="/platform/account.html" class="nav-link${activePage === 'account' ? ' active' : ''}">ACCOUNT</a>
            <a href="/platform/api_keys.html" class="nav-link${activePage === 'api_keys' ? ' active' : ''}">API KEYS</a>
            <a href="/platform/billing.html" class="nav-link${activePage === 'billing' ? ' active' : ''}">BILLING</a>
            <a href="/platform/usage.html" class="nav-link${activePage === 'usage' ? ' active' : ''}">USAGE</a>
        </div>`;
    }

    const userSection = loggedIn
        ? `<div class="nav-user">
               ${user ? `<span class="nav-tier">${(user.tier || 'FREE').toUpperCase()}</span>` : ''}
               ${user ? `<span class="nav-credits">${Number(user.credits || 0).toLocaleString()} CR</span>` : ''}
               <a href="#" onclick="Auth.logout();return false" class="nav-link" style="color:var(--red)">LOGOUT</a>
           </div>`
        : `<div class="nav-user">
               <a href="/platform/login.html" class="nav-link">LOGIN</a>
               <a href="/platform/signup.html" class="btn btn-primary btn-small" style="width:auto">SIGN UP</a>
           </div>`;

    nav.innerHTML = `
        <a href="https://ogenti.com" class="nav-brand">
            O SERIES <span class="nav-tag">PLATFORM</span>
        </a>
        <div class="nav-links">${links}</div>
        ${userSection}
    `;
}

// ── Init nav on load ──
document.addEventListener('DOMContentLoaded', () => {
    renderNav(document.body.dataset.page || '');
});

// ── Format helpers ──
function formatDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
function formatCredits(n) {
    return Number(n || 0).toLocaleString();
}
