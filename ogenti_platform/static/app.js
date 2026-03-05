/* ═══════════════════════════════════════════════
   SERIES PLATFORM — AUTH HELPERS
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

    let productTabs = '';
    let platformLinks = '';
    if (loggedIn) {
        const products = [
            { id: 'ogenti', label: 'OGENTI', color: 'var(--pink)', trainPage: 'training', trainUrl: '/platform/training.html', monitorUrl: '/monitor?product=ogenti' },
            { id: 'ovisen', label: 'OVISEN', color: 'var(--cyan)', trainPage: 'ovisen_training', trainUrl: '/platform/ovisen_training.html', monitorUrl: '/monitor?product=ovisen' },
            { id: 'phiren', label: 'PHIREN', color: 'var(--green)', trainPage: 'phiren_training', trainUrl: '/platform/phiren_training.html', monitorUrl: '/monitor?product=phiren' },
            { id: 'parhen', label: 'PARHEN', color: 'var(--orange)', trainPage: 'parhen_training', trainUrl: '/platform/parhen_training.html', monitorUrl: '/monitor?product=parhen' },
            { id: 'murhen', label: 'MURHEN', color: 'var(--yellow)', trainPage: 'murhen_training', trainUrl: '/platform/murhen_training.html', monitorUrl: '/monitor?product=murhen' },
        ];

        productTabs = products.map(p => {
            const isActive = activePage === p.trainPage || activePage === p.id + '_monitor';
            return `<div class="nav-product${isActive ? ' active' : ''}" style="--product-color:${p.color}">
                <span class="nav-product-label">${p.label}</span>
                <a href="${p.trainUrl}" class="nav-link${activePage === p.trainPage ? ' active' : ''}">TRAIN</a>
                <a href="${p.monitorUrl}" class="nav-link${activePage === p.id + '_monitor' ? ' active' : ''}">MONITOR</a>
            </div>`;
        }).join('');

        platformLinks = `<div class="nav-platform">
            <a href="/platform/account.html" class="nav-link${activePage === 'account' ? ' active' : ''}">ACCOUNT</a>
            <a href="/platform/api_keys.html" class="nav-link${activePage === 'api_keys' ? ' active' : ''}">API</a>
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
        <div class="nav-top">
            <a href="https://oseries.io" class="nav-brand">
                SERIES <span class="nav-tag">PLATFORM</span>
            </a>
            ${platformLinks}
            ${userSection}
        </div>
        ${loggedIn ? `<div class="nav-bottom">${productTabs}</div>` : ''}
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
