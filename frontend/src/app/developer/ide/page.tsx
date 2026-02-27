'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Code2, Monitor, BookOpen, Terminal, Brain,
  Plus, Sparkles,
  Columns, ArrowLeft, Send,
  PanelBottomClose, PanelBottomOpen
} from 'lucide-react';
import { useIDEStore } from '@/store/ideStore';
import { useAuthStore } from '@/store/authStore';
import Link from 'next/link';

const CodeEditor = dynamic(() => import('@/components/developer/CodeEditor'), { ssr: false });
const SandboxPreview = dynamic(() => import('@/components/developer/SandboxPreview'), { ssr: false });
const DocsPanel = dynamic(() => import('@/components/developer/DocsPanel'), { ssr: false });
const CommandTerminal = dynamic(() => import('@/components/developer/CommandTerminal'), { ssr: false });
const ImitationRecorder = dynamic(() => import('@/components/developer/ImitationRecorder'), { ssr: false });

type LeftTab = 'editor' | 'imitation';

export default function IDEPage() {
  const { user, isAuthenticated } = useAuthStore();
  const {
    layout, setLayout,
    rightPanel, setRightPanel,
    bottomPanelOpen, toggleBottomPanel,
    isRecording, createFile,
    files, sandboxRunning,
  } = useIDEStore();

  const [leftTab, setLeftTab] = useState<LeftTab>('editor');
  const [leftWidth, setLeftWidth] = useState(50);
  const [bottomHeight, setBottomHeight] = useState(35);
  const [isDraggingH, setIsDraggingH] = useState(false);
  const [isDraggingV, setIsDraggingV] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const isDeveloper = user?.role === 'DEVELOPER' || user?.role === 'ADMIN';

  // Horizontal resize
  const handleHDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDraggingH(true);
  }, []);

  useEffect(() => {
    if (!isDraggingH) return;
    const handleMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setLeftWidth(Math.max(20, Math.min(80, pct)));
    };
    const handleUp = () => setIsDraggingH(false);
    document.addEventListener('mousemove', handleMove);
    document.addEventListener('mouseup', handleUp);
    return () => {
      document.removeEventListener('mousemove', handleMove);
      document.removeEventListener('mouseup', handleUp);
    };
  }, [isDraggingH]);

  // Vertical resize
  const handleVDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDraggingV(true);
  }, []);

  useEffect(() => {
    if (!isDraggingV) return;
    const handleMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = 100 - ((e.clientY - rect.top) / rect.height) * 100;
      setBottomHeight(Math.max(15, Math.min(60, pct)));
    };
    const handleUp = () => setIsDraggingV(false);
    document.addEventListener('mousemove', handleMove);
    document.addEventListener('mouseup', handleUp);
    return () => {
      document.removeEventListener('mousemove', handleMove);
      document.removeEventListener('mouseup', handleUp);
    };
  }, [isDraggingV]);

  if (!isAuthenticated || !isDeveloper) {
    return (
      <div className="flex items-center justify-center h-full bg-bg-primary">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center space-y-6"
        >
          <div className="w-20 h-20 rounded-2xl bg-accent/10 flex items-center justify-center mx-auto">
            <Code2 size={32} className="text-accent" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Developer IDE</h1>
            <p className="text-sm text-text-secondary mt-2">
              Upgrade to a developer account to access the IDE.
            </p>
          </div>
          <Link href="/settings">
            <button className="btn-primary text-sm">
              Upgrade Account
            </button>
          </Link>
        </motion.div>
      </div>
    );
  }

  const showEditor = layout !== 'sandbox-only';
  const showSandbox = layout !== 'editor-only';
  const showRight = rightPanel !== 'none';

  return (
    <div className="flex flex-col h-full overflow-hidden bg-bg-primary select-none">
      {/* ─── Title Bar ─── */}
      <div className="flex items-center h-12 px-3 bg-bg-secondary border-b border-border-primary flex-shrink-0">
        {/* Left section */}
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          <Link
            href="/developer"
            className="flex items-center gap-2 px-3 py-2 text-sm text-text-tertiary hover:text-text-primary hover:bg-bg-elevated rounded-lg transition-all"
          >
            <ArrowLeft size={14} />
            <span className="hidden sm:inline font-medium">IDE</span>
          </Link>

          <div className="w-px h-5 bg-border-primary mx-1" />

          {/* Activity tabs */}
          <div className="flex items-center gap-0.5 p-1 rounded-lg bg-bg-tertiary/60">
            <ActivityTab
              active={leftTab === 'editor'}
              onClick={() => setLeftTab('editor')}
              icon={<Code2 size={14} />}
              label="Editor"
            />
            <ActivityTab
              active={leftTab === 'imitation'}
              onClick={() => setLeftTab('imitation')}
              icon={<Brain size={14} />}
              label="Imitation"
              badge={isRecording}
            />
          </div>

          <div className="w-px h-5 bg-border-primary mx-1" />

          <ToolbarButton
            icon={<Plus size={14} />}
            label="New File"
            onClick={() => {
              const name = prompt('File name:', 'new-plugin.ts');
              if (name) createFile(name);
            }}
          />
        </div>

        {/* Center — Layout */}
        <div className="flex items-center gap-0.5 p-1 rounded-lg bg-bg-tertiary/60">
          <LayoutTab
            active={layout === 'editor-sandbox'}
            onClick={() => setLayout('editor-sandbox')}
            icon={<Columns size={14} />}
            tooltip="Split View"
          />
          <LayoutTab
            active={layout === 'editor-only'}
            onClick={() => setLayout('editor-only')}
            icon={<Code2 size={14} />}
            tooltip="Editor Only"
          />
          <LayoutTab
            active={layout === 'sandbox-only'}
            onClick={() => setLayout('sandbox-only')}
            icon={<Monitor size={14} />}
            tooltip="Sandbox Only"
          />
        </div>

        {/* Right section */}
        <div className="flex items-center gap-1.5 flex-1 min-w-0 justify-end">
          <PanelToggle
            active={rightPanel === 'docs'}
            onClick={() => setRightPanel(rightPanel === 'docs' ? 'none' : 'docs')}
            icon={<BookOpen size={14} />}
            label="Docs"
          />
          <PanelToggle
            active={rightPanel === 'ai-assist'}
            onClick={() => setRightPanel(rightPanel === 'ai-assist' ? 'none' : 'ai-assist')}
            icon={<Sparkles size={14} />}
            label="AI"
          />
          <div className="w-px h-5 bg-border-primary mx-1" />
          <button
            onClick={toggleBottomPanel}
            className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-all
              ${bottomPanelOpen
                ? 'text-accent bg-accent-subtle font-medium'
                : 'text-text-tertiary hover:text-text-primary hover:bg-bg-elevated'
              }`}
            title="Toggle terminal"
          >
            {bottomPanelOpen ? <PanelBottomClose size={14} /> : <PanelBottomOpen size={14} />}
          </button>
        </div>
      </div>

      {/* ─── Main Content ─── */}
      <div ref={containerRef} className="flex-1 flex flex-col min-h-0">
        <div
          className="flex min-h-0"
          style={{ height: bottomPanelOpen ? `${100 - bottomHeight}%` : '100%' }}
        >
          {/* Left: Editor or Imitation */}
          {showEditor && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
              style={{ width: !showSandbox ? '100%' : `${leftWidth}%` }}
              className="min-w-0 h-full"
            >
              {leftTab === 'editor' ? <CodeEditor /> : <ImitationRecorder />}
            </motion.div>
          )}

          {/* Drag handle H */}
          {layout === 'editor-sandbox' && (
            <div
              className={`w-[3px] cursor-col-resize relative group flex-shrink-0 transition-colors
                ${isDraggingH ? 'bg-accent/50' : 'bg-border-primary hover:bg-accent/30'}`}
              onMouseDown={handleHDragStart}
            >
              <div className="absolute inset-y-0 -left-1 -right-1" />
            </div>
          )}

          {/* Right: Sandbox */}
          {showSandbox && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2, delay: 0.05 }}
              style={{ width: !showEditor ? '100%' : `${100 - leftWidth}%` }}
              className="min-w-0 h-full"
            >
              <SandboxPreview />
            </motion.div>
          )}

          {/* Panel: Docs or AI */}
          <AnimatePresence>
            {showRight && (
              <motion.div
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 340, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: 'easeInOut' }}
                className="flex-shrink-0 h-full overflow-hidden border-l border-border-primary"
              >
                {rightPanel === 'docs' && <DocsPanel />}
                {rightPanel === 'ai-assist' && <AIAssistPanel />}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Drag handle V */}
        {bottomPanelOpen && (
          <div
            className={`h-[3px] cursor-row-resize relative group flex-shrink-0 transition-colors
              ${isDraggingV ? 'bg-accent/50' : 'bg-border-primary hover:bg-accent/30'}`}
            onMouseDown={handleVDragStart}
          >
            <div className="absolute inset-x-0 -top-1 -bottom-1" />
          </div>
        )}

        {/* Bottom: Terminal */}
        <AnimatePresence>
          {bottomPanelOpen && (
            <motion.div
              initial={{ height: 0 }}
              animate={{ height: `${bottomHeight}%` }}
              exit={{ height: 0 }}
              transition={{ duration: 0.15 }}
              className="min-h-0 overflow-hidden"
            >
              <CommandTerminal />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ─── Status Bar ─── */}
      <div className="flex items-center justify-between h-8 px-4 bg-bg-secondary border-t border-border-primary text-xs flex-shrink-0">
        <div className="flex items-center gap-4">
          {sandboxRunning ? (
            <span className="flex items-center gap-2 text-success">
              <span className="w-2 h-2 rounded-full bg-success shadow-[0_0_8px_rgba(74,222,128,0.4)]" />
              Sandbox Active
            </span>
          ) : (
            <span className="flex items-center gap-2 text-text-tertiary">
              <span className="w-2 h-2 rounded-full bg-text-tertiary/30" />
              Sandbox Idle
            </span>
          )}
          {isRecording && (
            <span className="flex items-center gap-2 text-error">
              <span className="w-2 h-2 rounded-full bg-error animate-pulse shadow-[0_0_8px_rgba(239,68,68,0.4)]" />
              Recording
            </span>
          )}
          <span className="text-text-tertiary/30">|</span>
          <span className="text-text-tertiary">{files.length} file{files.length !== 1 ? 's' : ''}</span>
        </div>
        <div className="flex items-center gap-5 text-text-tertiary">
          <span>TypeScript</span>
          <span>UTF-8</span>
          <span className="text-text-secondary font-medium">OGENTI SDK v1.0</span>
        </div>
      </div>
    </div>
  );
}

/* ─── Toolbar Sub-components ─── */

function ActivityTab({ active, onClick, icon, label, badge }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; label: string; badge?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-3.5 py-1.5 text-sm font-medium rounded-md transition-all relative
        ${active
          ? 'bg-bg-elevated text-text-primary shadow-sm'
          : 'text-text-tertiary hover:text-text-secondary hover:bg-bg-elevated/50'
        }`}
    >
      {icon}
      {label}
      {badge && (
        <span className="w-2 h-2 rounded-full bg-error animate-pulse absolute -top-0.5 -right-0.5" />
      )}
    </button>
  );
}

function LayoutTab({ active, onClick, icon, tooltip }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; tooltip: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center justify-center w-8 h-8 rounded-md transition-all
        ${active
          ? 'bg-bg-elevated text-accent shadow-sm'
          : 'text-text-tertiary hover:text-text-secondary hover:bg-bg-elevated/50'
        }`}
      title={tooltip}
    >
      {icon}
    </button>
  );
}

function ToolbarButton({ icon, label, onClick }: {
  icon: React.ReactNode; label: string; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 px-3 py-2 text-sm text-text-tertiary hover:text-text-primary hover:bg-bg-elevated rounded-lg transition-all"
    >
      {icon}
      {label}
    </button>
  );
}

function PanelToggle({ active, onClick, icon, label }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-all
        ${active
          ? 'text-accent bg-accent-subtle font-medium'
          : 'text-text-tertiary hover:text-text-primary hover:bg-bg-elevated'
        }`}
    >
      {icon}
      {label}
    </button>
  );
}

/* ─── AI Assist Panel ─── */

function AIAssistPanel() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<{ role: 'user' | 'ai'; content: string }[]>([
    {
      role: 'ai',
      content: `I'm your OGENTI coding assistant. I can help you:\n\n• Write agent plugin code\n• Debug issues with your agent\n• Explain SDK functions\n• Suggest patterns for your use case\n\nAsk me anything about building agents.`,
    },
  ]);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { files, activeFileId } = useIDEStore();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setInput('');
    setLoading(true);

    try {
      const activeFile = files.find((f) => f.id === activeFileId);
      const response = await fetch('http://localhost:4000/api/ide/ai-assist', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('accessToken')}`,
        },
        body: JSON.stringify({
          message: text,
          currentCode: activeFile?.content || '',
          fileName: activeFile?.name || 'agent.ts',
        }),
      });

      if (!response.ok) {
        setMessages((prev) => [
          ...prev,
          {
            role: 'ai',
            content: `Here are some tips:\n\n1. Use \`ctx.sendScreenshot()\` to see the current screen\n2. Use \`ctx.askLLM(messages, { screenshot: true })\` to analyze what's visible\n3. The agent runs in a loop — check state after each action\n\nCheck the Docs panel for the full API reference.`,
          },
        ]);
        return;
      }

      const data = await response.json();
      setMessages((prev) => [
        ...prev,
        { role: 'ai', content: data.data?.response || 'No response generated.' },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'ai', content: 'Connection error. Check the SDK Docs for offline reference.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-bg-primary">
      {/* Header */}
      <div className="flex items-center justify-between px-5 h-12 bg-bg-secondary border-b border-border-primary flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <Sparkles size={15} className="text-accent" />
          <span className="text-sm font-semibold text-text-primary">AI Assistant</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5">
        {messages.map((msg, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
          >
            {msg.role === 'user' ? (
              <div className="flex justify-end">
                <div className="max-w-[85%] text-sm leading-relaxed text-text-primary bg-bg-elevated rounded-2xl rounded-br-sm px-4 py-3 border border-border-primary">
                  {msg.content}
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-xs text-accent font-semibold">
                  <Sparkles size={11} />
                  AI
                </div>
                <div className="text-sm leading-relaxed text-text-secondary whitespace-pre-wrap">
                  {msg.content}
                </div>
              </div>
            )}
          </motion.div>
        ))}
        {loading && (
          <div className="flex items-center gap-2.5 text-sm text-text-tertiary">
            <div className="flex gap-1">
              <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:300ms]" />
            </div>
            Thinking...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-border-primary bg-bg-secondary">
        <div className="flex items-center gap-2 bg-bg-tertiary rounded-xl border border-border-primary focus-within:border-accent/40 transition-colors">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask about SDK..."
            className="flex-1 px-4 py-3 text-sm bg-transparent text-text-primary placeholder:text-text-tertiary outline-none"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="p-2.5 mr-2 text-accent hover:bg-accent-subtle rounded-lg transition-colors disabled:opacity-20"
          >
            <Send size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
