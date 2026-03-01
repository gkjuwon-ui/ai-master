/* ============================================================
   OGENTI Protocol Monitor — Dashboard Engine v2
   Real backend integration via WebSocket + REST fallback
   ============================================================ */

(() => {
    'use strict';

    // ─── Configuration ────────────────────────────────────────
    const CONFIG = {
        WS_RECONNECT_INTERVAL: 3000,
        WS_MAX_RETRIES: Infinity,
        CHART_HISTORY: 200,
        FEED_MAX: 50,

        PHASES: ['Warmup', 'Simple', 'Complex', 'Generalize', 'Universalize'],

        // API base — auto-detect from current host
        get API_BASE() {
            const loc = window.location;
            if (loc.port === '8000' || (loc.hostname !== 'localhost' && loc.hostname !== '127.0.0.1')) {
                return loc.origin;
            }
            return 'http://localhost:8000';
        },

        get WS_URL() {
            const base = this.API_BASE.replace(/^http/, 'ws');
            return `${base}/ws`;
        },
    };

    // ─── Connection State ─────────────────────────────────────
    const conn = {
        ws: null,
        connected: false,
        mode: 'connecting',  // 'live', 'demo', 'connecting', 'reconnecting'
        retries: 0,
        reconnectTimer: null,
    };

    // ─── Dashboard State ──────────────────────────────────────
    const state = {
        status: 'idle',
        episode: 0,
        phase: 0,
        phaseName: 'Warmup',
        paused: false,

        metrics: {
            compression: 1.0,
            fidelity: 0.0,
            avgTokens: 30,
            budget: 30.0,
            reward: 0.0,
        },

        history: {
            episodes: [],
            compression: [],
            fidelity: [],
            budget: [],
        },

        phaseHistory: [],
        vocab: [],
        startTime: Date.now(),
        epRate: 0,
    };

    // ─── DOM Helpers ──────────────────────────────────────────
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // ────────────────────────────────────────────────────────────
    // WebSocket Connection
    // ────────────────────────────────────────────────────────────

    function connectWebSocket() {
        if (conn.ws && conn.ws.readyState <= 1) return;

        conn.mode = 'connecting';
        updateConnectionUI();

        try {
            conn.ws = new WebSocket(CONFIG.WS_URL);
        } catch (e) {
            fallbackToDemo();
            return;
        }

        conn.ws.onopen = () => {
            conn.connected = true;
            conn.mode = 'live';
            conn.retries = 0;
            updateConnectionUI();
            console.log('[OGENTI] WebSocket connected');
        };

        conn.ws.onmessage = (evt) => {
            try {
                const msg = JSON.parse(evt.data);
                handleServerEvent(msg);
            } catch (e) {
                console.warn('[OGENTI] Bad message:', e);
            }
        };

        conn.ws.onclose = () => {
            conn.connected = false;
            if (conn.mode !== 'demo') {
                conn.mode = 'reconnecting';
                updateConnectionUI();
                scheduleReconnect();
            }
        };

        conn.ws.onerror = () => {
            conn.ws.close();
        };
    }

    function scheduleReconnect() {
        if (conn.reconnectTimer) return;
        conn.retries++;

        if (conn.retries > CONFIG.WS_MAX_RETRIES) {
            fallbackToDemo();
            return;
        }

        const delay = Math.min(CONFIG.WS_RECONNECT_INTERVAL * Math.pow(1.5, Math.min(conn.retries, 8)), 30000);
        conn.reconnectTimer = setTimeout(() => {
            conn.reconnectTimer = null;
            connectWebSocket();
        }, delay);
    }

    function fallbackToDemo() {
        conn.mode = 'demo';
        updateConnectionUI();
        console.log('[OGENTI] No server — running in demo mode');
        startDemoSimulation();
    }

    function sendCommand(cmd) {
        if (conn.ws && conn.ws.readyState === 1) {
            conn.ws.send(JSON.stringify({ cmd }));
        }
    }

    // ────────────────────────────────────────────────────────────
    // Server Event Handlers
    // ────────────────────────────────────────────────────────────

    function handleServerEvent(msg) {
        const { type, data } = msg;

        switch (type) {
            case 'state':    handleFullState(data); break;
            case 'episode':  handleEpisode(data); break;
            case 'phase':    handlePhaseChange(data); break;
            case 'channel':  handleChannelMessage(data); break;
            case 'vocab':    handleVocabToken(data); break;
            case 'eval':     handleEval(data); break;
            case 'status':   handleStatus(data); break;
            case 'heartbeat': break;
            case 'pong':     break;
        }
    }

    function handleFullState(data) {
        state.status = data.status || 'idle';
        state.episode = data.episode || 0;
        state.phase = data.phase || 0;
        state.phaseName = data.phase_name || CONFIG.PHASES[state.phase] || 'Warmup';
        state.metrics.compression = data.compression || 1.0;
        state.metrics.fidelity = data.fidelity || 0.0;
        state.metrics.avgTokens = data.avg_tokens || 30;
        state.metrics.budget = data.budget || 30.0;
        state.metrics.reward = data.total_reward || 0.0;
        state.epRate = data.ep_rate || 0;
        state.phaseHistory = data.phase_history || [];

        if (data.history && data.history.length) {
            state.history = { episodes: [], compression: [], fidelity: [], budget: [] };
            for (const h of data.history.slice(-CONFIG.CHART_HISTORY)) {
                state.history.episodes.push(h.episode);
                state.history.compression.push(h.compression);
                state.history.fidelity.push(h.fidelity);
                state.history.budget.push(h.budget);
            }
            refreshCharts();
        }

        if (data.vocab && data.vocab.length) {
            state.vocab = data.vocab;
            rebuildVocabUI();
        }

        state.paused = data.status === 'paused';
        updateAllUI();
    }

    function handleEpisode(data) {
        const newEp = data.episode || state.episode;

        // Detect cycle reset — episode went backwards → clear history
        if (newEp < state.episode - 100) {
            state.history = { episodes: [], compression: [], fidelity: [], budget: [] };
            state.vocab = [];
            rebuildVocabUI();
            $('#protocolFeed').innerHTML = '';
            state.phase = 0;
            state.phaseName = 'Warmup';
            updatePhaseTimeline();
        }

        state.episode = newEp;
        state.phase = data.phase ?? state.phase;
        state.metrics.compression = data.compression || state.metrics.compression;

        // Fidelity: server sends as percentage (0-100), normalize to 0-1
        if (typeof data.fidelity === 'number') {
            state.metrics.fidelity = data.fidelity > 1.01 ? data.fidelity / 100 : data.fidelity;
        }

        state.metrics.avgTokens = data.tokens || state.metrics.avgTokens;
        state.metrics.budget = data.budget || state.metrics.budget;
        state.metrics.reward = data.reward || state.metrics.reward;

        pushHistory(data);
        updateAllUI();
    }

    function handlePhaseChange(data) {
        state.phase = data.phase ?? state.phase;
        state.phaseName = data.name || CONFIG.PHASES[state.phase] || '';
        state.phaseHistory = data.history || state.phaseHistory;
        updatePhaseTimeline();
    }

    function handleChannelMessage(data) {
        addFeedMessage({
            sender: data.sender || '',
            receiver: data.receiver || '',
            tokenIds: data.token_ids || [],
            tokenCount: data.token_count || 0,
            success: data.success !== false,
            fidelity: data.fidelity || 0,
            task: data.task || '',
        });
    }

    function handleVocabToken(data) {
        const token = { id: data.id, meaning: data.meaning, category: data.category, freq: data.freq || 0, phase: data.phase || 0 };
        state.vocab.push(token);
        renderVocabToken(token);
        $('#vocabCount').textContent = `${state.vocab.length} tokens`;
    }

    function handleEval(data) {
        console.log('[OGENTI] Eval:', data);
    }

    function handleStatus(data) {
        state.status = data.status || state.status;
        state.paused = data.status === 'paused';

        const indicator = $('.status-indicator');
        const statusText = $('#statusText');

        if (state.paused) {
            indicator.classList.add('paused');
            statusText.textContent = 'Paused';
        } else {
            indicator.classList.remove('paused');
            statusText.textContent = state.status === 'training' ? 'Training Active' :
                                     state.status === 'completed' ? 'Completed' : 'Idle';
        }
    }

    // ────────────────────────────────────────────────────────────
    // Connection Status UI
    // ────────────────────────────────────────────────────────────

    function updateConnectionUI() {
        const badge = $('#connectionBadge');
        if (!badge) return;

        badge.className = 'connection-badge ' + conn.mode;

        const labels = {
            live: '● LIVE',
            demo: '◌ DEMO',
            connecting: '… CONNECTING',
            reconnecting: '↻ RECONNECTING',
        };

        badge.textContent = labels[conn.mode] || conn.mode;
    }

    // ────────────────────────────────────────────────────────────
    // Canvas: Agent Visualizer
    // ────────────────────────────────────────────────────────────

    let canvas, ctx;
    let particles = [];
    let agentA = {}, agentB = {};
    let canvasW = 0, canvasH = 0;

    function initCanvas() {
        canvas = $('#agentCanvas');
        ctx = canvas.getContext('2d');
        resizeCanvas();
        window.addEventListener('resize', resizeCanvas);
        requestAnimationFrame(renderCanvas);
    }

    function resizeCanvas() {
        const container = canvas.parentElement;
        const rect = container.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        canvas.style.width = rect.width + 'px';
        canvas.style.height = rect.height + 'px';
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        canvasW = rect.width;
        canvasH = rect.height;
        const r = Math.min(32, canvasW * 0.045);
        agentA = { x: canvasW * 0.15, y: canvasH * 0.5, r };
        agentB = { x: canvasW * 0.85, y: canvasH * 0.5, r };
    }

    function spawnParticles() {
        const cf = Math.min(state.metrics.compression / 16, 1);
        const count = Math.max(1, Math.round(5 * (1 - cf * 0.75)));
        const spread = 25 * (1 - cf * 0.6);

        for (let i = 0; i < count; i++) {
            particles.push({
                x: agentA.x + agentA.r + 4,
                y: agentA.y + (Math.random() - 0.5) * spread * 2,
                speed: 1.2 + Math.random() * 1.8,
                size: 1.5 + Math.random() * (1.5 + cf * 2),
                opacity: 0.7 + Math.random() * 0.3,
                hue: Math.random() > 0.35 ? 0 : 1,
            });
        }
    }

    function updateParticles() {
        const boundary = agentB.x - agentB.r - 4;
        for (const p of particles) {
            p.x += p.speed;
            p.y += (agentB.y - p.y) * 0.012;
            if (p.x > boundary - 40) p.opacity *= 0.92;
        }
        particles = particles.filter(p => p.x < boundary && p.opacity > 0.03);
    }

    function drawAgent(agent, pulse, isSending) {
        const r = agent.r * pulse;
        const grad = ctx.createRadialGradient(agent.x, agent.y, r * 0.2, agent.x, agent.y, r * 2.8);
        grad.addColorStop(0, `rgba(0, 240, 255, ${isSending ? 0.1 : 0.05})`);
        grad.addColorStop(1, 'rgba(0, 240, 255, 0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(agent.x, agent.y, r * 2.8, 0, Math.PI * 2);
        ctx.fill();

        ctx.beginPath();
        ctx.arc(agent.x, agent.y, r, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(0, 240, 255, ${isSending ? 0.7 : 0.35})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(agent.x, agent.y, r * 0.6, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(0, 240, 255, 0.1)';
        ctx.lineWidth = 0.5;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(agent.x, agent.y, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#00f0ff';
        ctx.fill();
    }

    function renderCanvas() {
        if (!ctx || !canvasW) { requestAnimationFrame(renderCanvas); return; }

        ctx.clearRect(0, 0, canvasW, canvasH);

        const lineAlpha = 0.03 + (state.metrics.fidelity * 0.04);
        ctx.beginPath();
        ctx.moveTo(agentA.x + agentA.r + 8, agentA.y);
        ctx.lineTo(agentB.x - agentB.r - 8, agentB.y);
        ctx.strokeStyle = `rgba(0, 240, 255, ${lineAlpha})`;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 8]);
        ctx.stroke();
        ctx.setLineDash([]);

        const colors = ['0, 240, 255', '124, 92, 252'];
        for (const p of particles) {
            const c = colors[p.hue];
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size * 3.5, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${c}, ${p.opacity * 0.06})`;
            ctx.fill();
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${c}, ${p.opacity})`;
            ctx.fill();
        }

        const t = Date.now() * 0.002;
        drawAgent(agentA, Math.sin(t) * 0.06 + 0.94, true);
        drawAgent(agentB, Math.sin(t + Math.PI) * 0.06 + 0.94, false);

        if (!state.paused && Math.random() < 0.35) spawnParticles();
        updateParticles();
        requestAnimationFrame(renderCanvas);
    }

    // ────────────────────────────────────────────────────────────
    // Charts
    // ────────────────────────────────────────────────────────────

    let trainingChart, budgetChart;

    function initCharts() {
        const fontMono = { family: "'JetBrains Mono', monospace", size: 10 };
        const gridColor = 'rgba(255,255,255,0.03)';
        const tickColor = '#444';

        trainingChart = new Chart($('#trainingChart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Compression', data: [],
                        borderColor: '#00f0ff', backgroundColor: 'rgba(0, 240, 255, 0.04)',
                        fill: true, tension: 0.4, pointRadius: 0, borderWidth: 1.5,
                    },
                    {
                        label: 'Fidelity', data: [],
                        borderColor: '#00ff88', backgroundColor: 'rgba(0, 255, 136, 0.04)',
                        fill: true, tension: 0.4, pointRadius: 0, borderWidth: 1.5,
                        yAxisID: 'yFidelity',
                    },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false, animation: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.85)',
                        borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1,
                        titleFont: fontMono, bodyFont: fontMono, padding: 10, cornerRadius: 8,
                        callbacks: {
                            label: (c) => c.datasetIndex === 0
                                ? `Compression: ${c.parsed.y.toFixed(1)}x`
                                : `Fidelity: ${c.parsed.y.toFixed(1)}%`,
                        },
                    },
                },
                scales: {
                    x: { display: true, grid: { color: gridColor }, ticks: { color: tickColor, font: fontMono, maxTicksLimit: 6 } },
                    y: {
                        display: true, position: 'left', grid: { color: gridColor },
                        ticks: { color: tickColor, font: fontMono },
                        min: 0,
                        suggestedMax: 4,
                        title: { display: true, text: 'Compression (x)', color: '#444', font: { size: 10 } },
                    },
                    yFidelity: {
                        display: true, position: 'right', grid: { display: false },
                        ticks: { color: tickColor, font: fontMono }, min: 0, max: 100,
                        title: { display: true, text: 'Fidelity (%)', color: '#444', font: { size: 10 } },
                    },
                },
            },
        });

        budgetChart = new Chart($('#budgetChart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Token Budget', data: [],
                    borderColor: '#7c5cfc', backgroundColor: 'rgba(124, 92, 252, 0.08)',
                    fill: true, tension: 0.3, pointRadius: 0, borderWidth: 1.5,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false, animation: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.85)',
                        borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1,
                        titleFont: fontMono, bodyFont: fontMono, padding: 10, cornerRadius: 8,
                        callbacks: { label: (c) => `Budget: ${c.parsed.y.toFixed(1)} tokens` },
                    },
                },
                scales: {
                    x: { display: true, grid: { color: gridColor }, ticks: { color: tickColor, font: fontMono, maxTicksLimit: 6 } },
                    y: {
                        display: true, grid: { color: gridColor },
                        ticks: { color: tickColor, font: fontMono },
                        min: 0,
                        suggestedMax: 35,
                        title: { display: true, text: 'Max Tokens', color: '#444', font: { size: 10 } },
                    },
                },
            },
        });
    }

    function pushHistory(data) {
        const h = state.history;
        h.episodes.push(data.episode || state.episode);
        h.compression.push(data.compression || state.metrics.compression);

        const fid = typeof data.fidelity === 'number'
            ? (data.fidelity > 1 ? data.fidelity : data.fidelity * 100)
            : state.metrics.fidelity * 100;
        h.fidelity.push(fid);
        h.budget.push(data.budget || state.metrics.budget);

        if (h.episodes.length > CONFIG.CHART_HISTORY) {
            h.episodes.shift(); h.compression.shift();
            h.fidelity.shift(); h.budget.shift();
        }
        refreshCharts();
    }

    function refreshCharts() {
        const h = state.history;
        trainingChart.data.labels = h.episodes.map(String);
        trainingChart.data.datasets[0].data = [...h.compression];
        trainingChart.data.datasets[1].data = [...h.fidelity];
        trainingChart.update('none');

        budgetChart.data.labels = h.episodes.map(String);
        budgetChart.data.datasets[0].data = [...h.budget];
        budgetChart.update('none');
    }

    // ────────────────────────────────────────────────────────────
    // Protocol Feed
    // ────────────────────────────────────────────────────────────

    function addFeedMessage({ sender, receiver, tokenIds, tokenCount, success, fidelity, task }) {
        const el = document.createElement('div');
        el.className = 'feed-message';

        const now = new Date();
        const timeStr = [now.getHours(), now.getMinutes(), now.getSeconds()]
            .map(n => String(n).padStart(2, '0')).join(':');

        const senderShort = sender.replace('encoder_', '').replace('decoder_', '');
        const receiverShort = receiver.replace('encoder_', '').replace('decoder_', '');
        const route = `${senderShort}→${receiverShort}`;

        const idStr = tokenIds.length
            ? `ξ[${tokenIds.slice(0, 5).join(',')}${tokenIds.length > 5 ? '…' : ''}]→◊`
            : `ξ[…]→◊`;

        el.innerHTML = `
            <span class="feed-time">${timeStr}</span>
            <span class="feed-route">${route}</span>
            <span class="feed-tokens" title="${task}">${idStr} ${tokenCount}t</span>
            <span class="feed-status ${success ? 'success' : 'fail'}">${success ? fidelity.toFixed(1) + '%' : 'DROP'}</span>
        `;

        const feed = $('#protocolFeed');
        feed.insertBefore(el, feed.firstChild);
        while (feed.children.length > CONFIG.FEED_MAX) feed.removeChild(feed.lastChild);
    }

    // ────────────────────────────────────────────────────────────
    // Vocabulary
    // ────────────────────────────────────────────────────────────

    function renderVocabToken(token) {
        const maxFreq = Math.max(...state.vocab.map(t => t.freq || 1), 1);
        const barWidth = Math.round(((token.freq || 1) / maxFreq) * 100);

        const el = document.createElement('div');
        el.className = 'vocab-token';
        el.innerHTML = `
            <span class="vocab-id">${token.id}</span>
            <div class="vocab-info">
                <span class="vocab-meaning">${token.meaning}</span>
                <div class="vocab-bar-bg"><div class="vocab-bar" style="width:${barWidth}%"></div></div>
            </div>
            <span class="vocab-cat">${token.category}</span>
        `;
        $('#vocabGrid').appendChild(el);
    }

    function rebuildVocabUI() {
        const grid = $('#vocabGrid');
        grid.innerHTML = '';
        for (const token of state.vocab) renderVocabToken(token);
        $('#vocabCount').textContent = `${state.vocab.length} tokens`;
    }

    // ────────────────────────────────────────────────────────────
    // UI Updates
    // ────────────────────────────────────────────────────────────

    function updateAllUI() {
        $('#metricPhase').textContent = state.phase;
        $('#metricPhaseName').textContent = state.phaseName || CONFIG.PHASES[state.phase] || '';
        $('#metricCompression').textContent = state.metrics.compression.toFixed(1);
        $('#metricFidelity').textContent = (state.metrics.fidelity * 100).toFixed(1);
        $('#metricEpisodes').textContent = state.episode.toLocaleString();

        if (state.epRate > 0) {
            $('#metricRate').textContent = `${Math.round(state.epRate)} ep/s`;
        }

        $('#vizTokenCount').textContent = `${state.metrics.avgTokens} tokens`;

        updatePhaseTimeline();

        const totalEp = 5000;
        const progress = Math.min((state.episode / totalEp) * 100, 100);
        $('#nav').style.setProperty('--progress', `${progress}%`);

        document.title = `OGENTI · Ep ${state.episode.toLocaleString()}`;
    }

    function updatePhaseTimeline() {
        $$('.phase-item').forEach((el, i) => {
            el.classList.toggle('active', i <= state.phase);
            el.classList.toggle('current', i === state.phase);
        });
        $$('.phase-connector').forEach((el, i) => {
            el.classList.toggle('active', i < state.phase);
        });
    }

    // ────────────────────────────────────────────────────────────
    // Pause / Resume
    // ────────────────────────────────────────────────────────────

    function togglePause() {
        if (conn.mode === 'live') {
            sendCommand(state.paused ? 'resume' : 'pause');
        } else {
            state.paused = !state.paused;
            handleStatus({ status: state.paused ? 'paused' : 'training' });
        }
    }

    // ────────────────────────────────────────────────────────────
    // Demo Mode (fallback when no server)
    // ────────────────────────────────────────────────────────────

    let demoInterval = null;

    const DEMO = {
        TICK: 250, EP_PER_TICK: 12, TOTAL: 6000,
        PHASES: [
            { name: 'Warmup', start: 0, end: 400 },
            { name: 'Simple', start: 400, end: 1500 },
            { name: 'Complex', start: 1500, end: 2800 },
            { name: 'Generalize', start: 2800, end: 4200 },
            { name: 'Universalize', start: 4200, end: 6000 },
        ],
        TARGETS: [
            { compression: 1.0, fidelity: 0.00, tokens: 30, budget: 30 },
            { compression: 2.2, fidelity: 0.52, tokens: 24, budget: 27 },
            { compression: 8.5, fidelity: 0.86, tokens: 11, budget: 18 },
            { compression: 13.0, fidelity: 0.94, tokens: 6, budget: 8 },
            { compression: 15.8, fidelity: 0.97, tokens: 5, budget: 5 },
            { compression: 16.5, fidelity: 0.98, tokens: 4, budget: 4 },
        ],
        VOCAB: [
            { id: 7, meaning: 'begin-ctx', category: 'struct', phase: 0 },
            { id: 22, meaning: 'end-response', category: 'struct', phase: 0 },
            { id: 1, meaning: 'separator', category: 'struct', phase: 0 },
            { id: 15, meaning: 'ack', category: 'struct', phase: 0 },
            { id: 42, meaning: 'summarize', category: 'op', phase: 1 },
            { id: 87, meaning: 'compare', category: 'op', phase: 1 },
            { id: 91, meaning: 'extract', category: 'op', phase: 1 },
            { id: 3, meaning: 'key-points', category: 'op', phase: 1 },
            { id: 67, meaning: 'enumerate', category: 'op', phase: 1 },
            { id: 45, meaning: 'analyze', category: 'op', phase: 1 },
            { id: 55, meaning: 'aggregate', category: 'op', phase: 1 },
            { id: 30, meaning: 'transform', category: 'op', phase: 1 },
            { id: 33, meaning: 'causal-link', category: 'rel', phase: 2 },
            { id: 14, meaning: 'contrast', category: 'rel', phase: 2 },
            { id: 200, meaning: 'temporal', category: 'mod', phase: 2 },
            { id: 8, meaning: 'quantitative', category: 'mod', phase: 2 },
            { id: 77, meaning: 'trend-up', category: 'semantic', phase: 2 },
            { id: 78, meaning: 'trend-down', category: 'semantic', phase: 2 },
            { id: 120, meaning: 'entity-ref', category: 'semantic', phase: 2 },
            { id: 156, meaning: 'sentiment-pos', category: 'semantic', phase: 2 },
            { id: 99, meaning: 'confidence-hi', category: 'meta', phase: 3 },
            { id: 100, meaning: 'confidence-lo', category: 'meta', phase: 3 },
            { id: 250, meaning: 'uncertainty', category: 'meta', phase: 3 },
            { id: 11, meaning: 'scope-global', category: 'meta', phase: 3 },
        ],
        TASKS: [
            'Summarize quarterly earnings report', 'Compare product A vs B metrics',
            'Extract findings from research paper', 'Analyze customer sentiment trends',
            'Generate executive summary', 'Classify document by topic',
            'Identify anomalies in dataset', 'Translate technical spec to guide',
        ],
    };

    let demoVocabIdx = 0;

    function startDemoSimulation() {
        state.episode = 0; state.phase = 0;
        state.startTime = Date.now();
        demoVocabIdx = 0;
        handleStatus({ status: 'training' });
        demoInterval = setInterval(demoTick, DEMO.TICK);
    }

    function demoTick() {
        if (state.paused) return;

        state.episode += DEMO.EP_PER_TICK + Math.floor(Math.random() * 7) - 3;

        const newPhase = DEMO.PHASES.findIndex(p => state.episode >= p.start && state.episode < p.end);
        if (newPhase >= 0 && newPhase !== state.phase) {
            state.phase = newPhase;
            state.phaseName = DEMO.PHASES[newPhase].name;
        }

        if (state.episode >= DEMO.TOTAL) { resetDemo(); return; }

        // Global progress across all phases for smooth learning curve
        const globalProgress = clamp(state.episode / DEMO.TOTAL, 0, 1);
        const tGlobal = smoothstep(globalProgress);

        // Final targets (end of training)
        const finalTarget = DEMO.TARGETS[DEMO.TARGETS.length - 1];
        const startTarget = DEMO.TARGETS[0];

        // Phase-local detail
        const phase = DEMO.PHASES[state.phase];
        const localProgress = clamp((state.episode - phase.start) / (phase.end - phase.start), 0, 1);
        const tLocal = smoothstep(localProgress);

        // Blend global + local for natural curve
        const phaseTarget = DEMO.TARGETS[Math.min(state.phase + 1, DEMO.TARGETS.length - 1)];
        const t = 0.7 * tGlobal + 0.3 * tLocal * ((state.phase + 1) / 4);

        const noiseScale = 0.02 + state.phase * 0.015;

        state.metrics.compression = Math.max(1, lerp(startTarget.compression, phaseTarget.compression, t) * (1 + (Math.random() - 0.5) * noiseScale * 2));
        state.metrics.fidelity = clamp(lerp(startTarget.fidelity, phaseTarget.fidelity, t) + (Math.random() - 0.5) * noiseScale * 0.5, 0, 1);
        state.metrics.avgTokens = Math.max(3, Math.round(lerp(startTarget.tokens, phaseTarget.tokens, t) + (Math.random() - 0.5) * 1.5));
        state.metrics.budget = Math.max(5, lerp(startTarget.budget, phaseTarget.budget, t) + (Math.random() - 0.5) * 0.8);

        const elapsed = (Date.now() - state.startTime) / 1000;
        state.epRate = elapsed > 0 ? state.episode / elapsed : 0;

        if (Math.random() < 0.45) {
            const task = DEMO.TASKS[Math.floor(Math.random() * DEMO.TASKS.length)];
            const tokens = state.metrics.avgTokens;
            const ids = Array.from({ length: tokens }, () => Math.floor(Math.random() * 256));
            const ok = tokens <= Math.ceil(state.metrics.budget);
            const success = ok && Math.random() > 0.05;
            addFeedMessage({
                sender: `α${Math.floor(Math.random() * 3) + 1}`,
                receiver: `β${Math.floor(Math.random() * 3) + 1}`,
                tokenIds: ids.slice(0, 5), tokenCount: tokens,
                success, fidelity: success ? state.metrics.fidelity * 100 + (Math.random() - 0.5) * 8 : 0,
                task,
            });
        }

        if (demoVocabIdx < DEMO.VOCAB.length) {
            const next = DEMO.VOCAB[demoVocabIdx];
            if (state.phase >= next.phase && Math.random() < 0.12) {
                handleVocabToken({ ...next, freq: Math.floor(Math.random() * 1500) + 200 });
                demoVocabIdx++;
            }
        }

        pushHistory({ episode: state.episode, compression: state.metrics.compression, fidelity: state.metrics.fidelity * 100, budget: state.metrics.budget });
        updateAllUI();
    }

    function resetDemo() {
        state.episode = 0; state.phase = 0; state.phaseName = 'Warmup';
        state.metrics = { compression: 1.0, fidelity: 0.0, avgTokens: 30, budget: 30.0, reward: 0.0 };
        state.history = { episodes: [], compression: [], fidelity: [], budget: [] };
        state.vocab = []; demoVocabIdx = 0; state.startTime = Date.now();

        trainingChart.data.labels = [];
        trainingChart.data.datasets.forEach(d => d.data = []);
        trainingChart.update('none');
        budgetChart.data.labels = [];
        budgetChart.data.datasets[0].data = [];
        budgetChart.update('none');

        $('#protocolFeed').innerHTML = '';
        rebuildVocabUI();
        $$('.phase-item').forEach(el => el.classList.remove('active', 'current'));
        $$('.phase-item')[0].classList.add('active', 'current');
        $$('.phase-connector').forEach(el => el.classList.remove('active'));
    }

    // ────────────────────────────────────────────────────────────
    // Interactions
    // ────────────────────────────────────────────────────────────

    function setupInteractions() {
        document.addEventListener('keydown', (e) => {
            if (e.code === 'Space' && e.target === document.body) {
                e.preventDefault();
                togglePause();
            }
        });
        canvas.addEventListener('click', () => { for (let i = 0; i < 15; i++) spawnParticles(); });
    }

    // ────────────────────────────────────────────────────────────
    // Utilities
    // ────────────────────────────────────────────────────────────

    function lerp(a, b, t) { return a + (b - a) * t; }
    function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }
    function smoothstep(t) { return t * t * (3 - 2 * t); }

    // ────────────────────────────────────────────────────────────
    // Init
    // ────────────────────────────────────────────────────────────

    function init() {
        initCanvas();
        initCharts();
        setupInteractions();

        // Try connecting to backend WebSocket
        connectWebSocket();

        // If not connected in 2s, fall back to demo
        setTimeout(() => {
            if (!conn.connected && conn.mode !== 'demo') fallbackToDemo();
        }, 2000);

        setTimeout(() => {
            const loader = $('#loader');
            if (loader) loader.classList.add('hidden');
        }, 600);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
