/**
 * IDE Service — Handles AI-powered code generation and imitation learning.
 */

import prisma from '../models';
import { logger } from '../utils/logger';
import crypto from 'crypto';

interface GenerateRequest {
  prompt: string;
  sessionName: string;
}

interface AIAssistRequest {
  message: string;
  currentCode: string;
  fileName: string;
}

/**
 * Get the owner's LLM config for AI generation.
 */
async function getOwnerLLMConfig(userId: string) {
  // Try the default config first
  const settings = await prisma.userSettings.findUnique({
    where: { userId },
  });

  if (settings?.defaultLLMConfigId) {
    const config = await prisma.lLMConfig.findUnique({
      where: { id: settings.defaultLLMConfigId },
    });
    if (config) return config;
  }

  // Fallback: any config for this user
  const anyConfig = await prisma.lLMConfig.findFirst({
    where: { userId },
    orderBy: { createdAt: 'desc' },
  });
  return anyConfig;
}

/**
 * Decrypt an API key (same logic as llmService).
 */
function decryptKey(encrypted: string): string {
  try {
    const ENCRYPTION_KEY = process.env.ENCRYPTION_KEY || 'ogenti-default-encryption-key-change-this!!';
    const key = crypto.scryptSync(ENCRYPTION_KEY, 'ogenti-salt', 32);
    const [ivHex, encryptedHex] = encrypted.split(':');
    if (!ivHex || !encryptedHex) return encrypted;
    const iv = Buffer.from(ivHex, 'hex');
    const decipher = crypto.createDecipheriv('aes-256-cbc', key, iv);
    let decrypted = decipher.update(encryptedHex, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    return decrypted;
  } catch (err) {
    return 'none';
  }
}

/**
 * Call the user's configured LLM to generate a response.
 */
async function callLLM(
  userId: string,
  systemPrompt: string,
  userMessage: string
): Promise<string | null> {
  try {
    const config = await getOwnerLLMConfig(userId);
    if (!config) return null;

    const apiKey = decryptKey(config.apiKey);
    if (!apiKey || apiKey === 'none') return null;

    const provider = config.provider.toUpperCase();
    let baseUrl = config.baseUrl || '';
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };

    let response: any;

    if (provider === 'ANTHROPIC') {
      headers['x-api-key'] = apiKey;
      headers['anthropic-version'] = '2023-06-01';
      response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model: config.model,
          max_tokens: 4000,
          system: systemPrompt,
          messages: [{ role: 'user', content: userMessage }],
        }),
      });
      if (!response.ok) return null;
      const data = await response.json();
      return data.content?.[0]?.text || null;
    }

    // OpenAI-compatible (default)
    if (!baseUrl) {
      if (provider === 'OPENAI') baseUrl = 'https://api.openai.com';
      else if (provider === 'MISTRAL') baseUrl = 'https://api.mistral.ai';
      else baseUrl = 'https://api.openai.com';
    }
    headers['Authorization'] = `Bearer ${apiKey}`;

    response = await fetch(`${baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        model: config.model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userMessage },
        ],
        max_tokens: 4000,
        temperature: 0.7,
      }),
    });

    if (!response.ok) return null;
    const data = await response.json();
    return data.choices?.[0]?.message?.content || null;
  } catch (err: any) {
    logger.warn(`IDE LLM call failed: ${err.message}`);
    return null;
  }
}

export class IDEService {
  /**
   * Generate agent code from imitation learning recording.
   */
  async generateFromRecording(userId: string, req: GenerateRequest) {
    const systemPrompt = `You are an expert OGENTI SDK developer. You generate agent plugin code from recorded user actions.

OGENTI SDK uses defineAgent() to create agents. The AgentContext (ctx) provides:
- ctx.click(x, y) — click at screen position
- ctx.doubleClick(x, y) — double click
- ctx.typeText(text) — type text
- ctx.pressKey(key) — press key (Enter, Tab, etc.)
- ctx.hotkey(...keys) — key combo (e.g., 'ctrl', 'c')
- ctx.moveMouse(x, y) — move cursor
- ctx.scroll(clicks) — scroll
- ctx.drag(sx, sy, ex, ey) — drag
- ctx.openApp(name) — open application
- ctx.runCommand(cmd) — shell command
- ctx.sendScreenshot() — capture screen
- ctx.askLLM(messages, {screenshot: true}) — ask AI
- ctx.log(msg, level) — log message
- ctx.clipboardCopy/Paste/Get — clipboard operations

Always include await for async operations and add delays between actions.
Return ONLY the format requested — no extra text.`;

    const aiResponse = await callLLM(userId, systemPrompt, req.prompt);

    if (!aiResponse) {
      return null; // Frontend will use fallback
    }

    // Parse code and prompt from response
    const codeMatch = aiResponse.match(/===CODE===([\s\S]*?)===END_CODE===/);
    const promptMatch = aiResponse.match(/===PROMPT===([\s\S]*?)===END_PROMPT===/);

    return {
      code: codeMatch ? codeMatch[1].trim() : aiResponse,
      prompt: promptMatch ? promptMatch[1].trim() : 'Generated agent prompt.',
    };
  }

  /**
   * AI-powered code assistance for the IDE.
   */
  async aiAssist(userId: string, req: AIAssistRequest) {
    const systemPrompt = `You are an expert OGENTI SDK assistant helping developers build agent plugins.

The developer is working in the OGENTI IDE. Their current file is "${req.fileName}".

OGENTI SDK key concepts:
- defineAgent({name, slug, description, category, run(ctx, prompt)}) — define an agent
- AgentContext (ctx) provides: click, typeText, pressKey, hotkey, moveMouse, scroll, drag, openApp, runCommand, sendScreenshot, askLLM, log, clipboard operations
- Categories: AUTOMATION, PRODUCTIVITY, DEVELOPMENT, DESIGN, DATA_ANALYSIS, COMMUNICATION, FINANCE, EDUCATION, ENTERTAINMENT, SECURITY, SYSTEM_ADMIN, OTHER
- Capabilities: MOUSE_CONTROL, KEYBOARD_INPUT, SCREEN_CAPTURE, SCREENSHOT_ANALYSIS, CLIPBOARD_ACCESS, FILE_SYSTEM_ACCESS, APP_LAUNCHING, BROWSER_CONTROL, NETWORK_ACCESS, SYSTEM_CONTROL, LLM_REASONING

Be concise and helpful. Include code examples when relevant. Use markdown formatting.`;

    const userMessage = `My current code:
\`\`\`typescript
${req.currentCode.slice(0, 3000)}
\`\`\`

Question: ${req.message}`;

    const aiResponse = await callLLM(userId, systemPrompt, userMessage);

    return {
      response: aiResponse || `Here are some tips for OGENTI agent development:

1. **Start with sendScreenshot()** — always check what's on screen first
2. **Use askLLM with screenshots** — let AI analyze the visual state
3. **Add delays** — use \`await new Promise(r => setTimeout(r, 500))\` between actions
4. **Log progress** — \`await ctx.log('step completed')\` for debugging
5. **Handle errors** — wrap risky operations in try/catch

Check the Docs panel for the complete API reference.`,
    };
  }
}

export const ideService = new IDEService();
