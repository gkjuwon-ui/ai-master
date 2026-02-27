import { create } from 'zustand';

// ── Types ───────────────────────────────────────────

export interface IDEFile {
  id: string;
  name: string;
  path: string;
  content: string;
  language: string;
  isDirty: boolean;
}

export interface SandboxLog {
  id: string;
  type: 'info' | 'warn' | 'error' | 'system' | 'agent' | 'user';
  message: string;
  timestamp: number;
}

export interface RecordedAction {
  id: string;
  type: 'click' | 'type' | 'key' | 'scroll' | 'drag' | 'navigate' | 'open_app' | 'terminal_command' | 'custom';
  description: string;
  params: Record<string, any>;
  screenshot?: string; // base64 snapshot
  timestamp: number;
}

export interface ImitationSession {
  id: string;
  name: string;
  actions: RecordedAction[];
  recording: boolean;
  generatedCode?: string;
  generatedPrompt?: string;
  startedAt: number;
  endedAt?: number;
}

export type PanelLayout = 'editor-sandbox' | 'editor-only' | 'sandbox-only';
export type BottomPanel = 'terminal' | 'output' | 'problems';
export type RightPanel = 'docs' | 'ai-assist' | 'none';

// ── SDK Documentation Data ─────────────────────────

export const SDK_DOCS = {
  overview: {
    title: 'OGENTI SDK Overview',
    content: `# OGENTI Agent SDK

Build OS-controlling AI agents with a simple, powerful API.

## Quick Start

\`\`\`typescript
import { defineAgent } from '@ogenti/sdk';

export default defineAgent({
  name: 'My Agent',
  slug: 'my-agent',
  description: 'Automates tasks on your PC',
  category: 'AUTOMATION',
  async run(ctx, prompt) {
    await ctx.log('Starting task...');
    const screenshot = await ctx.sendScreenshot();
    const plan = await ctx.askLLM([
      { role: 'system', content: 'You are a helpful assistant.' },
      { role: 'user', content: prompt }
    ]);
    ctx.typeText(plan);
  }
});
\`\`\`

## Architecture
- **Plugin**: Your agent code (TypeScript or Python)
- **Context**: OS control API injected at runtime
- **Sandbox**: Safe execution environment
- **LLM**: AI reasoning via your configured model
`,
  },
  context: {
    title: 'Agent Context API',
    content: `# AgentContext API Reference

The \`ctx\` object provides full OS control and AI capabilities.

## Mouse Control

| Method | Description |
|---|---|
| \`ctx.click(x, y, button?)\` | Click at coordinates (left/right) |
| \`ctx.doubleClick(x, y)\` | Double-click |
| \`ctx.moveMouse(x, y)\` | Move cursor |
| \`ctx.drag(sx, sy, ex, ey)\` | Drag from start to end |
| \`ctx.scroll(clicks)\` | Scroll (positive=down, negative=up) |

## Keyboard

| Method | Description |
|---|---|
| \`ctx.typeText(text)\` | Type text naturally |
| \`ctx.pressKey(key)\` | Press single key (Enter, Tab, etc.) |
| \`ctx.hotkey(...keys)\` | Key combo (e.g., 'ctrl', 'c') |

## Screen & Apps

| Method | Description |
|---|---|
| \`ctx.sendScreenshot()\` | Capture current screen |
| \`ctx.getMousePosition()\` | Get cursor \`{x, y}\` |
| \`ctx.getScreenSize()\` | Get screen \`{width, height}\` |
| \`ctx.openApp(name)\` | Open application by name |
| \`ctx.runCommand(cmd)\` | Execute shell command |

## Clipboard

| Method | Description |
|---|---|
| \`ctx.clipboardCopy(text)\` | Copy text to clipboard |
| \`ctx.clipboardPaste()\` | Paste from clipboard |
| \`ctx.clipboardGet()\` | Read clipboard content |

## AI / LLM

| Method | Description |
|---|---|
| \`ctx.askLLM(messages, opts?)\` | Ask AI model with message array |
| \`ctx.log(msg, level?)\` | Log message (INFO/WARN/ERROR/DEBUG) |

### askLLM Example
\`\`\`typescript
const result = await ctx.askLLM([
  { role: 'system', content: 'You analyze screenshots.' },
  { role: 'user', content: 'What do you see?' }
], { screenshot: true });
\`\`\`
`,
  },
  manifest: {
    title: 'Agent Manifest',
    content: `# Agent Manifest Configuration

Define your agent's metadata, pricing, and capabilities.

## Using defineAgent (Recommended)

\`\`\`typescript
import { defineAgent } from '@ogenti/sdk';

export default defineAgent({
  name: 'Excel Master',
  slug: 'excel-master',
  description: 'Automates Excel tasks',
  category: 'PRODUCTIVITY',
  version: '1.0.0',
  capabilities: [
    'MOUSE_CONTROL',
    'KEYBOARD_INPUT',
    'SCREEN_CAPTURE',
    'SCREENSHOT_ANALYSIS',
    'CLIPBOARD_ACCESS',
    'APP_LAUNCHING'
  ],
  async run(ctx, prompt) {
    // Agent logic here
  }
});
\`\`\`

## Categories
\`AUTOMATION\` | \`PRODUCTIVITY\` | \`DEVELOPMENT\` | \`DESIGN\` | \`DATA_ANALYSIS\` |
\`COMMUNICATION\` | \`FINANCE\` | \`EDUCATION\` | \`ENTERTAINMENT\` | \`SECURITY\` |
\`SYSTEM_ADMIN\` | \`OTHER\`

## Capabilities
\`MOUSE_CONTROL\` | \`KEYBOARD_INPUT\` | \`SCREEN_CAPTURE\` | \`SCREENSHOT_ANALYSIS\` |
\`CLIPBOARD_ACCESS\` | \`FILE_SYSTEM_ACCESS\` | \`APP_LAUNCHING\` | \`BROWSER_CONTROL\` |
\`NETWORK_ACCESS\` | \`SYSTEM_CONTROL\` | \`LLM_REASONING\`

## Pricing Models
\`FREE\` | \`ONE_TIME\` | \`SUBSCRIPTION_MONTHLY\` | \`SUBSCRIPTION_YEARLY\` | \`PAY_PER_USE\`
`,
  },
  patterns: {
    title: 'Common Patterns',
    content: `# Common Agent Patterns

## Pattern 1: Screenshot → Analyze → Act

\`\`\`typescript
async run(ctx, prompt) {
  await ctx.sendScreenshot();
  const analysis = await ctx.askLLM([
    { role: 'system', content: 'Analyze the screenshot and determine the next action.' },
    { role: 'user', content: prompt }
  ], { screenshot: true });

  // Parse and execute
  if (analysis.includes('click')) {
    const match = analysis.match(/click\\((\\d+),\\s*(\\d+)\\)/);
    if (match) ctx.click(parseInt(match[1]), parseInt(match[2]));
  }
}
\`\`\`

## Pattern 2: Multi-Step Task Loop

\`\`\`typescript
async run(ctx, prompt) {
  const maxSteps = 10;
  for (let i = 0; i < maxSteps; i++) {
    await ctx.sendScreenshot();
    const step = await ctx.askLLM([
      { role: 'system', content: \`Step \${i+1}/\${maxSteps}. Task: \${prompt}\` },
      { role: 'user', content: 'What should I do next? Reply DONE if complete.' }
    ], { screenshot: true });

    if (step.includes('DONE')) break;
    // Execute the step...
    await new Promise(r => setTimeout(r, 1000));
  }
}
\`\`\`

## Pattern 3: Form Filling

\`\`\`typescript
async run(ctx, prompt) {
  const data = JSON.parse(prompt);
  for (const [field, value] of Object.entries(data)) {
    // Click the field
    await ctx.sendScreenshot();
    const pos = await ctx.askLLM([
      { role: 'user', content: \`Find the "\${field}" input field. Reply with x,y coordinates.\` }
    ], { screenshot: true });
    const [x, y] = pos.split(',').map(Number);
    ctx.click(x, y);
    await new Promise(r => setTimeout(r, 300));
    ctx.hotkey('ctrl', 'a');
    ctx.typeText(String(value));
    ctx.pressKey('Tab');
  }
}
\`\`\`

## Pattern 4: App Automation

\`\`\`typescript
async run(ctx, prompt) {
  ctx.openApp('notepad');
  await new Promise(r => setTimeout(r, 2000));
  ctx.typeText('Hello from OGENTI!');
  ctx.hotkey('ctrl', 's');
}
\`\`\`
`,
  },
  imitation: {
    title: 'Imitation Learning',
    content: `# Imitation Learning Guide

Record your actions in the sandbox and let AI generate agent code automatically.

## How It Works

1. **Start Recording** — Click the record button
2. **Perform Your Task** — Do the task manually in the sandbox
3. **Name the Action** — Give it a descriptive name (e.g., "Save Excel file")
4. **Stop Recording** — Click stop
5. **Generate Code** — AI analyzes your actions and writes the plugin code + prompt

## Tips for Better Results

- **Be deliberate** — Perform actions clearly, avoid random clicks
- **One task per recording** — Keep recordings focused
- **Name actions well** — "Format cells as currency" beats "do the thing"
- **Do it multiple times** — Record variations for robust code generation

## What Gets Generated

- **Plugin Code**: Full \`defineAgent()\` with your recorded workflow
- **Agent Prompt**: System prompt describing when/how to use each action
- **Prompt Cache**: Frequently used prompts are cached for faster execution

## Example

Record yourself opening Excel → selecting cells → applying formatting → saving.

Generated code:
\`\`\`typescript
export default defineAgent({
  name: 'Excel Formatter',
  slug: 'excel-formatter',
  async run(ctx, prompt) {
    ctx.openApp('excel');
    await new Promise(r => setTimeout(r, 2000));
    // Select cells A1:D10
    ctx.click(100, 150);
    ctx.hotkey('ctrl', 'shift', 'End');
    // Apply currency format
    ctx.hotkey('ctrl', '1');
    // ... generated from your recording
  }
});
\`\`\`
`,
  },
};

// ── Default Template ────────────────────────────────

export const DEFAULT_AGENT_CODE = `import { defineAgent } from '@ogenti/sdk';

export default defineAgent({
  name: 'My Agent',
  slug: 'my-agent',
  description: 'Describe what your agent does',
  category: 'AUTOMATION',

  async run(ctx, prompt) {
    await ctx.log('Starting task: ' + prompt);

    // Take a screenshot to see the current state
    await ctx.sendScreenshot();

    // Ask the LLM what to do
    const plan = await ctx.askLLM([
      { role: 'system', content: 'You are a helpful OS automation agent.' },
      { role: 'user', content: prompt }
    ], { screenshot: true });

    await ctx.log('Plan: ' + plan);

    // Execute your automation logic here
    // ctx.click(x, y)       — Click at position
    // ctx.typeText('hello')  — Type text
    // ctx.pressKey('Enter')  — Press a key
    // ctx.hotkey('ctrl','c') — Key combination
    // ctx.openApp('notepad') — Open application
  }
});
`;

// ── Store ────────────────────────────────────────────

interface IDEState {
  // Files
  files: IDEFile[];
  activeFileId: string | null;

  // Layout
  layout: PanelLayout;
  bottomPanel: BottomPanel;
  rightPanel: RightPanel;
  bottomPanelOpen: boolean;
  rightPanelOpen: boolean;

  // Sandbox
  sandboxRunning: boolean;
  sandboxUrl: string | null;
  sandboxCursorInside: boolean;
  sandboxAvailable: boolean | null;
  sandboxLaunching: boolean;

  // Terminal / Output
  terminalLogs: SandboxLog[];
  commandHistory: string[];

  // Imitation Learning
  imitationSessions: ImitationSession[];
  activeImitationId: string | null;
  isRecording: boolean;

  // AI Assist
  aiGenerating: boolean;
  aiSuggestion: string | null;

  // Docs
  activeDocSection: keyof typeof SDK_DOCS;

  // Actions
  createFile: (name: string, content?: string) => void;
  updateFileContent: (fileId: string, content: string) => void;
  setActiveFile: (fileId: string) => void;
  closeFile: (fileId: string) => void;

  setLayout: (layout: PanelLayout) => void;
  toggleBottomPanel: () => void;
  toggleRightPanel: () => void;
  setBottomPanel: (panel: BottomPanel) => void;
  setRightPanel: (panel: RightPanel) => void;

  setSandboxRunning: (running: boolean) => void;
  setSandboxUrl: (url: string | null) => void;
  setSandboxCursorInside: (inside: boolean) => void;
  setSandboxAvailable: (available: boolean | null) => void;
  setSandboxLaunching: (launching: boolean) => void;

  addTerminalLog: (log: Omit<SandboxLog, 'id' | 'timestamp'>) => void;
  clearTerminalLogs: () => void;
  addCommandHistory: (cmd: string) => void;

  startRecording: (name: string) => void;
  stopRecording: () => void;
  addRecordedAction: (action: Omit<RecordedAction, 'id' | 'timestamp'>) => void;
  setGeneratedCode: (sessionId: string, code: string, prompt: string) => void;

  setAiGenerating: (generating: boolean) => void;
  setAiSuggestion: (suggestion: string | null) => void;
  setActiveDocSection: (section: keyof typeof SDK_DOCS) => void;
}

export const useIDEStore = create<IDEState>((set, get) => ({
  // Initial state
  files: [
    {
      id: 'main',
      name: 'agent.ts',
      path: '/agent.ts',
      content: DEFAULT_AGENT_CODE,
      language: 'typescript',
      isDirty: false,
    },
  ],
  activeFileId: 'main',

  layout: 'editor-sandbox',
  bottomPanel: 'terminal',
  rightPanel: 'none',
  bottomPanelOpen: true,
  rightPanelOpen: false,

  sandboxRunning: false,
  sandboxUrl: null,
  sandboxCursorInside: false,
  sandboxAvailable: null,
  sandboxLaunching: false,

  terminalLogs: [],
  commandHistory: [],

  imitationSessions: [],
  activeImitationId: null,
  isRecording: false,

  aiGenerating: false,
  aiSuggestion: null,

  activeDocSection: 'overview',

  // File actions
  createFile: (name, content = '') => {
    const ext = name.split('.').pop() || 'ts';
    const langMap: Record<string, string> = {
      ts: 'typescript', tsx: 'typescriptreact', js: 'javascript',
      jsx: 'javascriptreact', py: 'python', json: 'json', md: 'markdown',
    };
    const file: IDEFile = {
      id: `file_${Date.now()}`,
      name,
      path: `/${name}`,
      content,
      language: langMap[ext] || 'plaintext',
      isDirty: false,
    };
    set((s) => ({ files: [...s.files, file], activeFileId: file.id }));
  },

  updateFileContent: (fileId, content) => {
    set((s) => ({
      files: s.files.map((f) =>
        f.id === fileId ? { ...f, content, isDirty: true } : f
      ),
    }));
  },

  setActiveFile: (fileId) => set({ activeFileId: fileId }),

  closeFile: (fileId) => {
    const state = get();
    const remaining = state.files.filter((f) => f.id !== fileId);
    const newActive = state.activeFileId === fileId
      ? remaining[remaining.length - 1]?.id || null
      : state.activeFileId;
    set({ files: remaining, activeFileId: newActive });
  },

  // Layout actions
  setLayout: (layout) => set({ layout }),
  toggleBottomPanel: () => set((s) => ({ bottomPanelOpen: !s.bottomPanelOpen })),
  toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
  setBottomPanel: (panel) => set({ bottomPanel: panel, bottomPanelOpen: true }),
  setRightPanel: (panel) => set({ rightPanel: panel, rightPanelOpen: panel !== 'none' }),

  // Sandbox actions
  setSandboxRunning: (running) => set({ sandboxRunning: running }),
  setSandboxUrl: (url) => set({ sandboxUrl: url }),
  setSandboxCursorInside: (inside) => set({ sandboxCursorInside: inside }),
  setSandboxAvailable: (available) => set({ sandboxAvailable: available }),
  setSandboxLaunching: (launching) => set({ sandboxLaunching: launching }),

  // Terminal actions
  addTerminalLog: (log) => {
    const entry: SandboxLog = {
      ...log,
      id: `log_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      timestamp: Date.now(),
    };
    set((s) => ({ terminalLogs: [...s.terminalLogs.slice(-500), entry] }));
  },
  clearTerminalLogs: () => set({ terminalLogs: [] }),
  addCommandHistory: (cmd) => {
    set((s) => ({ commandHistory: [...s.commandHistory.slice(-100), cmd] }));
  },

  // Imitation Learning actions
  startRecording: (name) => {
    const session: ImitationSession = {
      id: `imit_${Date.now()}`,
      name,
      actions: [],
      recording: true,
      startedAt: Date.now(),
    };
    set((s) => ({
      imitationSessions: [...s.imitationSessions, session],
      activeImitationId: session.id,
      isRecording: true,
    }));
  },

  stopRecording: () => {
    const { activeImitationId } = get();
    if (!activeImitationId) return;
    set((s) => ({
      isRecording: false,
      imitationSessions: s.imitationSessions.map((sess) =>
        sess.id === activeImitationId
          ? { ...sess, recording: false, endedAt: Date.now() }
          : sess
      ),
    }));
  },

  addRecordedAction: (action) => {
    const { activeImitationId, isRecording } = get();
    if (!isRecording || !activeImitationId) return;
    const entry: RecordedAction = {
      ...action,
      id: `act_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      timestamp: Date.now(),
    };
    set((s) => ({
      imitationSessions: s.imitationSessions.map((sess) =>
        sess.id === activeImitationId
          ? { ...sess, actions: [...sess.actions, entry] }
          : sess
      ),
    }));
  },

  setGeneratedCode: (sessionId, code, prompt) => {
    set((s) => ({
      imitationSessions: s.imitationSessions.map((sess) =>
        sess.id === sessionId
          ? { ...sess, generatedCode: code, generatedPrompt: prompt }
          : sess
      ),
    }));
  },

  setAiGenerating: (generating) => set({ aiGenerating: generating }),
  setAiSuggestion: (suggestion) => set({ aiSuggestion: suggestion }),
  setActiveDocSection: (section) => set({ activeDocSection: section }),
}));
