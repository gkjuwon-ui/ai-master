/* ═══════════════════════════════════════════════
   OGENTI PLATFORM — AUTH HELPERS
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
        const pages = [
            ['account', 'ACCOUNT'],
            ['training', 'TRAIN'],
            ['api_keys', 'API KEYS'],
            ['billing', 'BILLING'],
            ['usage', 'USAGE']
        ];
        links = pages.map(([p, label]) =>
            `<a href="/platform/${p}.html" class="nav-link${activePage === p ? ' active' : ''}">${label}</a>`
        ).join('');
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
            OGENTI <span class="nav-tag">PLATFORM</span>
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
