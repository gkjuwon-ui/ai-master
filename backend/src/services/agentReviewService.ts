/**
 * Agent Security Review Service
 * 
 * Uses LLM + static analysis to review agent plugins before marketplace publishing.
 * Rejects any agent that contains security risks (hacking, data exfiltration,
 * privilege escalation, malicious commands, etc.)
 */

import { logger } from '../utils/logger';
import { config } from '../config';
import prisma from '../models';
import { decrypt } from '../utils/crypto';

// ── Types ────────────────────────────────────────────────────────────

export type ReviewVerdict = 'APPROVED' | 'REJECTED';
export type RiskLevel = 'NONE' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface SecurityFinding {
  rule: string;
  severity: RiskLevel;
  description: string;
  line?: number;
  snippet?: string;
}

export interface ReviewReport {
  verdict: ReviewVerdict;
  overallRisk: RiskLevel;
  findings: SecurityFinding[];
  summary: string;
  llmAnalysis?: string;
  reviewedAt: string;
  reviewDurationMs: number;
}

// ── Dangerous Pattern Definitions ────────────────────────────────────

const DANGEROUS_PATTERNS: {
  pattern: RegExp;
  rule: string;
  severity: RiskLevel;
  description: string;
}[] = [
  // -- Data Exfiltration --
  {
    pattern: /requests?\.(get|post|put|patch|delete)\s*\(\s*["'`]https?:\/\//i,
    rule: 'NETWORK_EXFIL',
    severity: 'HIGH',
    description: 'Outbound HTTP request to external URL — possible data exfiltration',
  },
  {
    pattern: /urllib|httplib|aiohttp\.ClientSession|fetch\s*\(|axios\s*[\.(]/i,
    rule: 'NETWORK_LIB',
    severity: 'MEDIUM',
    description: 'Network library imported — review for unauthorized external communication',
  },
  {
    pattern: /socket\.(socket|connect|bind|listen)/i,
    rule: 'RAW_SOCKET',
    severity: 'CRITICAL',
    description: 'Raw socket usage — severe security risk',
  },
  // -- File System Abuse --
  {
    pattern: /(?:open|read|write)\s*\(\s*["'`](?:\/etc\/passwd|\/etc\/shadow|C:\\Windows\\System32)/i,
    rule: 'SYSTEM_FILE_ACCESS',
    severity: 'CRITICAL',
    description: 'Attempted access to system-critical files',
  },
  {
    pattern: /shutil\.rmtree\s*\(\s*["'`](?:\/|C:\\|~)/i,
    rule: 'RECURSIVE_DELETE',
    severity: 'CRITICAL',
    description: 'Recursive deletion of root/home directory',
  },
  {
    pattern: /\.ssh\/|id_rsa|authorized_keys|\.gnupg/i,
    rule: 'SSH_KEY_ACCESS',
    severity: 'CRITICAL',
    description: 'Attempted access to SSH keys or credentials',
  },
  // -- Code Injection / Execution --
  {
    pattern: /\beval\s*\(|\bexec\s*\(|\bcompile\s*\(/i,
    rule: 'CODE_INJECTION',
    severity: 'HIGH',
    description: 'Dynamic code execution (eval/exec) — injection risk',
  },
  {
    pattern: /subprocess\.(call|run|Popen|check_output)|os\.system|os\.popen|child_process/i,
    rule: 'SHELL_EXEC',
    severity: 'HIGH',
    description: 'Shell command execution — potential for arbitrary command injection',
  },
  {
    pattern: /ctypes|cffi|CDLL|windll|kernel32|ntdll/i,
    rule: 'NATIVE_CODE',
    severity: 'HIGH',
    description: 'Native code / FFI usage — can bypass all sandboxing',
  },
  // -- Credential Theft --
  {
    pattern: /keyring|getpass|win32cred|credential_manager/i,
    rule: 'CREDENTIAL_ACCESS',
    severity: 'CRITICAL',
    description: 'Credential store access — possible password theft',
  },
  {
    pattern: /BROWSER_COOKIE|chrome.*cookies|firefox.*cookies|\.cookies\b/i,
    rule: 'COOKIE_THEFT',
    severity: 'CRITICAL',
    description: 'Browser cookie access — session hijacking risk',
  },
  {
    pattern: /environ\s*\[\s*["'`](API_KEY|SECRET|TOKEN|PASSWORD|PRIVATE_KEY)/i,
    rule: 'ENV_SECRET_READ',
    severity: 'HIGH',
    description: 'Reading sensitive environment variables',
  },
  // -- Privilege Escalation --
  {
    pattern: /setuid|setgid|chmod\s+[0-7]*7|sudo\s|runas\s|net\s+user|net\s+localgroup/i,
    rule: 'PRIV_ESCALATION',
    severity: 'CRITICAL',
    description: 'Privilege escalation attempt',
  },
  {
    pattern: /registry|winreg|RegOpenKey|HKEY_LOCAL_MACHINE|HKEY_CURRENT_USER/i,
    rule: 'REGISTRY_ACCESS',
    severity: 'HIGH',
    description: 'Windows Registry access — can modify system configuration',
  },
  // -- Persistence Mechanisms --
  {
    pattern: /crontab|schtasks|startup\s*folder|autorun|HKCU.*\\Run/i,
    rule: 'PERSISTENCE',
    severity: 'CRITICAL',
    description: 'Persistence mechanism — attempts to survive restarts',
  },
  {
    pattern: /systemctl\s+(enable|start)|launchctl\s+load|service\s+.*start/i,
    rule: 'SERVICE_INSTALL',
    severity: 'CRITICAL',
    description: 'System service installation — persistent background access',
  },
  // -- Crypto Mining / Abuse --
  {
    pattern: /stratum\+tcp|cryptonight|xmrig|hashrate|mining.pool/i,
    rule: 'CRYPTOMINER',
    severity: 'CRITICAL',
    description: 'Cryptocurrency mining indicators detected',
  },
  // -- Obfuscation --
  {
    pattern: /base64\.(b64decode|decodebytes)\s*\(\s*["'`][A-Za-z0-9+\/=]{50,}/i,
    rule: 'ENCODED_PAYLOAD',
    severity: 'HIGH',
    description: 'Large base64-encoded payload — possible obfuscated malicious code',
  },
  {
    pattern: /\\x[0-9a-f]{2}(?:\\x[0-9a-f]{2}){20,}/i,
    rule: 'HEX_SHELLCODE',
    severity: 'CRITICAL',
    description: 'Hex-encoded shellcode pattern detected',
  },
  // -- Anti-Analysis --
  {
    pattern: /is_debugger|IsDebuggerPresent|ptrace|strace|ltrace/i,
    rule: 'ANTI_DEBUG',
    severity: 'HIGH',
    description: 'Anti-debugging technique — attempting to evade analysis',
  },
];

// ── Static Analyzer ──────────────────────────────────────────────────

function staticAnalysis(code: string): SecurityFinding[] {
  const findings: SecurityFinding[] = [];
  const lines = code.split('\n');

  for (const { pattern, rule, severity, description } of DANGEROUS_PATTERNS) {
    for (let i = 0; i < lines.length; i++) {
      if (pattern.test(lines[i])) {
        findings.push({
          rule,
          severity,
          description,
          line: i + 1,
          snippet: lines[i].trim().slice(0, 120),
        });
      }
    }
  }

  return findings;
}

// ── LLM Review ───────────────────────────────────────────────────────

const REVIEW_SYSTEM_PROMPT = `You are a senior security auditor for the ogenti AI Agent Marketplace.
Your job is to review agent plugin source code for ANY security risks before it is published.

REVIEW CRITERIA (reject if ANY apply):
1. DATA EXFILTRATION: Sends user data to external servers
2. CREDENTIAL THEFT: Reads passwords, API keys, tokens, cookies, SSH keys
3. PRIVILEGE ESCALATION: Attempts sudo, admin, registry modifications
4. MALWARE BEHAVIOR: Persistence mechanisms, crypto mining, keyloggers
5. CODE INJECTION: eval/exec with untrusted input, deserialization attacks
6. FILESYSTEM ABUSE: Reads/writes outside the agent's working scope
7. NETWORK ABUSE: Opens raw sockets, tunnels, reverse shells
8. OBFUSCATION: Heavily encoded payloads hiding true intent
9. ANTI-ANALYSIS: Debugger detection, environment checks to evade review
10. SOCIAL ENGINEERING: Tricks users into granting extra permissions

RESPONSE FORMAT (strict JSON only, no markdown):
{
  "verdict": "APPROVED" or "REJECTED",
  "risk_level": "NONE" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "findings": [
    {
      "rule": "SHORT_RULE_ID",
      "severity": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
      "description": "What the risk is and why",
      "line": <line_number_or_null>,
      "snippet": "offending code snippet or null"
    }
  ],
  "summary": "One paragraph overall assessment"
}

IMPORTANT:
- Be thorough but fair. Normal OS automation (pyautogui, mss screenshots, keyboard/mouse) is EXPECTED.
- Agents ARE SUPPOSED to control mouse, keyboard, take screenshots — that is their core function.
- Only flag actions that go BEYOND legitimate OS automation into malicious territory.
- When in doubt, REJECT. User safety is paramount.
- Respond with ONLY the JSON object. No explanations outside the JSON.`;

async function llmReview(
  code: string,
  manifest: Record<string, any>,
  llmConfig: { provider: string; model: string; apiKey: string; baseUrl?: string | null }
): Promise<{ verdict: ReviewVerdict; riskLevel: RiskLevel; findings: SecurityFinding[]; summary: string; raw: string }> {
  const userMessage = `Review this agent plugin for security risks.

MANIFEST:
${JSON.stringify(manifest, null, 2)}

SOURCE CODE:
\`\`\`
${code.slice(0, 30000)}
\`\`\`

Respond with ONLY a JSON object following the format specified.`;

  try {
    const provider = llmConfig.provider.toUpperCase();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    let response: any;

    if (provider === 'ANTHROPIC') {
      headers['x-api-key'] = llmConfig.apiKey;
      headers['anthropic-version'] = '2023-06-01';
      response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model: llmConfig.model,
          max_tokens: 4096,
          system: REVIEW_SYSTEM_PROMPT,
          messages: [{ role: 'user', content: userMessage }],
        }),
      });
    } else if (provider === 'GOOGLE') {
      response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${llmConfig.model}:generateContent?key=${llmConfig.apiKey}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            contents: [
              { role: 'user', parts: [{ text: REVIEW_SYSTEM_PROMPT + '\n\n' + userMessage }] },
            ],
            generationConfig: { maxOutputTokens: 4096 },
          }),
        }
      );
    } else {
      // OpenAI-compatible (OpenAI, Mistral, Local, Custom)
      let baseUrl = llmConfig.baseUrl || '';
      if (!baseUrl) {
        if (provider === 'OPENAI') baseUrl = 'https://api.openai.com';
        else if (provider === 'MISTRAL') baseUrl = 'https://api.mistral.ai';
        else if (provider === 'LOCAL') baseUrl = 'http://localhost:11434';
        else baseUrl = 'https://api.openai.com';
      }
      if (llmConfig.apiKey && llmConfig.apiKey !== 'none') {
        headers['Authorization'] = `Bearer ${llmConfig.apiKey}`;
      }
      response = await fetch(`${baseUrl}/v1/chat/completions`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model: llmConfig.model,
          messages: [
            { role: 'system', content: REVIEW_SYSTEM_PROMPT },
            { role: 'user', content: userMessage },
          ],
          max_tokens: 4096,
          temperature: 0.1,
        }),
      });
    }

    if (!response.ok) {
      const errText = await response.text();
      logger.warn(`LLM review API error ${response.status}: ${errText}`);
      throw new Error(`LLM API ${response.status}`);
    }

    const data: any = await response.json();

    // Extract text from different provider formats
    let text = '';
    if (provider === 'ANTHROPIC') {
      text = data.content?.[0]?.text || '';
    } else if (provider === 'GOOGLE') {
      text = data.candidates?.[0]?.content?.parts?.[0]?.text || '';
    } else {
      text = data.choices?.[0]?.message?.content || '';
    }

    // Parse JSON from response (strip markdown fences if present)
    const jsonMatch = text.replace(/```json\s*/g, '').replace(/```\s*/g, '').trim();
    const parsed = JSON.parse(jsonMatch);

    return {
      verdict: parsed.verdict === 'APPROVED' ? 'APPROVED' : 'REJECTED',
      riskLevel: parsed.risk_level || 'MEDIUM',
      findings: (parsed.findings || []).map((f: any) => ({
        rule: f.rule || 'LLM_FINDING',
        severity: f.severity || 'MEDIUM',
        description: f.description || 'Unknown finding',
        line: f.line || undefined,
        snippet: f.snippet || undefined,
      })),
      summary: parsed.summary || 'Review completed.',
      raw: text,
    };
  } catch (err: any) {
    logger.error(`LLM review failed: ${err.message}`);
    throw err;
  }
}

// ── Resolve LLM Config ───────────────────────────────────────────────

async function resolveLLMConfig(developerId?: string): Promise<{
  provider: string; model: string; apiKey: string; baseUrl?: string | null;
} | null> {
  // 1. Platform-level review LLM (env vars)
  const envProvider = process.env.REVIEW_LLM_PROVIDER;
  const envModel = process.env.REVIEW_LLM_MODEL;
  const envKey = process.env.REVIEW_LLM_API_KEY;
  if (envProvider && envModel && envKey) {
    return {
      provider: envProvider,
      model: envModel,
      apiKey: envKey,
      baseUrl: process.env.REVIEW_LLM_BASE_URL || null,
    };
  }

  // 2. Developer's default LLM config
  if (developerId) {
    try {
      const settings = await prisma.userSettings.findUnique({ where: { userId: developerId } });
      if (settings?.defaultLLMConfigId) {
        const cfg = await prisma.lLMConfig.findUnique({ where: { id: settings.defaultLLMConfigId } });
        if (cfg) {
          return {
            provider: cfg.provider,
            model: cfg.model,
            apiKey: decrypt(cfg.apiKey),
            baseUrl: cfg.baseUrl,
          };
        }
      }
      // Fallback: first LLM config of any user (admin)
      const anyConfig = await prisma.lLMConfig.findFirst({ orderBy: { createdAt: 'asc' } });
      if (anyConfig) {
        return {
          provider: anyConfig.provider,
          model: anyConfig.model,
          apiKey: decrypt(anyConfig.apiKey),
          baseUrl: anyConfig.baseUrl,
        };
      }
    } catch (e) {
      logger.warn('Failed to resolve developer LLM config', e);
    }
  }

  return null;
}

// ── Main Review Function ─────────────────────────────────────────────

export class AgentReviewService {
  /**
   * Review an agent's code for security risks.
   * Combines static analysis + LLM analysis.
   * Returns a full report with verdict.
   */
  async reviewAgent(agentId: string, developerId: string): Promise<ReviewReport> {
    const start = Date.now();
    logger.info(`Starting security review for agent ${agentId}`);

    // 1. Load agent data
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent) throw new Error('Agent not found');

    // 2. Load agent source code
    let sourceCode = '';
    if (agent.bundlePath) {
      try {
        const fs = await import('fs');
        if (fs.existsSync(agent.bundlePath)) {
          // If it's a single file, read directly
          const stat = fs.statSync(agent.bundlePath);
          if (stat.isFile()) {
            sourceCode = fs.readFileSync(agent.bundlePath, 'utf-8');
          }
        }
      } catch (e) {
        logger.warn(`Could not read bundle: ${e}`);
      }
    }

    // If no bundle, construct a pseudo-source from manifest for review
    if (!sourceCode) {
      sourceCode = [
        `# Agent: ${agent.name}`,
        `# Slug: ${agent.slug}`,
        `# Runtime: ${agent.runtime}`,
        `# Entry: ${agent.entryPoint}`,
        `# Capabilities: ${agent.capabilities}`,
        `# Permissions: ${agent.permissions}`,
        `# Description: ${agent.description}`,
        agent.longDescription ? `# Long Description: ${agent.longDescription}` : '',
        agent.configSchema ? `# Config Schema: ${agent.configSchema}` : '',
      ].join('\n');
    }

    const manifest = {
      name: agent.name,
      slug: agent.slug,
      version: agent.version,
      runtime: agent.runtime,
      entryPoint: agent.entryPoint,
      capabilities: JSON.parse(agent.capabilities || '[]'),
      permissions: JSON.parse(agent.permissions || '[]'),
      price: agent.price,
    };

    // 3. Static analysis (always runs — no external dependency)
    const staticFindings = staticAnalysis(sourceCode);
    logger.info(`Static analysis: ${staticFindings.length} finding(s)`);

    // 4. Determine early reject from critical static findings
    const criticalStatic = staticFindings.filter(f => f.severity === 'CRITICAL');
    if (criticalStatic.length >= 3) {
      // 3+ critical static findings → instant reject, skip LLM
      const report: ReviewReport = {
        verdict: 'REJECTED',
        overallRisk: 'CRITICAL',
        findings: staticFindings,
        summary: `Rejected: ${criticalStatic.length} critical security violations detected by static analysis. Issues include: ${criticalStatic.map(f => f.rule).join(', ')}`,
        reviewedAt: new Date().toISOString(),
        reviewDurationMs: Date.now() - start,
      };
      await this.saveReviewResult(agentId, report);
      return report;
    }

    // 5. LLM analysis (if available)
    let llmResult: Awaited<ReturnType<typeof llmReview>> | null = null;
    const llmConfig = await resolveLLMConfig(developerId);

    if (llmConfig) {
      try {
        llmResult = await llmReview(sourceCode, manifest, llmConfig);
        logger.info(`LLM review verdict: ${llmResult.verdict} (${llmResult.riskLevel})`);
      } catch (err) {
        logger.warn('LLM review unavailable, falling back to static-only review');
      }
    } else {
      logger.info('No LLM config available — using static analysis only');
    }

    // 6. Merge findings & determine verdict
    const allFindings = [...staticFindings];
    if (llmResult) {
      for (const f of llmResult.findings) {
        // Deduplicate by rule+line
        const dup = allFindings.find(e => e.rule === f.rule && e.line === f.line);
        if (!dup) allFindings.push(f);
      }
    }

    // Determine overall risk
    let overallRisk: RiskLevel = 'NONE';
    for (const f of allFindings) {
      if (riskOrd(f.severity) > riskOrd(overallRisk)) {
        overallRisk = f.severity;
      }
    }

    // Verdict logic:
    //   CRITICAL findings → REJECTED
    //   HIGH with ≥2 findings → REJECTED
    //   LLM said REJECTED → REJECTED
    //   Otherwise → APPROVED
    let verdict: ReviewVerdict = 'APPROVED';
    const criticals = allFindings.filter(f => f.severity === 'CRITICAL');
    const highs = allFindings.filter(f => f.severity === 'HIGH');

    if (criticals.length > 0) {
      verdict = 'REJECTED';
    } else if (highs.length >= 2) {
      verdict = 'REJECTED';
    } else if (llmResult?.verdict === 'REJECTED' && llmResult.riskLevel !== 'LOW') {
      verdict = 'REJECTED';
    }

    const summary = llmResult?.summary ||
      (verdict === 'APPROVED'
        ? `Agent passed security review with ${allFindings.length} finding(s). No critical risks detected.`
        : `Agent rejected: ${allFindings.length} security finding(s). Critical: ${criticals.length}, High: ${highs.length}. ${allFindings.slice(0, 3).map(f => f.description).join('; ')}`);

    const report: ReviewReport = {
      verdict,
      overallRisk,
      findings: allFindings,
      summary,
      llmAnalysis: llmResult?.raw,
      reviewedAt: new Date().toISOString(),
      reviewDurationMs: Date.now() - start,
    };

    // 7. Save result & update agent status
    await this.saveReviewResult(agentId, report);

    logger.info(`Review complete for ${agent.name}: ${verdict} (${Date.now() - start}ms)`);
    return report;
  }

  /**
   * Save review result and update agent status.
   */
  private async saveReviewResult(agentId: string, report: ReviewReport) {
    const newStatus = report.verdict === 'APPROVED' ? 'PUBLISHED' : 'REJECTED';

    await prisma.agent.update({
      where: { id: agentId },
      data: {
        status: newStatus,
        // Store review report in outputSchema (JSON field) for retrieval
        outputSchema: JSON.stringify({
          _reviewReport: report,
        }),
      },
    });

    // Get agent for notification
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent) return;

    // Create notification for developer
    await prisma.notification.create({
      data: {
        userId: agent.developerId,
        type: report.verdict === 'APPROVED' ? 'AGENT_PUBLISHED' : 'AGENT_REJECTED',
        title: report.verdict === 'APPROVED'
          ? `✅ ${agent.name} published!`
          : `❌ ${agent.name} rejected`,
        message: report.summary,
        data: JSON.stringify({
          agentId,
          verdict: report.verdict,
          overallRisk: report.overallRisk,
          findingCount: report.findings.length,
        }),
      },
    });
  }

  /**
   * Get the review report for an agent.
   */
  async getReviewReport(agentId: string): Promise<ReviewReport | null> {
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent?.outputSchema) return null;

    try {
      const parsed = JSON.parse(agent.outputSchema);
      return parsed._reviewReport || null;
    } catch {
      return null;
    }
  }

  /**
   * Re-review a rejected agent (after developer fixes).
   */
  async reReview(agentId: string, developerId: string): Promise<ReviewReport> {
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent) throw new Error('Agent not found');
    if (agent.developerId !== developerId) throw new Error('Not your agent');
    if (agent.status !== 'REJECTED') throw new Error('Agent is not in rejected state');

    // Set back to pending
    await prisma.agent.update({
      where: { id: agentId },
      data: { status: 'PENDING_REVIEW' },
    });

    return this.reviewAgent(agentId, developerId);
  }
}

// ── Helpers ──────────────────────────────────────────────────────────

function riskOrd(level: RiskLevel): number {
  switch (level) {
    case 'NONE': return 0;
    case 'LOW': return 1;
    case 'MEDIUM': return 2;
    case 'HIGH': return 3;
    case 'CRITICAL': return 4;
    default: return 0;
  }
}

export const agentReviewService = new AgentReviewService();
