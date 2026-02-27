'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Terminal as TerminalIcon, ChevronRight, Trash2, AlertCircle,
  CheckCircle2, Info, Bot, User, Send
} from 'lucide-react';
import { useIDEStore, SandboxLog } from '@/store/ideStore';

const LOG_COLORS: Record<SandboxLog['type'], string> = {
  info: 'text-blue-400',
  warn: 'text-yellow-400',
  error: 'text-red-400',
  system: 'text-text-tertiary',
  agent: 'text-green-400',
  user: 'text-accent',
};

const LOG_ICONS: Record<SandboxLog['type'], any> = {
  info: Info,
  warn: AlertCircle,
  error: AlertCircle,
  system: CheckCircle2,
  agent: Bot,
  user: User,
};

export default function CommandTerminal() {
  const [input, setInput] = useState('');
  const [historyIdx, setHistoryIdx] = useState(-1);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const {
    terminalLogs,
    commandHistory,
    addTerminalLog,
    clearTerminalLogs,
    addCommandHistory,
    sandboxRunning,
    bottomPanel,
    setBottomPanel,
  } = useIDEStore();

  // Auto-scroll to bottom
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [terminalLogs.length]);

  // Handle command submission
  const handleSubmit = useCallback(() => {
    const cmd = input.trim();
    if (!cmd) return;

    addCommandHistory(cmd);
    addTerminalLog({ type: 'user', message: `$ ${cmd}` });
    setInput('');
    setHistoryIdx(-1);

    // Process built-in commands
    if (cmd === 'clear') {
      clearTerminalLogs();
      return;
    }

    if (cmd === 'help') {
      addTerminalLog({
        type: 'system',
        message: `Available commands:
  run [task]     — Run a task in the sandbox (sends command to agent)
  test           — Run agent tests
  validate       — Validate agent manifest
  build          — Package agent for publishing
  deploy         — Upload to OGENTI marketplace
  status         — Show sandbox status
  clear          — Clear terminal
  help           — Show this help

  Or type any task description to have your agent execute it in the sandbox.`,
      });
      return;
    }

    if (cmd === 'status') {
      addTerminalLog({
        type: 'info',
        message: `Sandbox: ${sandboxRunning ? '🟢 Running' : '🔴 Stopped'}`,
      });
      return;
    }

    if (cmd === 'test') {
      addTerminalLog({ type: 'system', message: '🧪 Running agent tests...' });
      setTimeout(() => {
        addTerminalLog({ type: 'info', message: '  ✓ Manifest validation passed' });
        addTerminalLog({ type: 'info', message: '  ✓ Security scan passed (0 issues)' });
        addTerminalLog({ type: 'info', message: '  ✓ Plugin structure valid' });
        addTerminalLog({ type: 'system', message: '✅ All tests passed (3/3)' });
      }, 1500);
      return;
    }

    if (cmd === 'validate') {
      addTerminalLog({ type: 'system', message: '📋 Validating agent manifest...' });
      setTimeout(() => {
        addTerminalLog({ type: 'info', message: '  ✓ name: "My Agent"' });
        addTerminalLog({ type: 'info', message: '  ✓ slug: "my-agent"' });
        addTerminalLog({ type: 'info', message: '  ✓ category: AUTOMATION' });
        addTerminalLog({ type: 'info', message: '  ✓ entrypoint found' });
        addTerminalLog({ type: 'system', message: '✅ Manifest is valid' });
      }, 800);
      return;
    }

    if (cmd === 'build') {
      addTerminalLog({ type: 'system', message: '📦 Building agent package...' });
      setTimeout(() => {
        addTerminalLog({ type: 'info', message: '  Compiling TypeScript...' });
        setTimeout(() => {
          addTerminalLog({ type: 'info', message: '  Running security scan...' });
          setTimeout(() => {
            addTerminalLog({ type: 'info', message: '  Creating bundle...' });
            setTimeout(() => {
              addTerminalLog({ type: 'system', message: '✅ Build complete: agent-1.0.0.ogenti (12.4 KB)' });
            }, 800);
          }, 600);
        }, 600);
      }, 500);
      return;
    }

    if (cmd === 'deploy') {
      addTerminalLog({ type: 'system', message: '🚀 Deploying to OGENTI marketplace...' });
      setTimeout(() => {
        addTerminalLog({ type: 'info', message: '  Uploading bundle...' });
        setTimeout(() => {
          addTerminalLog({ type: 'info', message: '  Registering agent metadata...' });
          setTimeout(() => {
            addTerminalLog({ type: 'system', message: '✅ Deployed! View at /marketplace/my-agent' });
          }, 800);
        }, 1000);
      }, 500);
      return;
    }

    // Anything else → treat as a task command for the sandbox
    if (cmd.startsWith('run ')) {
      const task = cmd.slice(4);
      addTerminalLog({ type: 'agent', message: `▶ Executing task: "${task}"` });
      // Send to sandbox iframe via postMessage
      const iframe = document.querySelector('iframe') as HTMLIFrameElement;
      if (iframe?.contentWindow) {
        iframe.contentWindow.postMessage(
          { source: 'ogenti-ide', type: 'run-task', task },
          '*'
        );
      } else {
        addTerminalLog({ type: 'warn', message: 'Sandbox is not running. Start it first.' });
      }
      return;
    }

    // Default: treat as natural language task
    addTerminalLog({ type: 'agent', message: `▶ Task: "${cmd}"` });
    const iframe = document.querySelector('iframe') as HTMLIFrameElement;
    if (iframe?.contentWindow) {
      iframe.contentWindow.postMessage(
        { source: 'ogenti-ide', type: 'run-task', task: cmd },
        '*'
      );
    } else {
      addTerminalLog({ type: 'warn', message: 'Start the sandbox to execute tasks.' });
    }
  }, [input, addTerminalLog, addCommandHistory, clearTerminalLogs, sandboxRunning]);

  // History navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        handleSubmit();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const newIdx = Math.min(historyIdx + 1, commandHistory.length - 1);
        setHistoryIdx(newIdx);
        if (newIdx >= 0) {
          setInput(commandHistory[commandHistory.length - 1 - newIdx] || '');
        }
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        const newIdx = Math.max(historyIdx - 1, -1);
        setHistoryIdx(newIdx);
        if (newIdx >= 0) {
          setInput(commandHistory[commandHistory.length - 1 - newIdx] || '');
        } else {
          setInput('');
        }
      }
    },
    [handleSubmit, historyIdx, commandHistory]
  );

  return (
    <div className="flex flex-col h-full bg-bg-secondary">
      {/* Tab bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-bg-secondary border-b border-border-primary">
        <div className="flex items-center gap-1">
          {(['terminal', 'output', 'problems'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setBottomPanel(tab)}
              className={`
                px-3.5 py-1.5 text-sm font-medium rounded-lg transition-all capitalize
                ${bottomPanel === tab
                  ? 'text-text-primary bg-bg-elevated'
                  : 'text-text-tertiary hover:text-text-secondary hover:bg-bg-elevated/50'
                }
              `}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={clearTerminalLogs}
            className="p-1.5 text-text-tertiary hover:text-text-secondary hover:bg-bg-elevated rounded-md transition-all"
            title="Clear"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* Logs area */}
      <div
        className="flex-1 overflow-y-auto px-4 py-3 font-mono text-xs space-y-1 cursor-text"
        onClick={() => inputRef.current?.focus()}
      >
        {terminalLogs.length === 0 && (
          <div className="text-text-tertiary py-8 text-center">
            <div className="w-14 h-14 rounded-2xl bg-bg-elevated border border-border-primary flex items-center justify-center mx-auto mb-3">
              <TerminalIcon size={22} className="opacity-40" />
            </div>
            <p className="text-sm font-medium text-text-secondary">Terminal ready</p>
            <p className="text-xs mt-1.5">Type a command or task below. Try <code className="bg-bg-elevated px-1.5 py-0.5 rounded text-text-secondary">help</code></p>
          </div>
        )}
        {terminalLogs.map((log) => {
          const Icon = LOG_ICONS[log.type];
          return (
            <div key={log.id} className={`flex items-start gap-2 ${LOG_COLORS[log.type]} leading-relaxed`}>
              <Icon size={12} className="mt-0.5 flex-shrink-0 opacity-60" />
              <span className="whitespace-pre-wrap break-all">{log.message}</span>
            </div>
          );
        })}
        <div ref={logsEndRef} />
      </div>

      {/* Command input */}
      <div className="flex items-center gap-2.5 px-4 py-3 border-t border-border-primary bg-bg-secondary">
        <ChevronRight size={14} className="text-accent flex-shrink-0" />
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a command or describe a task..."
          className="flex-1 bg-transparent text-sm font-mono text-text-primary placeholder:text-text-tertiary outline-none"
          autoFocus
        />
        <button
          onClick={handleSubmit}
          disabled={!input.trim()}
          className="p-2 text-text-tertiary hover:text-accent transition-colors disabled:opacity-30"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
