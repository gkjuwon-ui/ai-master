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
    // REST Polling Engine
    // ────────────────────────────────────────────────────────────

    async function connectWithKey(key) {
        key = (key || '').trim().toUpperCase();
        if (!key) return;
        conn.currentKey = key;
        conn.mode = 'connecting';
        updateConnectionUI();
        try {
            await pollDashboard(key);
            conn.mode = 'live';
            conn.connected = true;
            updateConnectionUI();
            updateURL(key);
            const overlay = $('#keyOverlay');
            if (overlay) overlay.style.display = 'none';
            startPolling(key);
        } catch (e) {
            conn.mode = 'error';
            conn.connected = false;
            updateConnectionUI();
            const el = $('#keyError');
            if (el) el.textContent = e.message || 'INVALID KEY';
        }
    }

    async function pollDashboard(key) {
        const resp = await fetch(`${CONFIG.API_BASE}/api/training/dashboard/${key}`, { cache: 'no-store' });
        if (resp.status === 404) throw new Error('INVALID KEY — CHECK YOUR DASHBOARD KEY');
        if (!resp.ok) throw new Error(`SERVER ERROR ${resp.status}`);
        const data = await resp.json();
        handleApiData(data);
        return data;
    }

    function handleApiData(data) {
        // Synthetic vocab generation based on real phase
        const targetVocabSize = Math.floor(data.phase * 8 + (data.progress_pct / 100) * 12);
        while (state.vocab.length < targetVocabSize && state.vocab.length < DEMO.VOCAB.length) {
            const v = DEMO.VOCAB[state.vocab.length];
            if (v) handleVocabToken({ ...v, freq: Math.floor(data.progress_pct * 10 + Math.random() * 500) + 1 });
        }

        // Synthetic feed message based on live phase
        if (data.status === 'training' && Math.random() < 0.45) {
            const task = DEMO.TASKS[Math.floor(Math.random() * DEMO.TASKS.length)];
            addFeedMessage({
                sender: `α${Math.floor(Math.random() * 3) + 1}`,
                receiver: `β${Math.floor(Math.random() * 3) + 1}`,
                tokenIds: Array.from({ length: 5 }, () => Math.floor(Math.random() * 256)),
                tokenCount: data.avg_tokens,
                success: Math.random() > 0.05,
                fidelity: data.fidelity * 100,
                task,
            });
        }

        // Drive the full-state visualizer
        handleFullState({
            status: data.status,
            episode: data.current_episode,
            phase: data.phase,
            phase_name: data.phase_name,
            compression: data.compression,
            fidelity: data.fidelity,
            avg_tokens: data.avg_tokens,
            budget: data.budget,
            total_reward: 0,
            ep_rate: 0,
        });
        pushHistory({ episode: data.current_episode, compression: data.compression, fidelity: data.fidelity * 100, budget: data.budget });

        // Update job info bar
        const setEl = (id, val, style) => { const el = $(id); if (el) { el.textContent = val; if (style) Object.assign(el.style, style); } };
        setEl('#jobModel', data.model || '—');
        setEl('#jobDataset', data.dataset || '—');
        setEl('#jobStatus', (data.job_status || data.status || '—').toUpperCase(), {
            color: data.job_status === 'completed' ? 'var(--green)' : data.job_status === 'failed' ? '#ff4060' : 'var(--cyan)'
        });
        setEl('#jobProgress', `${Math.round(data.progress_pct || 0)}%`);
        const bar = $('#jobInfoBar');
        if (bar) bar.style.display = 'flex';

        // Stop polling when terminal state
        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
            stopPolling();
            updateConnectionUI();
        }
    }

    function startPolling(key) {
        stopPolling();
        conn.pollTimer = setInterval(async () => {
            if (document.hidden) return;
            try { await pollDashboard(key); }
            catch (e) { console.warn('[OGENTI] Poll error:', e.message); }
        }, CONFIG.POLL_INTERVAL);
    }

    function stopPolling() {
        if (conn.pollTimer) { clearInterval(conn.pollTimer); conn.pollTimer = null; }
    }

    function updateURL(key) {
        const url = new URL(window.location.href);
        url.searchParams.set('key', key);
        window.history.replaceState({}, '', url.toString());
    }

    function fallbackToDemo() {
        conn.mode = 'demo';
        conn.connected = false;
        updateConnectionUI();
        const overlay = $('#keyOverlay');
        if (overlay) overlay.style.display = 'none';
        startDemoSimulation();
    }

    // No-op in REST mode
    function sendCommand(cmd) {}

    // ────────────────────────────────────────────────────────────
    // REST Polling Fallback (for Colab iframe where WS may not relay data)
    // ────────────────────────────────────────────────────────────

    let restPollTimer = null;

    function startRestPolling() {
        if (restPollTimer) return;
        restPollTimer = setInterval(async () => {
            if (document.hidden) return;
            try {
                const resp = await fetch(`${CONFIG.API_BASE}/api/snapshot`, { cache: 'no-store' });
                if (!resp.ok) return;
                const data = await resp.json();
                handleFullState(data);
            } catch (e) {
                console.warn('[OGENTI] REST poll error:', e.message);
            }
        }, 2000);  // Poll every 2 seconds
    }

    // ────────────────────────────────────────────────────────────
    // Local WebSocket Mode (direct connection for local training)
    // ────────────────────────────────────────────────────────────

    function connectWebSocketLocal() {
        const wsUrl = CONFIG.WS_URL;
        conn.mode = 'connecting';
        updateConnectionUI();

        try {
            conn.ws = new WebSocket(wsUrl);
        } catch (e) {
            console.warn('[OGENTI] WS connect failed:', e);
            setTimeout(() => connectWebSocketLocal(), CONFIG.WS_RECONNECT_INTERVAL);
            return;
        }

        conn.ws.onopen = () => {
            conn.connected = true;
            conn.mode = 'live';
            conn.retries = 0;
            updateConnectionUI();
            // Also start REST polling as fallback (Colab proxy may not relay WS data)
            startRestPolling();
            // Show bar with local info
            const bar = $('#jobInfoBar');
            if (bar) bar.style.display = 'flex';
            const setEl = (id, val) => { const el = $(id); if (el) el.textContent = val; };
            setEl('#jobModel', 'LOCAL');
            setEl('#jobDataset', 'CPU');
            setEl('#jobStatus', 'LIVE');
        };

        conn.ws.onmessage = (evt) => {
            try {
                const msg = JSON.parse(evt.data);
                handleServerEvent(msg);
            } catch (e) {
                console.warn('[OGENTI] WS parse error:', e);
            }
        };

        conn.ws.onclose = () => {
            conn.connected = false;
            conn.mode = 'reconnecting';
            conn.retries++;
            updateConnectionUI();
            // Keep REST polling going as fallback
            startRestPolling();
            if (conn.retries <= CONFIG.WS_MAX_RETRIES) {
                setTimeout(() => connectWebSocketLocal(), CONFIG.WS_RECONNECT_INTERVAL);
            }
        };

        conn.ws.onerror = (err) => {
            console.warn('[OGENTI] WS error:', err);
        };
    }

    // Global submitKey called from HTML onclick
    window.submitKey = function () {
        const input = $('#keyInput');
        const key = (input ? input.value : '').trim();
        if (!key) { const el = $('#keyError'); if (el) el.textContent = 'ENTER A DASHBOARD KEY'; return; }
        const el = $('#keyError'); if (el) el.textContent = '';
        const btn = $('#keyBtn');
        if (btn) { btn.disabled = true; btn.textContent = 'CONNECTING...'; }
        connectWithKey(key).finally(() => { if (btn) { btn.disabled = false; btn.textContent = 'CONNECT →'; } });
    };

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
            case 'adapter_exported': handleAdapterExported(data); break;
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
        handleStatus({ status: data.status || 'idle' });
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
            live: '[*] LIVE',
            demo: '[ ] DEMO',
            connecting: '... CONNECTING',
            error: '[!] ERROR',
            idle: '-- READY',
        };
        badge.textContent = labels[conn.mode] || conn.mode.toUpperCase();
    }

    // ────────────────────────────────────────────────────────────
    // Canvas: 16-bit Pixel Agent Visualizer
    // ────────────────────────────────────────────────────────────

    let canvas, ctx;
    let packets = [];
    let agentA = {}, agentB = {};
    let canvasW = 0, canvasH = 0;
    let waveOffset = 0;

    // pixel unit for scaling
    function px(n) { return Math.round(n * Math.max(1, canvasW / 800)); }

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
        agentA = { x: canvasW * 0.13, y: canvasH * 0.48, r };
        agentB = { x: canvasW * 0.87, y: canvasH * 0.48, r };
    }

    // Spawn square data packets instead of round particles
    function spawnParticles() {
        const cf = Math.min(state.metrics.compression / 16, 1);
        const count = Math.max(1, Math.round(3 * (1 - cf * 0.6)));

        for (let i = 0; i < count; i++) {
            const hueRng = Math.random();
            packets.push({
                x: agentA.x + px(28),
                y: agentA.y + (Math.random() - 0.5) * px(10),
                speed: px(1.5) + Math.random() * px(1.5),
                size: px(2) + Math.random() * px(2 + cf * 2),
                opacity: 0.8 + Math.random() * 0.2,
                color: hueRng < 0.35 ? '#b060ff' : hueRng < 0.6 ? '#00ff88' : hueRng < 0.8 ? '#ffe040' : '#00f0ff',
            });
        }
    }

    function updateParticles() {
        const boundary = agentB.x - px(28);
        for (const p of packets) {
            p.x += p.speed;
            p.y += (agentB.y - p.y) * 0.015;
            if (p.x > boundary - px(30)) p.opacity *= 0.9;
        }
        packets = packets.filter(p => p.x < boundary && p.opacity > 0.05);
    }

    // Draw a 16-bit pixel robot
    function drawPixelRobot(cx, cy, scale, color, shadowColor, t, isSender) {
        const s = scale;
        const bob = Math.round(Math.sin(t * (isSender ? 1.0 : 1.2)) * s * 1.5);
        const y = cy + bob;
        const x = cx;

        // Helper: draw a pixel rect
        function r(rx, ry, rw, rh, c, a) {
            ctx.globalAlpha = a !== undefined ? a : 1;
            ctx.fillStyle = c;
            ctx.fillRect(Math.round(x + rx * s), Math.round(y + ry * s), Math.round(rw * s), Math.round(rh * s));
            ctx.globalAlpha = 1;
        }

        // Glow under robot
        ctx.globalAlpha = 0.08;
        ctx.fillStyle = color;
        ctx.fillRect(Math.round(x - 8 * s), Math.round(y + 20 * s), Math.round(16 * s), Math.round(4 * s));
        ctx.globalAlpha = 1;

        // Antenna
        r(-1, -18, 2, 4, color);
        r(-3, -20, 6, 2, color, 0.5);

        // Head outline
        r(-4, -14, 8, 2, color);         // top
        r(-6, -12, 2, 2, color);         // top-left
        r(4, -12, 2, 2, color);          // top-right
        r(-8, -10, 2, 10, color);        // left
        r(6, -10, 2, 10, color);         // right
        r(-6, 0, 2, 2, color);           // bottom-left
        r(4, 0, 2, 2, color);            // bottom-right
        r(-4, 2, 8, 2, color);           // bottom

        // Head fill
        r(-6, -10, 12, 10, color, 0.08);

        // Eyes (white pixels)
        const blinkPhase = Math.sin(t * 0.7);
        if (blinkPhase > -0.95) { // blink occasionally
            r(-4, -6, 2, 2, '#fff');
            r(2, -6, 2, 2, '#fff');
        }

        // Core (center of head)
        r(-2, -4, 4, 4, color);

        // Neck
        r(-2, 4, 4, 2, color);

        // Body
        r(-4, 6, 8, 2, color);           // top
        r(-6, 8, 12, 2, shadowColor);    // shoulders
        r(-8, 10, 4, 8, shadowColor);    // left arm
        r(4, 10, 4, 8, shadowColor);     // right arm
        r(-4, 8, 8, 12, color);          // torso

        // Legs
        r(-4, 20, 3, 4, shadowColor);
        r(1, 20, 3, 4, shadowColor);
    }

    // Draw 8-bit waveform beam between agents
    function drawWaveBeam(x1, x2, cy, t) {
        const segW = px(4);
        const amplitude = px(6) + state.metrics.fidelity * px(8);
        const freq = 0.15 + state.metrics.compression * 0.008;
        const baseAlpha = 0.15 + state.metrics.fidelity * 0.25;

        // Glow trail
        ctx.globalAlpha = baseAlpha * 0.2;
        ctx.fillStyle = '#00f0ff';
        ctx.fillRect(x1, cy - px(1), x2 - x1, px(2));
        ctx.globalAlpha = 1;

        // Pixelated sine wave
        const steps = Math.floor((x2 - x1) / segW);
        for (let i = 0; i < steps; i++) {
            const xPos = x1 + i * segW;
            const phase = (i * freq + t) % (Math.PI * 2);
            const yOff = Math.round(Math.sin(phase) * amplitude / segW) * segW;

            // Main wave pixel
            const alpha = 0.4 + Math.sin(phase + t * 0.5) * 0.2;
            ctx.globalAlpha = baseAlpha + alpha * 0.3;
            ctx.fillStyle = '#00f0ff';
            ctx.fillRect(xPos, cy + yOff - segW / 2, segW - 1, segW);

            // Secondary harmonic (smaller, purple)
            if (i % 2 === 0) {
                const yOff2 = Math.round(Math.sin(phase * 2.3 + 1.5) * amplitude * 0.5 / segW) * segW;
                ctx.globalAlpha = baseAlpha * 0.5;
                ctx.fillStyle = '#b060ff';
                ctx.fillRect(xPos, cy + yOff2 - segW / 4, segW - 1, segW / 2);
            }

            // Tertiary harmonic (green, sparse)
            if (i % 4 === 0 && state.metrics.compression > 2) {
                const yOff3 = Math.round(Math.sin(phase * 0.7 - 0.8) * amplitude * 0.7 / segW) * segW;
                ctx.globalAlpha = baseAlpha * 0.3;
                ctx.fillStyle = '#00ff88';
                ctx.fillRect(xPos + segW / 4, cy + yOff3 - segW / 4, segW / 2, segW / 2);
            }
        }
        ctx.globalAlpha = 1;
    }

    function renderCanvas() {
        if (!ctx || !canvasW) { requestAnimationFrame(renderCanvas); return; }

        ctx.clearRect(0, 0, canvasW, canvasH);

        const t = Date.now() * 0.003;
        if (!state.paused) waveOffset += 0.06;

        // Draw 8-bit waveform beam
        const beamX1 = agentA.x + px(28);
        const beamX2 = agentB.x - px(28);
        drawWaveBeam(beamX1, beamX2, agentA.y, waveOffset);

        // Draw data packets (square pixels)
        for (const p of packets) {
            const s = Math.round(p.size);
            // Glow
            ctx.globalAlpha = p.opacity * 0.12;
            ctx.fillStyle = p.color;
            ctx.fillRect(p.x - s, p.y - s, s * 3, s * 3);
            // Core pixel
            ctx.globalAlpha = p.opacity;
            ctx.fillStyle = p.color;
            ctx.fillRect(p.x, p.y, s, s);
            ctx.globalAlpha = 1;
        }

        // Draw pixel robots
        const robotScale = Math.max(2, Math.min(3.5, canvasW / 280));
        drawPixelRobot(agentA.x, agentA.y, robotScale, '#00f0ff', '#007088', t, true);
        drawPixelRobot(agentB.x, agentB.y, robotScale, '#00ff88', '#007744', t, false);

        // Spawn & update
        if (!state.paused && Math.random() < 0.3) spawnParticles();
        updateParticles();
        requestAnimationFrame(renderCanvas);
    }

    // ────────────────────────────────────────────────────────────
    // Charts
    // ────────────────────────────────────────────────────────────

    let trainingChart, budgetChart;

    function initCharts() {
        const fontMono = { family: "'Silkscreen', 'Press Start 2P', monospace", size: 10 };
        const gridColor = 'rgba(26, 26, 58, 0.8)';
        const tickColor = '#3a3a5a';

        trainingChart = new Chart($('#trainingChart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Compression', data: [],
                        borderColor: '#00f0ff', backgroundColor: 'rgba(0, 240, 255, 0.06)',
                        fill: true, tension: 0.1, pointRadius: 0, borderWidth: 2, stepped: false,
                    },
                    {
                        label: 'Fidelity', data: [],
                        borderColor: '#00ff88', backgroundColor: 'rgba(0, 255, 136, 0.06)',
                        fill: true, tension: 0.1, pointRadius: 0, borderWidth: 2, stepped: false,
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
                        backgroundColor: '#0a0a1a',
                        borderColor: '#1a1a3a', borderWidth: 2,
                        titleFont: fontMono, bodyFont: fontMono, padding: 10, cornerRadius: 0,
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
                    borderColor: '#b060ff', backgroundColor: 'rgba(176, 96, 255, 0.08)',
                    fill: true, tension: 0.1, pointRadius: 0, borderWidth: 2, stepped: false,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false, animation: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#0a0a1a',
                        borderColor: '#1a1a3a', borderWidth: 2,
                        titleFont: fontMono, bodyFont: fontMono, padding: 10, cornerRadius: 0,
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
    // Adapter Export Notification
    // ────────────────────────────────────────────────────────────

    function handleAdapterExported(data) {
        console.log('[OGENTI] Universal Adapter Exported:', data);

        // Show export banner
        let banner = document.getElementById('adapterBanner');
        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'adapterBanner';
            banner.style.cssText = `
                position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
                background: #0a0a1a;
                border-bottom: 4px solid #00f0ff;
                color: #c8c8e0; padding: 16px 24px; text-align: center;
                font-family: 'Silkscreen', 'Press Start 2P', monospace; font-size: 14px;
                box-shadow: 0 4px 20px rgba(0,240,255,0.2);
                animation: bannerSlide 0.5s ease-out;
                cursor: pointer;
            `;
            document.body.appendChild(banner);

            // Add animation keyframes
            if (!document.getElementById('bannerAnim')) {
                const style = document.createElement('style');
                style.id = 'bannerAnim';
                style.textContent = `
                    @keyframes bannerSlide {
                        from { transform: translateY(-100%); opacity: 0; }
                        to   { transform: translateY(0); opacity: 1; }
                    }
                    @keyframes bannerFade {
                        from { opacity: 1; }
                        to   { opacity: 0; transform: translateY(-100%); }
                    }
                `;
                document.head.appendChild(style);
            }
        }

        const models = data.supported_models || [];
        const metrics = data.final_metrics || {};
        const fileList = (data.files || []).join(' + ');

        banner.innerHTML = `
            <div style="font-family:'Press Start 2P',monospace; font-size:0.6rem; margin-bottom:8px; color:#00f0ff; text-shadow:0 0 8px rgba(0,240,255,0.5);">>>> UNIVERSAL ADAPTER EXPORTED <<<</div>
            <div style="font-size:0.7rem; line-height:2;">
                <span style="background:#12122a; border:2px solid #1a1a3a; padding:3px 8px; margin:0 4px;">PATH: ${data.path || 'checkpoints/universal_adapter'}</span>
                <span style="background:#12122a; border:2px solid #1a1a3a; padding:3px 8px; margin:0 4px;">PARAMS: ${((data.params || 0) / 1000).toFixed(0)}K</span>
                <span style="background:#12122a; border:2px solid #1a1a3a; padding:3px 8px; margin:0 4px;">MATCH: ${((metrics.distill_match || 0) * 100).toFixed(1)}%</span>
                <span style="background:#12122a; border:2px solid #1a1a3a; padding:3px 8px; margin:0 4px;">COMPRESS: ${(metrics.compression || 0).toFixed(1)}x</span>
            </div>
            <div style="font-family:'Press Start 2P',monospace; font-size:0.35rem; color:#6a6a8a; margin-top:8px;">
                COMPATIBLE: ${models.join(' / ')}
            </div>
            <div style="font-family:'Press Start 2P',monospace; font-size:0.3rem; color:#3a3a5a; margin-top:6px;">CLICK TO DISMISS</div>
        `;

        banner.onclick = () => {
            banner.style.animation = 'bannerFade 0.3s ease-in forwards';
            setTimeout(() => banner.remove(), 300);
        };

        // Auto-dismiss after 15s
        setTimeout(() => {
            if (banner.parentNode) {
                banner.style.animation = 'bannerFade 0.3s ease-in forwards';
                setTimeout(() => banner.remove(), 300);
            }
        }, 15000);

        // Also add to feed
        const feedEl = document.createElement('div');
        feedEl.className = 'feed-message';
        feedEl.style.cssText = 'border-left: 4px solid #00f0ff; background: rgba(0,240,255,0.06);';
        const now = new Date();
        const ts = [now.getHours(), now.getMinutes(), now.getSeconds()].map(n => String(n).padStart(2, '0')).join(':');
        feedEl.innerHTML = `
            <span class="feed-time">${ts}</span>
            <span class="feed-route" style="color:#00f0ff; font-weight:700;">>>> ADAPTER</span>
            <span class="feed-tokens">Universal adapter exported → ${fileList}</span>
            <span class="feed-status success">${models.length} models</span>
        `;
        const feed = $('#protocolFeed');
        if (feed) feed.insertBefore(feedEl, feed.firstChild);
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
        // In REST mode just pause the local visualization
        state.paused = !state.paused;
        handleStatus({ status: state.paused ? 'paused' : 'training' });
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

        // Enable Enter key on key input
        const input = $('#keyInput');
        if (input) {
            input.addEventListener('keydown', (e) => { if (e.key === 'Enter') window.submitKey(); });
            // Auto-uppercase
            input.addEventListener('input', () => { input.value = input.value.toUpperCase(); });
        }

        // Check URL for ?local (WebSocket mode) or ?key= (SaaS polling mode)
        const params = new URLSearchParams(window.location.search);
        const isLocal = params.has('local') || window.location.port === '8000';
        const urlKey = params.get('key');

        if (urlKey) {
            if (input) input.value = urlKey.toUpperCase();
            // Slight delay to let canvas init finish
            setTimeout(() => connectWithKey(urlKey), 300);
        } else {
            // Auto-connect via WebSocket (works for local, Colab iframe, any same-origin)
            const overlay = $('#keyOverlay');
            if (overlay) overlay.style.display = 'none';
            setTimeout(() => connectWebSocketLocal(), 300);
        }

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
