'use client';

import { useRef, useCallback, useEffect } from 'react';
import Editor, { OnMount, OnChange } from '@monaco-editor/react';
import { Code2 } from 'lucide-react';
import { useIDEStore } from '@/store/ideStore';

// SDK type definitions for auto-complete
const SDK_TYPE_DEFS = `
declare module '@ogenti/sdk' {
  export type AgentCategory =
    | 'AUTOMATION' | 'PRODUCTIVITY' | 'DEVELOPMENT' | 'DESIGN'
    | 'DATA_ANALYSIS' | 'COMMUNICATION' | 'FINANCE' | 'EDUCATION'
    | 'ENTERTAINMENT' | 'SECURITY' | 'SYSTEM_ADMIN' | 'OTHER';

  export type AgentCapability =
    | 'MOUSE_CONTROL' | 'KEYBOARD_INPUT' | 'SCREEN_CAPTURE'
    | 'SCREENSHOT_ANALYSIS' | 'CLIPBOARD_ACCESS' | 'FILE_SYSTEM_ACCESS'
    | 'APP_LAUNCHING' | 'BROWSER_CONTROL' | 'NETWORK_ACCESS'
    | 'SYSTEM_CONTROL' | 'LLM_REASONING';

  export interface LLMMessage {
    role: 'system' | 'user' | 'assistant';
    content: string;
  }

  export interface AgentContext {
    /** Log a message with optional level */
    log(message: string, level?: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG'): Promise<void>;

    /** Ask the LLM model with messages. Set screenshot: true to include current screen. */
    askLLM(messages: LLMMessage[], options?: { screenshot?: boolean }): Promise<string>;

    /** Click at screen coordinates */
    click(x: number, y: number, button?: 'left' | 'right'): void;
    /** Double-click at screen coordinates */
    doubleClick(x: number, y: number): void;
    /** Type text naturally with keyboard */
    typeText(text: string): void;
    /** Press a single key (Enter, Tab, Escape, etc.) */
    pressKey(key: string): void;
    /** Press key combination (e.g., hotkey('ctrl', 'c')) */
    hotkey(...keys: string[]): void;
    /** Move mouse cursor to coordinates */
    moveMouse(x: number, y: number): void;
    /** Scroll wheel (positive = down, negative = up) */
    scroll(clicks: number): void;
    /** Drag from start position to end position */
    drag(startX: number, startY: number, endX: number, endY: number): void;

    /** Open an application by name */
    openApp(name: string): void;
    /** Execute a shell command and return output */
    runCommand(command: string): Promise<string>;

    /** Capture and send a screenshot */
    sendScreenshot(): Promise<void>;
    /** Get current mouse position */
    getMousePosition(): { x: number; y: number };
    /** Get screen dimensions */
    getScreenSize(): { width: number; height: number };

    /** Copy text to clipboard */
    clipboardCopy(text: string): void;
    /** Paste from clipboard */
    clipboardPaste(): void;
    /** Read clipboard content */
    clipboardGet(): Promise<string>;
  }

  export interface AgentDef {
    /** Display name of the agent */
    name: string;
    /** URL-safe slug (lowercase, hyphens only) */
    slug: string;
    /** Description of what this agent does */
    description: string;
    /** Marketplace category */
    category: AgentCategory;
    /** Version string (default: '1.0.0') */
    version?: string;
    /** OS capabilities used */
    capabilities?: AgentCapability[];
    /** The agent's main logic */
    run: (ctx: AgentContext, prompt: string, config: Record<string, any>) => Promise<void>;
  }

  /** Define an agent plugin with a single function call */
  export function defineAgent(def: AgentDef): any;

  export abstract class AgentPlugin {
    abstract readonly name: string;
    abstract readonly description: string;
    abstract readonly version: string;
    abstract readonly capabilities: AgentCapability[];
    abstract execute(ctx: AgentContext, prompt: string, config: Record<string, any>): Promise<void>;
  }

  export class AgentManifest {
    name(name: string): this;
    slug(slug: string): this;
    version(version: string): this;
    description(desc: string): this;
    shortDescription(desc: string): this;
    category(cat: AgentCategory): this;
    capabilities(...caps: AgentCapability[]): this;
    free(): this;
    price(amount: number, model?: 'ONE_TIME' | 'SUBSCRIPTION_MONTHLY' | 'SUBSCRIPTION_YEARLY' | 'PAY_PER_USE'): this;
    tags(...tags: string[]): this;
    entrypoint(file: string): this;
    runtime(rt: 'python' | 'node'): this;
    build(): any;
    toJSON(): string;
  }
}
`;

// Custom OGENTI dark theme
const OGENTI_THEME_DATA = {
  base: 'vs-dark' as const,
  inherit: true,
  rules: [
    { token: 'comment', foreground: '6a737d', fontStyle: 'italic' },
    { token: 'keyword', foreground: '0071e3' },
    { token: 'string', foreground: '9ecbff' },
    { token: 'number', foreground: 'f9ae58' },
    { token: 'type', foreground: 'b392f0' },
    { token: 'function', foreground: 'e1e4e8' },
    { token: 'variable', foreground: 'e1e4e8' },
    { token: 'constant', foreground: '79b8ff' },
    { token: 'delimiter', foreground: '8b949e' },
  ],
  colors: {
    'editor.background': '#0a0a0a',
    'editor.foreground': '#e1e4e8',
    'editorLineNumber.foreground': '#444d56',
    'editorLineNumber.activeForeground': '#e86520',
    'editor.selectionBackground': '#e8652030',
    'editor.lineHighlightBackground': '#161b22',
    'editorCursor.foreground': '#e86520',
    'editorIndentGuide.background': '#1b1f23',
    'editorIndentGuide.activeBackground': '#303640',
    'editor.selectionHighlightBackground': '#e8652020',
    'editorBracketMatch.background': '#e8652030',
    'editorBracketMatch.border': '#e86520',
    'editorSuggestWidget.background': '#0d1117',
    'editorSuggestWidget.border': '#30363d',
    'editorSuggestWidget.selectedBackground': '#e8652030',
    'scrollbar.shadow': '#00000000',
    'scrollbarSlider.background': '#484f5833',
    'scrollbarSlider.hoverBackground': '#484f5866',
    'scrollbarSlider.activeBackground': '#e8652050',
  },
};

// Completion items for common SDK patterns
function registerCompletionProviders(monaco: any) {
  monaco.languages.registerCompletionItemProvider('typescript', {
    triggerCharacters: ['.', '('],
    provideCompletionItems: (model: any, position: any) => {
      const word = model.getWordUntilPosition(position);
      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      };

      // Get text before cursor to detect context
      const lineContent = model.getLineContent(position.lineNumber);
      const textBefore = lineContent.substring(0, position.column - 1);

      // ctx. completions
      if (textBefore.endsWith('ctx.')) {
        return {
          suggestions: [
            { label: 'click', kind: monaco.languages.CompletionItemKind.Method, insertText: 'click(${1:x}, ${2:y})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Click at coordinates', documentation: 'Click at (x, y) screen position', range },
            { label: 'doubleClick', kind: monaco.languages.CompletionItemKind.Method, insertText: 'doubleClick(${1:x}, ${2:y})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Double-click at coordinates', range },
            { label: 'typeText', kind: monaco.languages.CompletionItemKind.Method, insertText: "typeText('${1:text}')", insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Type text with keyboard', range },
            { label: 'pressKey', kind: monaco.languages.CompletionItemKind.Method, insertText: "pressKey('${1|Enter,Tab,Escape,Space,Backspace,Delete|}')", insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Press a key', range },
            { label: 'hotkey', kind: monaco.languages.CompletionItemKind.Method, insertText: "hotkey('${1|ctrl,alt,shift|}', '${2:key}')", insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Key combination', range },
            { label: 'moveMouse', kind: monaco.languages.CompletionItemKind.Method, insertText: 'moveMouse(${1:x}, ${2:y})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Move cursor to position', range },
            { label: 'scroll', kind: monaco.languages.CompletionItemKind.Method, insertText: 'scroll(${1:clicks})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Scroll (positive=down)', range },
            { label: 'drag', kind: monaco.languages.CompletionItemKind.Method, insertText: 'drag(${1:startX}, ${2:startY}, ${3:endX}, ${4:endY})', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Drag from ??to', range },
            { label: 'openApp', kind: monaco.languages.CompletionItemKind.Method, insertText: "openApp('${1:appName}')", insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Open application', range },
            { label: 'runCommand', kind: monaco.languages.CompletionItemKind.Method, insertText: "await ctx.runCommand('${1:command}')", insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Execute shell command', range },
            { label: 'sendScreenshot', kind: monaco.languages.CompletionItemKind.Method, insertText: 'await ctx.sendScreenshot()', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Capture & send screenshot', range },
            { label: 'getMousePosition', kind: monaco.languages.CompletionItemKind.Method, insertText: 'ctx.getMousePosition()', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Get cursor {x, y}', range },
            { label: 'getScreenSize', kind: monaco.languages.CompletionItemKind.Method, insertText: 'ctx.getScreenSize()', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Get {width, height}', range },
            { label: 'askLLM', kind: monaco.languages.CompletionItemKind.Method, insertText: "await ctx.askLLM([\n\t{ role: 'system', content: '${1:system prompt}' },\n\t{ role: 'user', content: '${2:user message}' }\n], { screenshot: ${3|true,false|} })", insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Ask AI model', range },
            { label: 'log', kind: monaco.languages.CompletionItemKind.Method, insertText: "await ctx.log('${1:message}', '${2|INFO,WARN,ERROR,DEBUG|}')", insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Log message', range },
            { label: 'clipboardCopy', kind: monaco.languages.CompletionItemKind.Method, insertText: "ctx.clipboardCopy('${1:text}')", insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Copy to clipboard', range },
            { label: 'clipboardPaste', kind: monaco.languages.CompletionItemKind.Method, insertText: 'ctx.clipboardPaste()', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Paste from clipboard', range },
            { label: 'clipboardGet', kind: monaco.languages.CompletionItemKind.Method, insertText: 'await ctx.clipboardGet()', insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, detail: 'Read clipboard', range },
          ],
        };
      }

      // Top-level SDK snippets
      return {
        suggestions: [
          {
            label: 'defineAgent',
            kind: monaco.languages.CompletionItemKind.Snippet,
            insertText: [
              "import { defineAgent } from '@ogenti/sdk';",
              '',
              'export default defineAgent({',
              "  name: '${1:Agent Name}',",
              "  slug: '${2:agent-slug}',",
              "  description: '${3:What this agent does}',",
              "  category: '${4|AUTOMATION,PRODUCTIVITY,DEVELOPMENT,DESIGN,DATA_ANALYSIS|}',",
              '',
              '  async run(ctx, prompt) {',
              '    ${5:// Your agent logic}',
              '  }',
              '});',
            ].join('\n'),
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            detail: 'Define a new OGENTI agent',
            documentation: 'Creates a complete agent definition with the defineAgent helper',
            range,
          },
          {
            label: 'screenshot-analyze',
            kind: monaco.languages.CompletionItemKind.Snippet,
            insertText: [
              '// Screenshot ??Analyze ??Act pattern',
              'await ctx.sendScreenshot();',
              'const analysis = await ctx.askLLM([',
              "  { role: 'system', content: '${1:Analyze the screenshot}' },",
              "  { role: 'user', content: prompt }",
              '], { screenshot: true });',
            ].join('\n'),
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            detail: 'Screenshot ??Analyze ??Act',
            range,
          },
          {
            label: 'task-loop',
            kind: monaco.languages.CompletionItemKind.Snippet,
            insertText: [
              '// Multi-step task loop',
              'for (let step = 0; step < ${1:10}; step++) {',
              '  await ctx.sendScreenshot();',
              '  const action = await ctx.askLLM([',
              '    { role: \'system\', content: `Step ${step+1}: ${2:task description}` },',
              "    { role: 'user', content: 'What next? Reply DONE if complete.' }",
              '  ], { screenshot: true });',
              "  if (action.includes('DONE')) break;",
              '  // Execute action...',
              '  await new Promise(r => setTimeout(r, 1000));',
              '}',
            ].join('\n'),
            insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            detail: 'Multi-step automation loop',
            range,
          },
        ],
      };
    },
  });
}

export default function CodeEditor() {
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);

  const {
    files,
    activeFileId,
    updateFileContent,
    setActiveFile,
    closeFile,
  } = useIDEStore();

  const activeFile = files.find((f) => f.id === activeFileId);

  const handleEditorMount: OnMount = useCallback((editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;

    // Register theme
    monaco.editor.defineTheme('ogenti-dark', OGENTI_THEME_DATA);
    monaco.editor.setTheme('ogenti-dark');

    // Add SDK type definitions
    monaco.languages.typescript.typescriptDefaults.addExtraLib(
      SDK_TYPE_DEFS,
      'file:///node_modules/@ogenti/sdk/index.d.ts'
    );

    // Configure TypeScript compiler
    monaco.languages.typescript.typescriptDefaults.setCompilerOptions({
      target: monaco.languages.typescript.ScriptTarget.ES2020,
      moduleResolution: monaco.languages.typescript.ModuleResolutionKind.NodeJs,
      module: monaco.languages.typescript.ModuleKind.ESNext,
      allowNonTsExtensions: true,
      strict: true,
      jsx: monaco.languages.typescript.JsxEmit.React,
      esModuleInterop: true,
    });

    // Register completion providers
    registerCompletionProviders(monaco);

    // Keybindings
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      // Save handled by parent
    });

    editor.focus();
  }, []);

  const handleChange: OnChange = useCallback(
    (value) => {
      if (activeFileId && value !== undefined) {
        updateFileContent(activeFileId, value);
      }
    },
    [activeFileId, updateFileContent]
  );

  return (
    <div className="flex flex-col h-full bg-bg-secondary">
      {/* Tab bar */}
      <div className="flex items-center bg-bg-secondary border-b border-border-primary overflow-x-auto scrollbar-thin">
        {files.map((file) => (
          <button
            key={file.id}
            onClick={() => setActiveFile(file.id)}
            className={`
              flex items-center gap-2.5 px-5 py-3 text-sm font-mono border-r border-border-primary
              transition-all whitespace-nowrap group
              ${file.id === activeFileId
                ? 'bg-bg-secondary text-text-primary border-b-2 border-b-accent -mb-px'
                : 'bg-bg-tertiary text-text-tertiary hover:text-text-secondary hover:bg-bg-elevated/30'
              }
            `}
          >
            <span className="text-accent text-xs font-semibold">TS</span>
            <span>{file.name}</span>
            {file.isDirty && (
              <span className="w-2 h-2 rounded-full bg-accent" />
            )}
            {files.length > 1 && (
              <span
                onClick={(e) => { e.stopPropagation(); closeFile(file.id); }}
                className="ml-1 opacity-0 group-hover:opacity-100 hover:text-error transition-all text-base"
              >
                ×
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Editor */}
      <div className="flex-1 min-h-0">
        {activeFile ? (
          <Editor
            height="100%"
            language={activeFile.language}
            value={activeFile.content}
            onChange={handleChange}
            onMount={handleEditorMount}
            theme="ogenti-dark"
            options={{
              fontSize: 13,
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              fontLigatures: true,
              minimap: { enabled: true, maxColumn: 80 },
              scrollBeyondLastLine: false,
              smoothScrolling: true,
              cursorBlinking: 'smooth',
              cursorSmoothCaretAnimation: 'on',
              renderLineHighlight: 'all',
              roundedSelection: true,
              padding: { top: 12 },
              lineNumbers: 'on',
              glyphMargin: false,
              folding: true,
              bracketPairColorization: { enabled: true },
              autoClosingBrackets: 'always',
              autoClosingQuotes: 'always',
              autoIndent: 'full',
              formatOnPaste: true,
              suggestOnTriggerCharacters: true,
              quickSuggestions: {
                strings: true,
                comments: false,
                other: true,
              },
              wordWrap: 'on',
              tabSize: 2,
              renderWhitespace: 'selection',
              guides: {
                indentation: true,
                bracketPairs: true,
              },
            }}
          />
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center space-y-4">
              <div className="w-16 h-16 rounded-2xl bg-bg-elevated border border-border-primary flex items-center justify-center mx-auto">
                <Code2 size={24} className="text-text-tertiary" />
              </div>
              <div>
                <p className="text-base font-medium text-text-secondary">No file open</p>
                <p className="text-sm text-text-tertiary mt-1">Create or open a file to start editing</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
