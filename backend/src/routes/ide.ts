/**
 * IDE Routes — Developer IDE API endpoints for AI code generation and assistance.
 */

import { Router, Request, Response } from 'express';
import { authenticate, AuthRequest } from '../middleware/auth';
import { ideService } from '../services/ideService';
import { logger } from '../utils/logger';

const router = Router();

/**
 * POST /api/ide/generate
 * Generate agent code from imitation learning recording.
 */
router.post('/generate', authenticate, async (req: AuthRequest, res: Response) => {
  try {
    const { prompt, sessionName } = req.body;
    if (!prompt) {
      return res.status(400).json({
        success: false,
        error: { code: 'BAD_REQUEST', message: 'prompt is required' },
      });
    }

    const result = await ideService.generateFromRecording(req.userId!, {
      prompt,
      sessionName: sessionName || 'Recording',
    });

    if (!result) {
      return res.status(503).json({
        success: false,
        error: { code: 'LLM_UNAVAILABLE', message: 'AI generation unavailable. Using local fallback.' },
      });
    }

    res.json({ success: true, data: result });
  } catch (err: any) {
    logger.error(`IDE generate error: ${err.message}`);
    res.status(500).json({
      success: false,
      error: { code: 'INTERNAL_ERROR', message: 'Failed to generate code' },
    });
  }
});

/**
 * POST /api/ide/ai-assist
 * AI-powered code assistance for the IDE.
 */
router.post('/ai-assist', authenticate, async (req: AuthRequest, res: Response) => {
  try {
    const { message, currentCode, fileName } = req.body;
    if (!message) {
      return res.status(400).json({
        success: false,
        error: { code: 'BAD_REQUEST', message: 'message is required' },
      });
    }

    const result = await ideService.aiAssist(req.userId!, {
      message,
      currentCode: currentCode || '',
      fileName: fileName || 'agent.ts',
    });

    res.json({ success: true, data: result });
  } catch (err: any) {
    logger.error(`IDE ai-assist error: ${err.message}`);
    res.status(500).json({
      success: false,
      error: { code: 'INTERNAL_ERROR', message: 'AI assist failed' },
    });
  }
});

/**
 * GET /api/ide/sdk-docs
 * Get SDK documentation data.
 */
router.get('/sdk-docs', (_req: Request, res: Response) => {
  // Return SDK documentation structure
  res.json({
    success: true,
    data: {
      version: '1.0.0',
      sections: ['overview', 'context', 'manifest', 'patterns', 'imitation'],
      contextMethods: [
        { name: 'click', signature: 'click(x: number, y: number, button?: "left" | "right"): void', description: 'Click at screen coordinates' },
        { name: 'doubleClick', signature: 'doubleClick(x: number, y: number): void', description: 'Double-click at screen coordinates' },
        { name: 'typeText', signature: 'typeText(text: string): void', description: 'Type text naturally with keyboard' },
        { name: 'pressKey', signature: 'pressKey(key: string): void', description: 'Press a single key' },
        { name: 'hotkey', signature: 'hotkey(...keys: string[]): void', description: 'Key combination' },
        { name: 'moveMouse', signature: 'moveMouse(x: number, y: number): void', description: 'Move cursor' },
        { name: 'scroll', signature: 'scroll(clicks: number): void', description: 'Scroll wheel' },
        { name: 'drag', signature: 'drag(sx: number, sy: number, ex: number, ey: number): void', description: 'Drag from start to end' },
        { name: 'openApp', signature: 'openApp(name: string): void', description: 'Open application' },
        { name: 'runCommand', signature: 'runCommand(cmd: string): Promise<string>', description: 'Execute shell command' },
        { name: 'sendScreenshot', signature: 'sendScreenshot(): Promise<void>', description: 'Capture screen' },
        { name: 'getMousePosition', signature: 'getMousePosition(): {x, y}', description: 'Get cursor position' },
        { name: 'getScreenSize', signature: 'getScreenSize(): {width, height}', description: 'Get screen dimensions' },
        { name: 'askLLM', signature: 'askLLM(messages: LLMMessage[], opts?): Promise<string>', description: 'Ask AI model' },
        { name: 'log', signature: 'log(message: string, level?: string): Promise<void>', description: 'Log message' },
        { name: 'clipboardCopy', signature: 'clipboardCopy(text: string): void', description: 'Copy to clipboard' },
        { name: 'clipboardPaste', signature: 'clipboardPaste(): void', description: 'Paste from clipboard' },
        { name: 'clipboardGet', signature: 'clipboardGet(): Promise<string>', description: 'Read clipboard' },
      ],
      categories: [
        'AUTOMATION', 'PRODUCTIVITY', 'DEVELOPMENT', 'DESIGN', 'DATA_ANALYSIS',
        'COMMUNICATION', 'FINANCE', 'EDUCATION', 'ENTERTAINMENT', 'SECURITY',
        'SYSTEM_ADMIN', 'OTHER',
      ],
      capabilities: [
        'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'SCREENSHOT_ANALYSIS',
        'CLIPBOARD_ACCESS', 'FILE_SYSTEM_ACCESS', 'APP_LAUNCHING', 'BROWSER_CONTROL',
        'NETWORK_ACCESS', 'SYSTEM_CONTROL', 'LLM_REASONING',
      ],
    },
  });
});

/**
 * POST /api/ide/validate
 * Validate agent code structure.
 */
router.post('/validate', authenticate, async (req: AuthRequest, res: Response) => {
  try {
    const { code } = req.body;
    if (!code) {
      return res.status(400).json({
        success: false,
        error: { code: 'BAD_REQUEST', message: 'code is required' },
      });
    }

    const issues: { type: 'error' | 'warning'; message: string; line?: number }[] = [];

    // Check for defineAgent or AgentPlugin
    if (!code.includes('defineAgent') && !code.includes('AgentPlugin')) {
      issues.push({ type: 'error', message: 'Must use defineAgent() or extend AgentPlugin' });
    }

    // Check for required fields
    if (code.includes('defineAgent')) {
      if (!code.includes("name:") && !code.includes("name :")) {
        issues.push({ type: 'error', message: 'Missing required field: name' });
      }
      if (!code.includes("slug:") && !code.includes("slug :")) {
        issues.push({ type: 'error', message: 'Missing required field: slug' });
      }
      if (!code.includes("description:") && !code.includes("description :")) {
        issues.push({ type: 'error', message: 'Missing required field: description' });
      }
      if (!code.includes("category:") && !code.includes("category :")) {
        issues.push({ type: 'error', message: 'Missing required field: category' });
      }
      if (!code.includes("run") && !code.includes("execute")) {
        issues.push({ type: 'error', message: 'Missing required method: run()' });
      }
    }

    // Security warnings
    const dangerousPatterns = [
      { pattern: /process\.env/g, msg: 'Accessing process.env — ensure no secrets are hardcoded' },
      { pattern: /require\s*\(/g, msg: 'Using require() — prefer SDK imports' },
      { pattern: /eval\s*\(/g, msg: 'Using eval() — this is a security risk' },
      { pattern: /child_process/g, msg: 'Accessing child_process — must declare SYSTEM_CONTROL capability' },
      { pattern: /fs\s*\.\s*(readFile|writeFile|unlink|rmdir)/g, msg: 'File system access — must declare FILE_SYSTEM_ACCESS capability' },
    ];

    for (const { pattern, msg } of dangerousPatterns) {
      if (pattern.test(code)) {
        issues.push({ type: 'warning', message: msg });
      }
    }

    res.json({
      success: true,
      data: {
        valid: issues.filter((i) => i.type === 'error').length === 0,
        issues,
      },
    });
  } catch (err: any) {
    logger.error(`IDE validate error: ${err.message}`);
    res.status(500).json({
      success: false,
      error: { code: 'INTERNAL_ERROR', message: 'Validation failed' },
    });
  }
});

export default router;
