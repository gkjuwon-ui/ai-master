import http from 'http';
import prisma from '../models';
import { config } from '../config';
import { NotFoundError, BadRequestError, ForbiddenError } from '../middleware/errorHandler';
import { logger } from '../utils/logger';
import { agentService } from './agentService';
import { llmService } from './llmService';
import { ogentTokenService } from './ogentTokenService';
import { wsService } from './websocketService';

/**
 * Reliable HTTP request using Node's built-in http module.
 * CRITICAL: Forces 127.0.0.1 for localhost to avoid IPv6 (::1) DNS resolution
 * on Node 17+ / Windows which fails when the target binds to 0.0.0.0 (IPv4 only).
 */
function runtimeFetch(
  urlStr: string,
  options?: { method?: string; headers?: Record<string, string>; body?: string; timeoutMs?: number }
): Promise<{ ok: boolean; status: number; text: () => Promise<string>; error?: string }> {
  // Use require() to guarantee the built-in module is loaded (no TS interop issues)
  const httpModule = require('http') as typeof http;

  return new Promise((resolve) => {
    try {
      const parsed = new URL(urlStr);
      const method = options?.method || 'GET';
      const body = options?.body;
      const timeoutMs = options?.timeoutMs || 10000;

      // Force IPv4 for localhost — this is the critical fix
      const hostname = (parsed.hostname === 'localhost' || parsed.hostname === '::1')
        ? '127.0.0.1'
        : parsed.hostname;

      const reqOptions: http.RequestOptions = {
        hostname,
        port: parseInt(parsed.port || '80', 10),
        path: parsed.pathname + parsed.search,
        method,
        headers: {
          ...(options?.headers || {}),
          ...(body ? { 'Content-Length': String(Buffer.byteLength(body)) } : {}),
        },
        timeout: timeoutMs,
      };

      const req = httpModule.request(reqOptions, (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (chunk: Buffer) => chunks.push(chunk));
        res.on('end', () => {
          const status = res.statusCode || 0;
          const bodyStr = Buffer.concat(chunks).toString('utf8');
          resolve({
            ok: status >= 200 && status < 300,
            status,
            text: () => Promise.resolve(bodyStr),
          });
        });
        res.on('error', (e) =>
          resolve({ ok: false, status: 0, text: () => Promise.resolve('response error'), error: e.message })
        );
      });

      req.on('error', (err) => {
        resolve({ ok: false, status: 0, text: () => Promise.resolve(err.message), error: err.message });
      });
      req.on('timeout', () => {
        req.destroy();
        resolve({ ok: false, status: 0, text: () => Promise.resolve('timeout'), error: 'timeout' });
      });

      if (body) req.write(body);
      req.end();
    } catch (err: any) {
      resolve({ ok: false, status: 0, text: () => Promise.resolve(err.message), error: err.message });
    }
  });
}

// ── Capability keyword mapping ──────────────────────────────────────────
// Maps task-related keywords in the user prompt to required AgentCapability values.
const CAPABILITY_KEYWORD_MAP: Record<string, string[]> = {
  // Coding / Development
  CODING: [
    'code', 'coding', 'program', 'programming', 'develop', 'development', 'debug', 'compile',
    'build', 'deploy', 'git', 'commit', 'push', 'pull', 'merge', 'refactor',
    'test', 'unit test', 'integration', 'api', 'backend', 'frontend', 'database',
    'sql', 'python', 'javascript', 'typescript', 'java', 'c++', 'rust', 'go',
    'react', 'vue', 'angular', 'node', 'django', 'flask', 'spring',
    'html', 'css', 'scss', 'webpack', 'vite', 'npm', 'pip', 'cargo',
    'function', 'class', 'variable', 'algorithm', 'data structure',
    '코딩', '코드', '프로그래밍', '개발', '디버그', '컴파일', '빌드', '배포',
  ],
  // Design / UI / Visual
  DESIGN: [
    'design', 'mockup', 'wireframe', 'prototype', 'ui', 'ux', 'layout',
    'figma', 'sketch', 'photoshop', 'illustrator', 'canva',
    'logo', 'icon', 'banner', 'poster', 'image', 'graphic', 'visual',
    'color', 'palette', 'typography', 'font', 'animation', 'illustration',
    'paint', 'draw', 'drawing', 'artwork', 'pixel',
    '디자인', '목업', '와이어프레임', '프로토타입', '로고', '아이콘', '배너',
    '이미지', '그래픽', '색상', '폰트', '그리기', '그림',
  ],
  // Research / Analysis
  RESEARCH: [
    'research', 'search', 'find', 'lookup', 'investigate', 'analyze', 'analysis',
    'report', 'summary', 'summarize', 'compare', 'review', 'study',
    'data', 'statistics', 'chart', 'graph', 'trend', 'insight',
    'web search', 'google', 'browse', 'crawl', 'scrape',
    '검색', '조사', '분석', '리서치', '요약', '보고서', '통계', '비교',
  ],
  // Writing / Documentation
  WRITING: [
    'write', 'writing', 'document', 'documentation', 'blog', 'article',
    'essay', 'email', 'letter', 'content', 'copywriting', 'editing',
    'proofread', 'translate', 'translation', 'text', 'paragraph',
    'markdown', 'readme', 'wiki', 'manual', 'guide', 'tutorial',
    '작성', '글쓰기', '문서', '블로그', '기사', '이메일', '번역', '교정',
  ],
  // Automation / System
  AUTOMATION: [
    'automate', 'automation', 'script', 'bot', 'cron', 'schedule',
    'workflow', 'pipeline', 'batch', 'macro', 'process',
    'install', 'configure', 'setup', 'deploy', 'monitor',
    '자동화', '스크립트', '봇', '워크플로우', '설치', '설정',
  ],
};

// Maps task categories to AgentCategory values
const CATEGORY_CAPABILITY_MAP: Record<string, string> = {
  CODING: 'CODING',
  DESIGN: 'DESIGN',
  RESEARCH: 'RESEARCH',
  WRITING: 'WRITING',
  AUTOMATION: 'AUTOMATION',
};

/** Analyze prompt to determine which task categories are required */
function analyzePromptCategories(prompt: string): string[] {
  const lowerPrompt = prompt.toLowerCase();
  const detectedCategories: string[] = [];

  for (const [category, keywords] of Object.entries(CAPABILITY_KEYWORD_MAP)) {
    for (const keyword of keywords) {
      if (lowerPrompt.includes(keyword.toLowerCase())) {
        if (!detectedCategories.includes(category)) {
          detectedCategories.push(category);
        }
        break; // Found a match for this category, move to next
      }
    }
  }

  return detectedCategories;
}

export class ExecutionService {
  private activeSessions = new Map<string, { cancel: () => void }>();

  /**
   * Check whether the selected agents have the capabilities required by the prompt.
   * Returns { ok: true } when compatible, or { ok: false, ... } with details about the mismatch
   * and marketplace suggestions.
   */
  async checkCapabilities(userId: string, data: {
    prompt: string;
    agentIds: string[];
  }) {
    const requiredCategories = analyzePromptCategories(data.prompt);

    if (requiredCategories.length === 0) {
      // Unable to determine – allow execution
      return { ok: true, requiredCategories: [], missingCategories: [], suggestedAgents: [] };
    }

    // Gather categories of selected agents
    const selectedAgentCategories: string[] = [];
    const selectedAgentDetails: any[] = [];
    for (const agentId of data.agentIds) {
      const agent = await prisma.agent.findUnique({ where: { id: agentId } });
      if (agent) {
        selectedAgentCategories.push(agent.category);
        selectedAgentDetails.push({
          id: agent.id,
          name: agent.name,
          category: agent.category,
          capabilities: agent.capabilities ? JSON.parse(agent.capabilities) : [],
        });
      }
    }

    // Determine which required categories are NOT covered by selected agents
    const missingCategories = requiredCategories.filter(
      (cat) => !selectedAgentCategories.includes(CATEGORY_CAPABILITY_MAP[cat] || cat)
    );

    if (missingCategories.length === 0) {
      return { ok: true, requiredCategories, missingCategories: [], suggestedAgents: [] };
    }

    // Find marketplace agents that cover the missing categories
    const suggestedAgents: any[] = [];
    for (const missingCat of missingCategories) {
      const mappedCategory = CATEGORY_CAPABILITY_MAP[missingCat] || missingCat;
      const agents = await prisma.agent.findMany({
        where: {
          status: 'PUBLISHED',
          category: mappedCategory,
          id: { notIn: data.agentIds },
        },
        include: {
          developer: {
            select: { id: true, username: true, displayName: true, avatar: true },
          },
        },
        take: 6,
        orderBy: { downloads: 'desc' },
      });

      for (const agent of agents) {
        // Check if user already owns this agent
        const hasAccess = await agentService.hasAccess(userId, agent.id);
        suggestedAgents.push({
          id: agent.id,
          name: agent.name,
          slug: agent.slug,
          description: agent.description,
          category: agent.category,
          icon: agent.icon,
          price: agent.price,
          pricingModel: agent.pricingModel,
          rating: agent.rating,
          downloads: agent.downloads,
          capabilities: agent.capabilities ? JSON.parse(agent.capabilities) : [],
          developer: agent.developer ? { ...agent.developer, verified: true } : undefined,
          owned: hasAccess,
        });
      }
    }

    const categoryLabels: Record<string, string> = {
      CODING: 'Coding',
      DESIGN: 'Design',
      RESEARCH: 'Research',
      WRITING: 'Writing',
      AUTOMATION: 'Automation',
    };

    return {
      ok: false,
      requiredCategories: requiredCategories.map((c) => categoryLabels[c] || c),
      missingCategories: missingCategories.map((c) => categoryLabels[c] || c),
      selectedAgents: selectedAgentDetails,
      suggestedAgents,
      message: `This task requires ${missingCategories.map((c) => categoryLabels[c] || c).join(', ')} capabilities, but the selected agents do not have them.`,
    };
  }

  async createSession(userId: string, data: {
    name?: string;
    prompt: string;
    agentIds: string[];
    llmConfigId: string;
    config?: {
      maxExecutionTime?: number;
      screenshotInterval?: number;
      sandboxMode?: boolean;
    };
  }) {
    // Validate agents access
    for (const agentId of data.agentIds) {
      const hasAccess = await agentService.hasAccess(userId, agentId);
      if (!hasAccess) {
        throw new ForbiddenError(`No access to agent: ${agentId}`);
      }
    }

    // Validate LLM config
    const llmConfig = await llmService.getConfig(data.llmConfigId, userId);
    if (!llmConfig) throw new NotFoundError('LLM Config');

    // Build agents array with details
    const agents = await Promise.all(
      data.agentIds.map(async (agentId, index) => {
        const agent = await prisma.agent.findUnique({ where: { id: agentId } });
        return {
          agentId,
          name: agent?.name || 'Unknown',
          icon: agent?.icon || '',
          order: index,
          status: 'QUEUED',
          config: {},
        };
      })
    );

    const executionConfig = {
      maxExecutionTime: data.config?.maxExecutionTime || config.agentRuntime.maxExecutionTime,
      screenshotInterval: data.config?.screenshotInterval || config.agentRuntime.screenshotInterval,
      sandboxMode: data.config?.sandboxMode ?? true,
      llmConfigId: data.llmConfigId,
    };

    const session = await prisma.executionSession.create({
      data: {
        userId,
        name: data.name || `Execution ${new Date().toLocaleString()}`,
        prompt: data.prompt,
        status: 'PENDING',
        config: JSON.stringify(executionConfig),
        agents: JSON.stringify(agents),
      },
    });

    logger.info(`Execution session created: ${session.id}`);
    return this.formatSession(session);
  }

  async getSession(sessionId: string, userId: string) {
    const session = await prisma.executionSession.findUnique({
      where: { id: sessionId },
      include: { logs: { orderBy: { createdAt: 'asc' }, take: 200 } },
    });
    if (!session) throw new NotFoundError('Execution session');
    if (session.userId !== userId) throw new ForbiddenError('Not your session');
    return this.formatSession(session);
  }

  async getUserSessions(userId: string, page = 1, limit = 20) {
    const skip = (page - 1) * limit;
    const [sessions, total] = await Promise.all([
      prisma.executionSession.findMany({
        where: { userId },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limit,
      }),
      prisma.executionSession.count({ where: { userId } }),
    ]);
    return {
      sessions: sessions.map(this.formatSession),
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit),
    };
  }

  async startExecution(sessionId: string, userId: string): Promise<void> {
    const session = await prisma.executionSession.findUnique({ where: { id: sessionId } });
    if (!session) throw new NotFoundError('Execution session');
    if (session.userId !== userId) throw new ForbiddenError('Not your session');
    if (session.status !== 'PENDING' && session.status !== 'PAUSED') {
      throw new BadRequestError('Session cannot be started');
    }

    // Start execution
    await prisma.executionSession.update({
      where: { id: sessionId },
      data: {
        status: 'RUNNING',
        startedAt: session.startedAt || new Date(),
      },
    });

    // Broadcast RUNNING status
    wsService?.broadcastToSession(sessionId, 'execution_status', {
      status: 'RUNNING',
    });

    // Get decrypted LLM config
    const sessionConfig = JSON.parse(session.config);
    const llmConfig = await llmService.getDecryptedConfig(sessionConfig.llmConfigId, userId);

    // Add log entry
    await this.addLog(sessionId, {
      agentId: 'system',
      level: 'INFO',
      type: 'SYSTEM',
      message: 'Execution started',
    });

    // Send execution request to Python agent runtime
    this.dispatchToRuntime(sessionId, session, llmConfig);
  }

  /** Wait for agent runtime to become healthy (up to maxWaitMs). */
  private async waitForRuntime(maxWaitMs = 30000): Promise<boolean> {
    const start = Date.now();
    logger.info(`Waiting for runtime at ${config.agentRuntime.url}/health (max ${maxWaitMs}ms)`);
    while (Date.now() - start < maxWaitMs) {
      try {
        const res = await runtimeFetch(`${config.agentRuntime.url}/health`, { timeoutMs: 3000 });
        if (res.ok) {
          logger.info(`Runtime health OK after ${Date.now() - start}ms`);
          return true;
        }
        const errDetail = res.error || await res.text();
        logger.debug(`Runtime health returned status=${res.status} error=${errDetail}`);
      } catch (err: any) {
        logger.debug(`Runtime health error: ${err.message}`);
      }
      await new Promise(r => setTimeout(r, 1000));
    }
    logger.error(`Runtime health check failed after ${maxWaitMs}ms`);
    return false;
  }

  private async dispatchToRuntime(sessionId: string, session: any, llmConfig: any) {
    try {
      // Wait for the runtime to be ready before dispatching
      await this.addLog(sessionId, {
        agentId: 'system', level: 'INFO', type: 'SYSTEM',
        message: 'Connecting to agent runtime...',
      });

      const runtimeReady = await this.waitForRuntime(30000);
      if (!runtimeReady) {
        await this.failSession(sessionId, 'Agent runtime is not running. Please ensure the Python runtime is started (port 5000).');
        return;
      }

      const agents = JSON.parse(session.agents);
      const sessionConfig = JSON.parse(session.config);

      const payload = {
        session_id: sessionId,
        prompt: session.prompt,
        agent_ids: agents.map((a: any) => a.agentId),
        agents: await Promise.all(
          agents.map(async (a: any) => {
            const agent = await prisma.agent.findUnique({
              where: { id: a.agentId },
              include: { llmConfig: true },
            });

            // Resolve per-agent LLM config: agent's own → session default
            let agentLlmConfig = null;
            if (agent?.llmConfigId && agent.llmConfig) {
              try {
                const decrypted = await llmService.getDecryptedConfig(agent.llmConfigId, session.userId);
                agentLlmConfig = {
                  provider: decrypted.provider,
                  model: decrypted.model,
                  apiKey: decrypted.apiKey,
                  baseUrl: decrypted.baseUrl,
                };
              } catch {
                // Fall back to session default if decryption fails
              }
            }

            // Resolve user's custom persona for this agent
            let persona: string | null = null;
            try {
              const purchase = await prisma.purchase.findUnique({
                where: { userId_agentId: { userId: session.userId, agentId: a.agentId } },
                select: { persona: true },
              });
              persona = purchase?.persona || null;
            } catch {
              // non-critical
            }

            return {
              id: a.agentId,
              name: a.name,
              slug: agent?.slug || '',
              entryPoint: agent?.entryPoint || 'main.py',
              runtime: agent?.runtime || 'python',
              bundlePath: agent?.bundlePath,
              capabilities: agent?.capabilities ? JSON.parse(agent.capabilities) : [],
              config: a.config || {},
              llm_config: agentLlmConfig,  // per-agent LLM (null = use session default)
              persona: persona,  // user's custom prompt/persona (null = use default)
            };
          })
        ),
        llm_config: llmConfig.provider === 'OGENT'
          ? {
              ...ogentTokenService.resolveOgentConfig('execute'),
              __ogent: true,
              __ogentOwnerId: session.userId,
            }
          : {
              provider: llmConfig.provider,
              model: llmConfig.model,
              apiKey: llmConfig.apiKey,
              baseUrl: llmConfig.baseUrl,
            },
        config: {
          maxExecutionTime: sessionConfig.maxExecutionTime,
          screenshotInterval: sessionConfig.screenshotInterval,
          sandboxMode: sessionConfig.sandboxMode,
        },
      };

      // Try WebSocket command channel first, fall back to HTTP
      const wsSent = wsService?.sendToRuntime(session.userId, {
        type: 'execute',
        ...payload,
      });

      if (wsSent) {
        await this.addLog(sessionId, {
          agentId: 'system', level: 'INFO', type: 'SYSTEM',
          message: 'Dispatched to agent runtime via WebSocket',
        });
        return;
      }

      // Fallback: direct HTTP (for local dev or legacy)
      let lastError = '';
      for (let attempt = 1; attempt <= 3; attempt++) {
        try {
          const response = await runtimeFetch(`${config.agentRuntime.url}/execute`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Runtime-Secret': config.agentRuntime.secret,
            },
            body: JSON.stringify(payload),
            timeoutMs: 15000,
          });

          if (response.ok) {
            await this.addLog(sessionId, {
              agentId: 'system', level: 'INFO', type: 'SYSTEM',
              message: 'Dispatched to agent runtime successfully',
            });
            return;
          }

          lastError = await response.text();
          logger.error(`Runtime dispatch attempt ${attempt} failed: ${lastError}`);
        } catch (err: any) {
          lastError = err.message;
          logger.error(`Runtime dispatch attempt ${attempt} error: ${lastError}`);
        }

        if (attempt < 3) await new Promise(r => setTimeout(r, 2000));
      }

      await this.failSession(sessionId, `Failed to connect to agent runtime after 3 attempts: ${lastError}`);
    } catch (error: any) {
      logger.error(`Failed to dispatch to runtime: ${error.message}`);
      await this.failSession(sessionId, `Failed to connect to agent runtime: ${error.message}`);
    }
  }

  async handleRuntimeCallback(sessionId: string, data: {
    type: 'log' | 'status' | 'screenshot' | 'complete' | 'error' | 'agent_status';
    [key: string]: any;
  }) {
    switch (data.type) {
      case 'log':
        // Persist session-level metrics snapshot (best-effort)
        if (data.logType === 'METRIC' && data.message === 'session_metrics') {
          try {
            await prisma.executionMetric.upsert({
              where: { sessionId },
              create: {
                sessionId,
                data: JSON.stringify(data.data || {}),
              },
              update: {
                data: JSON.stringify(data.data || {}),
              },
            });
          } catch (err) {
            logger.debug(`Failed to upsert execution metrics for session=${sessionId}`);
          }
        }
        await this.addLog(sessionId, {
          agentId: data.agentId || 'system',
          level: data.level || 'INFO',
          type: data.logType || 'AGENT',
          message: data.message,
          data: data.data,
        });
        break;

      case 'screenshot':
        await this.addLog(sessionId, {
          agentId: data.agentId || 'system',
          level: 'INFO',
          type: 'SCREENSHOT',
          message: 'Screenshot captured',
          screenshot: data.screenshot,
        });
        // Broadcast screenshot to frontend
        wsService?.broadcastToSession(sessionId, 'execution_screenshot', {
          screenshot: data.screenshot,
          agentId: data.agentId || 'system',
        });
        break;

      case 'status':
      case 'agent_status':
        await this.updateAgentStatus(sessionId, data.agentId, data.status);
        break;

      case 'complete':
        await this.completeSession(sessionId, data.result);
        break;

      case 'error':
        await this.failSession(sessionId, data.message || data.error || 'Unknown error');
        break;
    }
  }

  async pauseExecution(sessionId: string, userId: string) {
    const session = await prisma.executionSession.findUnique({ where: { id: sessionId } });
    if (!session) throw new NotFoundError('Execution session');
    if (session.userId !== userId) throw new ForbiddenError('Not your session');
    if (session.status !== 'RUNNING') throw new BadRequestError('Session not running');

    await prisma.executionSession.update({
      where: { id: sessionId },
      data: { status: 'PAUSED' },
    });

    // Signal runtime to pause (WebSocket first, HTTP fallback)
    const pauseSent = wsService?.sendToRuntime(session.userId, { type: 'pause', session_id: sessionId });
    if (!pauseSent) {
      await runtimeFetch(`${config.agentRuntime.url}/pause`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Runtime-Secret': config.agentRuntime.secret },
        body: JSON.stringify({ session_id: sessionId }),
      }).catch(() => {});
    }
  }

  async cancelExecution(sessionId: string, userId: string) {
    const session = await prisma.executionSession.findUnique({ where: { id: sessionId } });
    if (!session) throw new NotFoundError('Execution session');
    if (session.userId !== userId) throw new ForbiddenError('Not your session');

    await prisma.executionSession.update({
      where: { id: sessionId },
      data: { status: 'CANCELLED', completedAt: new Date() },
    });

    // Signal runtime to cancel (WebSocket first, HTTP fallback)
    const cancelSent = wsService?.sendToRuntime(session.userId, { type: 'cancel', session_id: sessionId });
    if (!cancelSent) {
      await runtimeFetch(`${config.agentRuntime.url}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Runtime-Secret': config.agentRuntime.secret },
        body: JSON.stringify({ session_id: sessionId }),
      }).catch(() => {});
    }

    await this.addLog(sessionId, {
      agentId: 'system',
      level: 'INFO',
      type: 'SYSTEM',
      message: 'Execution cancelled by user',
    });
  }

  async addLog(sessionId: string, log: {
    agentId: string;
    level: string;
    type: string;
    message: string;
    data?: any;
    screenshot?: string;
  }) {
    const created = await prisma.executionLog.create({
      data: {
        sessionId,
        agentId: log.agentId,
        level: log.level,
        type: log.type,
        message: log.message,
        data: log.data ? JSON.stringify(log.data) : null,
        screenshot: log.screenshot,
      },
    });

    // Broadcast log to subscribed frontend clients
    wsService?.broadcastToSession(sessionId, 'execution_log', {
      id: created.id,
      agentId: log.agentId,
      level: log.level,
      type: log.type,
      message: log.message,
      data: log.data,
      screenshot: log.screenshot,
      createdAt: created.createdAt,
    });

    return created;
  }

  async getSessionLogs(sessionId: string, userId: string, after?: string) {
    const session = await prisma.executionSession.findUnique({ where: { id: sessionId } });
    if (!session) throw new NotFoundError('Session');
    if (session.userId !== userId) throw new ForbiddenError('Not your session');

    const where: any = { sessionId };
    if (after) {
      where.createdAt = { gt: new Date(after) };
    }

    return prisma.executionLog.findMany({
      where,
      orderBy: { createdAt: 'asc' },
      take: 100,
    });
  }

  private async updateAgentStatus(sessionId: string, agentId: string, status: string) {
    const session = await prisma.executionSession.findUnique({ where: { id: sessionId } });
    if (!session) return;

    const agents = JSON.parse(session.agents);
    const agentIndex = agents.findIndex((a: any) => a.agentId === agentId);
    if (agentIndex >= 0) {
      agents[agentIndex].status = status;
      await prisma.executionSession.update({
        where: { id: sessionId },
        data: { agents: JSON.stringify(agents) },
      });
    }

    // Broadcast agent status update to frontend
    wsService?.broadcastToSession(sessionId, 'execution_status', {
      agentId,
      status,
      agents,
    });
  }

  private async completeSession(sessionId: string, result: any) {
    await prisma.executionSession.update({
      where: { id: sessionId },
      data: {
        status: 'COMPLETED',
        completedAt: new Date(),
        result: JSON.stringify(result),
      },
    });
    await this.addLog(sessionId, {
      agentId: 'system',
      level: 'INFO',
      type: 'SYSTEM',
      message: 'Execution completed successfully',
    });

    // Broadcast completion to frontend
    wsService?.broadcastToSession(sessionId, 'execution_completed', {
      status: 'COMPLETED',
      result,
    });

    logger.info(`Execution completed: ${sessionId}`);
  }

  private async failSession(sessionId: string, error: string) {
    await prisma.executionSession.update({
      where: { id: sessionId },
      data: {
        status: 'FAILED',
        completedAt: new Date(),
        result: JSON.stringify({ success: false, summary: error, artifacts: [], screenshots: [], totalTime: 0, tokensUsed: 0, cost: 0 }),
      },
    });
    await this.addLog(sessionId, {
      agentId: 'system',
      level: 'ERROR',
      type: 'SYSTEM',
      message: error,
    });

    // Broadcast failure to frontend
    wsService?.broadcastToSession(sessionId, 'execution_error', {
      status: 'FAILED',
      message: error,
    });

    logger.error(`Execution failed: ${sessionId} - ${error}`);
  }

  async deleteSession(sessionId: string, userId: string) {
    const session = await prisma.executionSession.findUnique({ where: { id: sessionId } });
    if (!session) throw new NotFoundError('Execution session');
    if (session.userId !== userId) throw new ForbiddenError('Not your session');

    await prisma.executionLog.deleteMany({ where: { sessionId } });
    await prisma.executionSession.delete({ where: { id: sessionId } });
  }

  private formatSession(session: any) {
    return {
      ...session,
      config: typeof session.config === 'string' ? JSON.parse(session.config) : session.config,
      agents: typeof session.agents === 'string' ? JSON.parse(session.agents) : session.agents,
      result: session.result ? (typeof session.result === 'string' ? JSON.parse(session.result) : session.result) : null,
      logs: session.logs?.map((l: any) => ({
        ...l,
        data: l.data ? (typeof l.data === 'string' ? JSON.parse(l.data) : l.data) : null,
      })) || [],
    };
  }
}

export const executionService = new ExecutionService();
