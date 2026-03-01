/* ============================================================
   OGENTI Protocol Monitor — Dashboard Engine
   Simulated MARL training visualization
   ============================================================ */

(() => {
    'use strict';

    // ─── Configuration ────────────────────────────────────────
    const CONFIG = {
        TICK_INTERVAL: 250,
        EPISODES_PER_TICK: 12,
        TOTAL_EPISODES: 5000,
        CHART_HISTORY: 150,
        FEED_MAX: 40,
        VOCAB_MAX: 24,

        PHASES: [
            { name: 'Warmup',     start: 0,    end: 500  },
            { name: 'Simple',     start: 500,  end: 2000 },
            { name: 'Complex',    start: 2000, end: 3500 },
            { name: 'Generalize', start: 3500, end: 5000 },
        ],

        // Metrics at phase boundaries [start, end_P0, end_P1, end_P2, end_P3]
        TARGETS: [
            { compression: 1.0,  fidelity: 0.00, tokens: 30, budget: 30 },
            { compression: 2.2,  fidelity: 0.52, tokens: 24, budget: 27 },
            { compression: 8.5,  fidelity: 0.86, tokens: 11, budget: 18 },
            { compression: 13.0, fidelity: 0.94, tokens: 6,  budget: 8  },
            { compression: 15.8, fidelity: 0.97, tokens: 5,  budget: 5  },
        ],
    };

    // ─── Emergent Vocabulary Definitions ──────────────────────
    const VOCAB_POOL = [
        // Phase 0 — structural tokens
        { id: 7,   meaning: 'begin-ctx',       category: 'struct',   phase: 0 },
        { id: 22,  meaning: 'end-response',    category: 'struct',   phase: 0 },
        { id: 1,   meaning: 'separator',       category: 'struct',   phase: 0 },
        { id: 15,  meaning: 'ack',             category: 'struct',   phase: 0 },
        // Phase 1 — basic operations
        { id: 42,  meaning: 'summarize',       category: 'op',       phase: 1 },
        { id: 87,  meaning: 'compare',         category: 'op',       phase: 1 },
        { id: 91,  meaning: 'extract',         category: 'op',       phase: 1 },
        { id: 3,   meaning: 'key-points',      category: 'op',       phase: 1 },
        { id: 67,  meaning: 'enumerate',       category: 'op',       phase: 1 },
        { id: 45,  meaning: 'analyze',         category: 'op',       phase: 1 },
        { id: 55,  meaning: 'aggregate',       category: 'op',       phase: 1 },
        { id: 30,  meaning: 'transform',       category: 'op',       phase: 1 },
        // Phase 2 — relational & modifiers
        { id: 33,  meaning: 'causal-link',     category: 'rel',      phase: 2 },
        { id: 14,  meaning: 'contrast',        category: 'rel',      phase: 2 },
        { id: 200, meaning: 'temporal',        category: 'mod',      phase: 2 },
        { id: 8,   meaning: 'quantitative',    category: 'mod',      phase: 2 },
        { id: 77,  meaning: 'trend-up',        category: 'semantic', phase: 2 },
        { id: 78,  meaning: 'trend-down',      category: 'semantic', phase: 2 },
        { id: 120, meaning: 'entity-ref',      category: 'semantic', phase: 2 },
        { id: 156, meaning: 'sentiment-pos',   category: 'semantic', phase: 2 },
        // Phase 3 — meta tokens
        { id: 99,  meaning: 'confidence-hi',   category: 'meta',     phase: 3 },
        { id: 100, meaning: 'confidence-lo',   category: 'meta',     phase: 3 },
        { id: 250, meaning: 'uncertainty',     category: 'meta',     phase: 3 },
        { id: 11,  meaning: 'scope-global',    category: 'meta',     phase: 3 },
    ];

    const TASKS = [
        'Summarize quarterly earnings report',
        'Compare product A vs B metrics',
        'Extract findings from research paper',
        'Analyze customer sentiment trends',
        'Generate executive summary',
        'Classify document by topic',
        'Identify anomalies in dataset',
        'Translate technical spec to guide',
        'Prioritize action items from notes',
        'Evaluate campaign performance',
        'Correlate sales with market trends',
        'Synthesize multiple data sources',
        'Forecast next quarter projections',
        'Assess risk factors in proposal',
        'Map dependencies between projects',
    ];

    // ─── State ────────────────────────────────────────────────
    const state = {
        episode: 0,
        phase: 0,
        paused: false,
        startTime: Date.now(),
        lastEpisode: 0,
        rateTimer: 0,

        metrics: {
            compression: 1.0,
            fidelity: 0.0,
            avgTokens: 30,
            budget: 30,
        },

        history: {
            episodes: [],
            compression: [],
            fidelity: [],
            budget: [],
        },

        discoveredVocab: [],
        vocabIndex: 0,
        messageCount: 0,
        simTime: { hours: 12, minutes: 0, seconds: 0 },
    };

    // ─── DOM Helpers ──────────────────────────────────────────
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // ─── Canvas: Agent Visualizer ─────────────────────────────
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
        const compressionFactor = Math.min(state.metrics.compression / 16, 1);
        const count = Math.max(1, Math.round(5 * (1 - compressionFactor * 0.75)));
        const spread = 25 * (1 - compressionFactor * 0.6);

        for (let i = 0; i < count; i++) {
            particles.push({
                x: agentA.x + agentA.r + 4,
                y: agentA.y + (Math.random() - 0.5) * spread * 2,
                speed: 1.2 + Math.random() * 1.8,
                size: 1.5 + Math.random() * (1.5 + compressionFactor * 2),
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
            if (p.x > boundary - 40) {
                p.opacity *= 0.92;
            }
        }
        particles = particles.filter(p => p.x < boundary && p.opacity > 0.03);
    }

    function drawAgent(agent, pulse, isSending) {
        const r = agent.r * pulse;

        // Glow
        const grad = ctx.createRadialGradient(agent.x, agent.y, r * 0.2, agent.x, agent.y, r * 2.8);
        grad.addColorStop(0, `rgba(0, 240, 255, ${isSending ? 0.1 : 0.05})`);
        grad.addColorStop(1, 'rgba(0, 240, 255, 0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(agent.x, agent.y, r * 2.8, 0, Math.PI * 2);
        ctx.fill();

        // Ring
        ctx.beginPath();
        ctx.arc(agent.x, agent.y, r, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(0, 240, 255, ${isSending ? 0.7 : 0.35})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Inner ring
        ctx.beginPath();
        ctx.arc(agent.x, agent.y, r * 0.6, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(0, 240, 255, 0.1)';
        ctx.lineWidth = 0.5;
        ctx.stroke();

        // Core
        ctx.beginPath();
        ctx.arc(agent.x, agent.y, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#00f0ff';
        ctx.fill();
    }

    function renderCanvas() {
        if (!ctx || !canvasW) {
            requestAnimationFrame(renderCanvas);
            return;
        }

        ctx.clearRect(0, 0, canvasW, canvasH);

        // Connection line
        const lineAlpha = 0.03 + (state.metrics.fidelity * 0.04);
        ctx.beginPath();
        ctx.moveTo(agentA.x + agentA.r + 8, agentA.y);
        ctx.lineTo(agentB.x - agentB.r - 8, agentB.y);
        ctx.strokeStyle = `rgba(0, 240, 255, ${lineAlpha})`;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 8]);
        ctx.stroke();
        ctx.setLineDash([]);

        // Particles
        const colors = ['0, 240, 255', '124, 92, 252'];
        for (const p of particles) {
            const c = colors[p.hue];
            // Glow
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size * 3.5, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${c}, ${p.opacity * 0.06})`;
            ctx.fill();
            // Core
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${c}, ${p.opacity})`;
            ctx.fill();
        }

        // Agents
        const t = Date.now() * 0.002;
        const pulseA = Math.sin(t) * 0.06 + 0.94;
        const pulseB = Math.sin(t + Math.PI) * 0.06 + 0.94;
        drawAgent(agentA, pulseA, true);
        drawAgent(agentB, pulseB, false);

        // Spawn particles
        if (!state.paused && Math.random() < 0.35) {
            spawnParticles();
        }

        updateParticles();
        requestAnimationFrame(renderCanvas);
    }

    // ─── Charts ───────────────────────────────────────────────
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
                        label: 'Compression',
                        data: [],
                        borderColor: '#00f0ff',
                        backgroundColor: 'rgba(0, 240, 255, 0.04)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        borderWidth: 1.5,
                    },
                    {
                        label: 'Fidelity',
                        data: [],
                        borderColor: '#00ff88',
                        backgroundColor: 'rgba(0, 255, 136, 0.04)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        borderWidth: 1.5,
                        yAxisID: 'yFidelity',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.85)',
                        borderColor: 'rgba(255,255,255,0.06)',
                        borderWidth: 1,
                        titleFont: fontMono,
                        bodyFont: fontMono,
                        padding: 10,
                        cornerRadius: 8,
                        callbacks: {
                            label: (ctx) => {
                                if (ctx.datasetIndex === 0) return `Compression: ${ctx.parsed.y.toFixed(1)}x`;
                                return `Fidelity: ${ctx.parsed.y.toFixed(1)}%`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        display: true,
                        grid: { color: gridColor },
                        ticks: { color: tickColor, font: fontMono, maxTicksLimit: 6 },
                        title: { display: false },
                    },
                    y: {
                        display: true,
                        position: 'left',
                        grid: { color: gridColor },
                        ticks: { color: tickColor, font: fontMono },
                        min: 0, max: 20,
                        title: {
                            display: true, text: 'Compression (x)',
                            color: '#444', font: { size: 10 },
                        },
                    },
                    yFidelity: {
                        display: true,
                        position: 'right',
                        grid: { display: false },
                        ticks: { color: tickColor, font: fontMono },
                        min: 0, max: 100,
                        title: {
                            display: true, text: 'Fidelity (%)',
                            color: '#444', font: { size: 10 },
                        },
                    },
                },
            },
        });

        budgetChart = new Chart($('#budgetChart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Token Budget',
                    data: [],
                    borderColor: '#7c5cfc',
                    backgroundColor: 'rgba(124, 92, 252, 0.08)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    borderWidth: 1.5,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.85)',
                        borderColor: 'rgba(255,255,255,0.06)',
                        borderWidth: 1,
                        titleFont: fontMono,
                        bodyFont: fontMono,
                        padding: 10,
                        cornerRadius: 8,
                        callbacks: {
                            label: (ctx) => `Budget: ${ctx.parsed.y.toFixed(1)} tokens`,
                        },
                    },
                },
                scales: {
                    x: {
                        display: true,
                        grid: { color: gridColor },
                        ticks: { color: tickColor, font: fontMono, maxTicksLimit: 6 },
                    },
                    y: {
                        display: true,
                        grid: { color: gridColor },
                        ticks: { color: tickColor, font: fontMono },
                        min: 0, max: 35,
                        title: {
                            display: true, text: 'Max Tokens',
                            color: '#444', font: { size: 10 },
                        },
                    },
                },
            },
        });
    }

    // ─── Simulation Engine ────────────────────────────────────
    let simInterval;

    function startSimulation() {
        simInterval = setInterval(tick, CONFIG.TICK_INTERVAL);
    }

    function tick() {
        if (state.paused) return;

        // Advance episode
        const jitter = Math.floor(Math.random() * 7) - 3;
        state.episode += CONFIG.EPISODES_PER_TICK + jitter;

        // Advance simulated time
        advanceSimTime();

        // Phase check
        const newPhase = CONFIG.PHASES.findIndex(
            p => state.episode >= p.start && state.episode < p.end
        );
        if (newPhase >= 0 && newPhase !== state.phase) {
            state.phase = newPhase;
        }

        // Loop simulation
        if (state.episode >= CONFIG.TOTAL_EPISODES) {
            resetSimulation();
            return;
        }

        // Compute metrics
        computeMetrics();

        // Protocol message (~45% chance)
        if (Math.random() < 0.45) {
            generateFeedMessage();
        }

        // Discover vocabulary
        tryDiscoverToken();

        // Update charts
        updateChartData();

        // Update all UI
        updateUI();
    }

    function resetSimulation() {
        state.episode = 0;
        state.phase = 0;
        state.metrics = { compression: 1.0, fidelity: 0.0, avgTokens: 30, budget: 30 };
        state.history = { episodes: [], compression: [], fidelity: [], budget: [] };
        state.discoveredVocab = [];
        state.vocabIndex = 0;
        state.messageCount = 0;
        state.simTime = { hours: 12, minutes: 0, seconds: 0 };

        // Clear charts
        trainingChart.data.labels = [];
        trainingChart.data.datasets.forEach(d => d.data = []);
        trainingChart.update('none');
        budgetChart.data.labels = [];
        budgetChart.data.datasets[0].data = [];
        budgetChart.update('none');

        // Clear feed
        $('#protocolFeed').innerHTML = '';

        // Clear vocab
        $('#vocabGrid').innerHTML = '';
        $('#vocabCount').textContent = '0 tokens';

        // Reset phase timeline
        $$('.phase-item').forEach(el => {
            el.classList.remove('active', 'current');
        });
        $$('.phase-item')[0].classList.add('active', 'current');
        $$('.phase-connector').forEach(el => el.classList.remove('active'));
    }

    function computeMetrics() {
        const phase = CONFIG.PHASES[state.phase];
        const progress = clamp((state.episode - phase.start) / (phase.end - phase.start), 0, 1);
        const t = smoothstep(progress);

        const from = CONFIG.TARGETS[state.phase];
        const to = CONFIG.TARGETS[state.phase + 1];

        const noiseS = () => (Math.random() - 0.5) * 0.06;
        const noiseL = () => (Math.random() - 0.5) * 0.1;

        state.metrics.compression = Math.max(1, lerp(from.compression, to.compression, t) * (1 + noiseS()));
        state.metrics.fidelity = clamp(lerp(from.fidelity, to.fidelity, t) + noiseL() * 0.15, 0, 1);
        state.metrics.avgTokens = Math.max(3, Math.round(lerp(from.tokens, to.tokens, t) + (Math.random() - 0.5) * 2));
        state.metrics.budget = Math.max(5, lerp(from.budget, to.budget, t) + (Math.random() - 0.5) * 0.5);
    }

    function advanceSimTime() {
        state.simTime.seconds += 3;
        if (state.simTime.seconds >= 60) {
            state.simTime.seconds = 0;
            state.simTime.minutes++;
            if (state.simTime.minutes >= 60) {
                state.simTime.minutes = 0;
                state.simTime.hours = (state.simTime.hours + 1) % 24;
            }
        }
    }

    function formatSimTime() {
        const { hours, minutes, seconds } = state.simTime;
        return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }

    // ─── Feed Message Generator ──────────────────────────────
    function generateFeedMessage() {
        const task = TASKS[Math.floor(Math.random() * TASKS.length)];
        const tokenCount = state.metrics.avgTokens + Math.floor((Math.random() - 0.5) * 4);
        const actualTokens = Math.max(2, tokenCount);

        // Generate random protocol token IDs
        const ids = [];
        for (let i = 0; i < actualTokens; i++) {
            ids.push(Math.floor(Math.random() * 256));
        }

        const budgetOk = actualTokens <= Math.ceil(state.metrics.budget);
        const fidelity = budgetOk
            ? (state.metrics.fidelity * 100 + (Math.random() - 0.5) * 8).toFixed(1)
            : ((state.metrics.fidelity * 100) * 0.7 + (Math.random() - 0.5) * 10).toFixed(1);

        const success = budgetOk && Math.random() > 0.05;

        const senderIdx = Math.floor(Math.random() * 3) + 1;
        const receiverIdx = Math.floor(Math.random() * 3) + 1;

        const el = document.createElement('div');
        el.className = 'feed-message';

        const tokenStr = `ξ[${ids.slice(0, 5).join(',')}${ids.length > 5 ? '…' : ''}]→◊`;

        el.innerHTML = `
            <span class="feed-time">${formatSimTime()}</span>
            <span class="feed-route">α${senderIdx}→β${receiverIdx}</span>
            <span class="feed-tokens" title="${task}">${tokenStr} ${actualTokens}t</span>
            <span class="feed-status ${success ? 'success' : 'fail'}">${success ? fidelity + '%' : 'DROP'}</span>
        `;

        const feed = $('#protocolFeed');
        feed.insertBefore(el, feed.firstChild);

        // Trim
        while (feed.children.length > CONFIG.FEED_MAX) {
            feed.removeChild(feed.lastChild);
        }

        state.messageCount++;
    }

    // ─── Vocabulary Discovery ─────────────────────────────────
    function tryDiscoverToken() {
        if (state.vocabIndex >= VOCAB_POOL.length) return;

        const next = VOCAB_POOL[state.vocabIndex];
        if (state.phase >= next.phase && Math.random() < 0.12) {
            const freq = Math.floor(Math.random() * 1500) + 200;
            state.discoveredVocab.push({ ...next, freq });
            state.vocabIndex++;
            renderVocabToken(state.discoveredVocab[state.discoveredVocab.length - 1]);
            $('#vocabCount').textContent = `${state.discoveredVocab.length} tokens`;
        }
    }

    function renderVocabToken(token) {
        const maxFreq = Math.max(...state.discoveredVocab.map(t => t.freq), 1);
        const barWidth = Math.round((token.freq / maxFreq) * 100);

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

    // ─── Chart Data ───────────────────────────────────────────
    function updateChartData() {
        const MAX = CONFIG.CHART_HISTORY;
        const h = state.history;

        h.episodes.push(state.episode);
        h.compression.push(state.metrics.compression);
        h.fidelity.push(state.metrics.fidelity * 100);
        h.budget.push(state.metrics.budget);

        if (h.episodes.length > MAX) {
            h.episodes.shift();
            h.compression.shift();
            h.fidelity.shift();
            h.budget.shift();
        }

        // Training chart
        trainingChart.data.labels = h.episodes.map(String);
        trainingChart.data.datasets[0].data = [...h.compression];
        trainingChart.data.datasets[1].data = [...h.fidelity];
        trainingChart.update('none');

        // Budget chart
        budgetChart.data.labels = h.episodes.map(String);
        budgetChart.data.datasets[0].data = [...h.budget];
        budgetChart.update('none');
    }

    // ─── UI Updates ───────────────────────────────────────────
    function updateUI() {
        // Metric cards
        $('#metricPhase').textContent = state.phase;
        $('#metricPhaseName').textContent = CONFIG.PHASES[state.phase].name;
        $('#metricCompression').textContent = state.metrics.compression.toFixed(1);
        $('#metricFidelity').textContent = (state.metrics.fidelity * 100).toFixed(1);
        $('#metricEpisodes').textContent = state.episode.toLocaleString();

        // Rate calculation
        state.rateTimer++;
        if (state.rateTimer % 4 === 0) {
            const elapsed = (Date.now() - state.startTime) / 1000;
            const rate = elapsed > 0 ? Math.round(state.episode / elapsed) : 0;
            $('#metricRate').textContent = `${rate} ep/s`;
        }

        // Token count in viz
        $('#vizTokenCount').textContent = `${state.metrics.avgTokens} tokens`;

        // Phase timeline
        $$('.phase-item').forEach((el, i) => {
            el.classList.toggle('active', i <= state.phase);
            el.classList.toggle('current', i === state.phase);
        });
        const connectors = $$('.phase-connector');
        connectors.forEach((el, i) => {
            el.classList.toggle('active', i < state.phase);
        });

        // Nav progress bar
        const progress = (state.episode / CONFIG.TOTAL_EPISODES) * 100;
        $('#nav').style.setProperty('--progress', `${progress}%`);

        // Page title
        document.title = `OGENTI · Ep ${state.episode.toLocaleString()}`;
    }

    // ─── Pause / Resume ───────────────────────────────────────
    function togglePause() {
        state.paused = !state.paused;
        const indicator = $('.status-indicator');
        const statusText = $('#statusText');

        if (state.paused) {
            indicator.classList.add('paused');
            statusText.textContent = 'Paused';
        } else {
            indicator.classList.remove('paused');
            statusText.textContent = 'Training Active';
            state.startTime = Date.now() - (state.episode / CONFIG.EPISODES_PER_TICK * CONFIG.TICK_INTERVAL);
        }
    }

    // ─── Interactions ─────────────────────────────────────────
    function setupInteractions() {
        document.addEventListener('keydown', (e) => {
            if (e.code === 'Space' && e.target === document.body) {
                e.preventDefault();
                togglePause();
            }
        });

        // Click canvas to burst particles
        canvas.addEventListener('click', () => {
            for (let i = 0; i < 15; i++) {
                spawnParticles();
            }
        });
    }

    // ─── Utilities ────────────────────────────────────────────
    function lerp(a, b, t) { return a + (b - a) * t; }
    function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }
    function smoothstep(t) { return t * t * (3 - 2 * t); }

    // ─── Init ─────────────────────────────────────────────────
    function init() {
        initCanvas();
        initCharts();
        setupInteractions();
        startSimulation();

        // Hide loader
        setTimeout(() => {
            const loader = $('#loader');
            if (loader) loader.classList.add('hidden');
        }, 600);
    }

    // Wait for DOM + Chart.js
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
