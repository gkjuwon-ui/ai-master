'use client';

import { useState, useCallback } from 'react';
import {
  Circle, Square, Play, Sparkles, Clock, MousePointer,
  Keyboard, Navigation, Eye, Loader2, Copy, Check,
  ChevronDown, ChevronRight, Tag, Brain, Zap, Download
} from 'lucide-react';
import { useIDEStore, ImitationSession, RecordedAction } from '@/store/ideStore';
import { api } from '@/lib/api';
import toast from 'react-hot-toast';

// Action type icons
const ACTION_ICONS: Record<string, any> = {
  click: MousePointer,
  type: Keyboard,
  key: Keyboard,
  scroll: Navigation,
  drag: Navigation,
  navigate: Eye,
  open_app: Play,
  close_app: Square,
  search: Eye,
  terminal_command: Square,
  custom: Sparkles,
};

export default function ImitationRecorder() {
  const [sessionName, setSessionName] = useState('');
  const [expandedSession, setExpandedSession] = useState<string | null>(null);
  const [generating, setGenerating] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState(false);
  const [copiedPrompt, setCopiedPrompt] = useState(false);

  const {
    imitationSessions,
    isRecording,
    activeImitationId,
    startRecording,
    stopRecording,
    setGeneratedCode,
    files,
    activeFileId,
    updateFileContent,
    addTerminalLog,
  } = useIDEStore();

  // Start recording
  const handleStartRecording = useCallback(() => {
    const name = sessionName.trim() || `Recording ${imitationSessions.length + 1}`;
    startRecording(name);
    setSessionName('');
    addTerminalLog({ type: 'system', message: `Recording started: "${name}"` });
    addTerminalLog({ type: 'system', message: '   Perform actions in the sandbox. Click Stop when done.' });
  }, [sessionName, imitationSessions.length, startRecording, addTerminalLog]);

  // Stop recording
  const handleStopRecording = useCallback(() => {
    stopRecording();
    addTerminalLog({ type: 'system', message: 'Recording stopped.' });
    const session = imitationSessions.find((s) => s.id === activeImitationId);
    if (session) {
      addTerminalLog({
        type: 'info',
        message: `   Captured ${session.actions.length} actions. Click "Generate Code" to create agent plugin.`,
      });
    }
  }, [stopRecording, imitationSessions, activeImitationId, addTerminalLog]);

  // Generate code from recorded actions (AI-powered)
  const handleGenerate = useCallback(
    async (session: ImitationSession) => {
      setGenerating(session.id);
      addTerminalLog({ type: 'system', message: `AI generating code from "${session.name}"...` });

      try {
        // Build action description for AI
        const actionDescriptions = session.actions.map((a, i) => {
          const time = ((a.timestamp - session.startedAt) / 1000).toFixed(1);
          return `  ${i + 1}. [${time}s] ${a.type}: ${JSON.stringify(a.params)}`;
        });

        const prompt = `You are an expert OGENTI SDK developer. Based on the following recorded user actions in a sandbox environment, generate:

1. A complete agent plugin using defineAgent() that reproduces this workflow
2. A system prompt for the agent that describes when and how to perform this task

Recording name: "${session.name}"
Duration: ${session.endedAt ? ((session.endedAt - session.startedAt) / 1000).toFixed(1) : '?'}s
Actions (${session.actions.length} total):
${actionDescriptions.join('\n')}

Generate the code in this EXACT format:

===CODE===
import { defineAgent } from '@ogenti/sdk';

export default defineAgent({
  name: '${session.name}',
  slug: '${session.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}',
  description: '<describe what this agent does based on the actions>',
  category: '<best category>',
  async run(ctx, prompt) {
    // Reproduce the recorded workflow
    <generated code based on actions>
  }
});
===END_CODE===

===PROMPT===
<system prompt for the agent describing the task, when to do it, and how>
===END_PROMPT===`;

        // Call backend AI generation API
        const response = await fetch('http://localhost:4000/api/ide/generate', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('accessToken')}`,
          },
          body: JSON.stringify({ prompt, sessionName: session.name }),
        });

        if (!response.ok) {
          // Fallback: generate locally without AI
          const fallbackCode = generateFallbackCode(session);
          const fallbackPrompt = generateFallbackPrompt(session);
          setGeneratedCode(session.id, fallbackCode, fallbackPrompt);
          addTerminalLog({ type: 'info', message: '   Generated with local fallback (AI unavailable)' });
          toast.success('Code generated (offline mode)');
          setGenerating(null);
          setExpandedSession(session.id);
          return;
        }

        const data = await response.json();
        const generatedCode = data.data?.code || generateFallbackCode(session);
        const generatedPrompt = data.data?.prompt || generateFallbackPrompt(session);

        setGeneratedCode(session.id, generatedCode, generatedPrompt);
        addTerminalLog({ type: 'system', message: 'Code & prompt generated successfully!' });
        toast.success('Agent code generated from recording!');
        setExpandedSession(session.id);
      } catch (err) {
        // Fallback generation
        const fallbackCode = generateFallbackCode(session);
        const fallbackPrompt = generateFallbackPrompt(session);
        setGeneratedCode(session.id, fallbackCode, fallbackPrompt);
        addTerminalLog({ type: 'info', message: '   Generated with local template (AI connection failed)' });
        toast.success('Code generated (offline mode)');
        setExpandedSession(session.id);
      } finally {
        setGenerating(null);
      }
    },
    [setGeneratedCode, addTerminalLog]
  );

  // Copy generated code to editor
  const handleApplyCode = useCallback(
    (code: string) => {
      if (activeFileId) {
        updateFileContent(activeFileId, code);
        addTerminalLog({ type: 'info', message: 'Applied generated code to editor' });
        toast.success('Code applied to editor');
      }
    },
    [activeFileId, updateFileContent, addTerminalLog]
  );

  // Copy to clipboard
  const handleCopy = useCallback(async (text: string, type: 'code' | 'prompt') => {
    await navigator.clipboard.writeText(text);
    if (type === 'code') { setCopiedCode(true); setTimeout(() => setCopiedCode(false), 2000); }
    else { setCopiedPrompt(true); setTimeout(() => setCopiedPrompt(false), 2000); }
    toast.success('Copied!');
  }, []);

  return (
    <div className="flex flex-col h-full bg-bg-secondary">
      {/* Header */}
      <div className="px-5 py-4 border-b border-border-primary bg-bg-secondary">
        <div className="flex items-center gap-2.5 mb-2">
          <Brain size={16} className="text-accent" />
          <span className="text-sm font-semibold text-text-primary">Imitation Learning</span>
        </div>
        <p className="text-xs text-text-tertiary leading-relaxed">
          Record your actions in the sandbox. AI will analyze your workflow and generate agent code automatically.
        </p>
      </div>

      {/* Recording controls */}
      <div className="px-5 py-4 border-b border-border-primary space-y-3">
        {!isRecording ? (
          <>
            <input
              type="text"
              value={sessionName}
              onChange={(e) => setSessionName(e.target.value)}
              placeholder="Recording name (e.g., Save Excel file)"
              className="w-full px-3.5 py-2.5 text-sm bg-bg-elevated border border-border-primary rounded-lg
                         text-text-primary placeholder:text-text-tertiary outline-none
                         focus:border-accent/40 transition-colors"
            />
            <button
              onClick={handleStartRecording}
              className="w-full flex items-center justify-center gap-2.5 px-4 py-2.5 text-sm font-medium
                         bg-red-500/15 text-red-400 border border-red-500/25 rounded-xl
                         hover:bg-red-500/25 transition-all"
            >
              <Circle size={13} className="fill-current" />
              Start Recording
            </button>
          </>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-sm">
              <span className="flex items-center gap-2 text-red-400">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
                Recording...
              </span>
              <span className="text-text-tertiary text-xs">
                {imitationSessions.find((s) => s.id === activeImitationId)?.actions.length || 0} actions
              </span>
            </div>
            <button
              onClick={handleStopRecording}
              className="w-full flex items-center justify-center gap-2.5 px-4 py-2.5 text-sm font-medium
                         bg-bg-elevated text-text-primary border border-border-primary rounded-xl
                         hover:bg-bg-tertiary transition-all"
            >
              <Square size={13} className="fill-current" />
              Stop Recording
            </button>
          </div>
        )}
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto">
        {imitationSessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <div className="w-14 h-14 rounded-2xl bg-bg-elevated border border-border-primary flex items-center justify-center mb-3">
              <Zap size={22} className="text-text-tertiary opacity-40" />
            </div>
            <p className="text-sm font-medium text-text-secondary">No recordings yet</p>
            <p className="text-xs text-text-tertiary mt-1.5">
              Start recording your actions in the sandbox
            </p>
          </div>
        ) : (
          <div className="py-2">
            {imitationSessions.map((session) => {
              const isExpanded = expandedSession === session.id;
              const isGeneratingThis = generating === session.id;
              return (
                <div key={session.id} className="border-b border-border-primary/50">
                  {/* Session header */}
                  <button
                    onClick={() => setExpandedSession(isExpanded ? null : session.id)}
                    className="w-full flex items-center gap-2.5 px-5 py-3 text-sm hover:bg-bg-elevated transition-all"
                  >
                    {isExpanded ? (
                      <ChevronDown size={13} className="text-text-tertiary" />
                    ) : (
                      <ChevronRight size={13} className="text-text-tertiary" />
                    )}
                    <Tag size={12} className="text-accent" />
                    <span className="text-text-primary font-medium flex-1 text-left truncate">
                      {session.name}
                    </span>
                    <span className="text-xs text-text-tertiary">
                      {session.actions.length} actions
                    </span>
                    {session.generatedCode && (
                      <span className="text-xs text-green-400 bg-green-400/10 px-2 py-0.5 rounded-md">
                        Generated
                      </span>
                    )}
                  </button>

                  {/* Expanded session */}
                  {isExpanded && (
                    <div className="px-5 pb-4 space-y-3">
                      {/* Action timeline */}
                      <div className="max-h-48 overflow-y-auto space-y-1 bg-bg-elevated rounded-xl p-3 border border-border-primary">
                        {session.actions.length === 0 ? (
                          <p className="text-xs text-text-tertiary text-center py-3">No actions recorded</p>
                        ) : (
                          session.actions.map((action, idx) => {
                            const Icon = ACTION_ICONS[action.type] || Sparkles;
                            const timeDelta = ((action.timestamp - session.startedAt) / 1000).toFixed(1);
                            return (
                              <div
                                key={action.id}
                                className="flex items-center gap-2.5 text-xs py-1"
                              >
                                <span className="text-text-tertiary w-10 text-right font-mono">{timeDelta}s</span>
                                <Icon size={12} className="text-accent flex-shrink-0" />
                                <span className="text-text-secondary truncate">
                                  {action.type}: {JSON.stringify(action.params).slice(0, 60)}
                                </span>
                              </div>
                            );
                          })
                        )}
                      </div>

                      {!session.generatedCode && (
                        <button
                          onClick={() => handleGenerate(session)}
                          disabled={isGeneratingThis || session.actions.length === 0}
                          className="w-full flex items-center justify-center gap-2.5 px-4 py-2.5 text-sm font-medium
                                     bg-gradient-to-r from-[#f08535] to-[#c04510] text-white rounded-xl
                                     hover:opacity-90 transition-opacity disabled:opacity-50"
                        >
                          {isGeneratingThis ? (
                            <>
                              <Loader2 size={14} className="animate-spin" />
                              AI Generating...
                            </>
                          ) : (
                            <>
                              <Sparkles size={14} />
                              Generate Agent Code
                            </>
                          )}
                        </button>
                      )}

                      {/* Generated code display */}
                      {session.generatedCode && (
                        <div className="space-y-2">
                          {/* Code */}
                          <div className="bg-bg-tertiary border border-border-primary rounded-xl overflow-hidden">
                            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border-primary">
                              <span className="text-xs font-semibold text-accent">Generated Code</span>
                              <div className="flex items-center gap-1.5">
                                <button
                                  onClick={() => handleCopy(session.generatedCode!, 'code')}
                                  className="p-1.5 text-text-tertiary hover:text-text-secondary transition-colors"
                                  title="Copy"
                                >
                                  {copiedCode ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                                </button>
                                <button
                                  onClick={() => handleApplyCode(session.generatedCode!)}
                                  className="px-2.5 py-1 text-xs bg-accent/10 text-accent rounded-lg hover:bg-accent/20 transition-colors"
                                >
                                  Apply to Editor
                                </button>
                              </div>
                            </div>
                            <pre className="p-4 text-xs font-mono text-text-secondary overflow-x-auto max-h-52">
                              <code>{session.generatedCode}</code>
                            </pre>
                          </div>

                          {/* Prompt */}
                          {session.generatedPrompt && (
                            <div className="bg-bg-tertiary border border-border-primary rounded-xl overflow-hidden">
                              <div className="flex items-center justify-between px-4 py-2.5 border-b border-border-primary">
                                <span className="text-xs font-semibold text-purple-400">Generated Prompt</span>
                                <button
                                  onClick={() => handleCopy(session.generatedPrompt!, 'prompt')}
                                  className="p-1.5 text-text-tertiary hover:text-text-secondary transition-colors"
                                  title="Copy"
                                >
                                  {copiedPrompt ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
                                </button>
                              </div>
                              <div className="p-4 text-xs text-text-secondary max-h-36 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                                {session.generatedPrompt}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ?? Fallback Code Generator (no AI needed) ??

function generateFallbackCode(session: ImitationSession): string {
  const slug = session.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const lines: string[] = [];
  lines.push(`import { defineAgent } from '@ogenti/sdk';`);
  lines.push('');
  lines.push('export default defineAgent({');
  lines.push(`  name: '${session.name}',`);
  lines.push(`  slug: '${slug}',`);
  lines.push(`  description: 'Agent that automates: ${session.name}',`);
  lines.push(`  category: 'AUTOMATION',`);
  lines.push('');
  lines.push('  async run(ctx, prompt) {');
  lines.push(`    await ctx.log('Starting: ${session.name}');`);
  lines.push('');

  // Convert recorded actions to code
  for (const action of session.actions) {
    const delay = `    await new Promise(r => setTimeout(r, 500));`;
    switch (action.type) {
      case 'click':
        lines.push(`    // Click at (${action.params.x}, ${action.params.y})`);
        lines.push(`    ctx.click(${action.params.x}, ${action.params.y});`);
        lines.push(delay);
        break;
      case 'type':
        lines.push(`    // Type text`);
        lines.push(`    ctx.typeText('${(action.params.text || '').replace(/'/g, "\\'")}');`);
        lines.push(delay);
        break;
      case 'key':
        if (action.params.ctrl || action.params.alt || action.params.shift) {
          const keys: string[] = [];
          if (action.params.ctrl) keys.push("'ctrl'");
          if (action.params.alt) keys.push("'alt'");
          if (action.params.shift) keys.push("'shift'");
          keys.push(`'${action.params.key}'`);
          lines.push(`    ctx.hotkey(${keys.join(', ')});`);
        } else {
          lines.push(`    ctx.pressKey('${action.params.key}');`);
        }
        lines.push(delay);
        break;
      case 'scroll':
        lines.push(`    ctx.scroll(${action.params.clicks || 3});`);
        lines.push(delay);
        break;
      case 'navigate':
        lines.push(`    // Navigate to: ${action.params.url}`);
        lines.push(`    await ctx.runCommand('start ${action.params.url}');`);
        lines.push(delay);
        break;
      case 'open_app':
        lines.push(`    ctx.openApp('${action.params.app}');`);
        lines.push(`    await new Promise(r => setTimeout(r, 2000));`);
        break;
      case 'terminal_command':
        lines.push(`    await ctx.runCommand('${(action.params.command || '').replace(/'/g, "\\'")}');`);
        lines.push(delay);
        break;
      default:
        lines.push(`    // ${action.type}: ${JSON.stringify(action.params)}`);
        break;
    }
    lines.push('');
  }

  lines.push(`    await ctx.log('Completed: ${session.name}');`);
  lines.push('  }');
  lines.push('});');

  return lines.join('\n');
}

function generateFallbackPrompt(session: ImitationSession): string {
  const actionTypes = [...new Set(session.actions.map((a) => a.type))];
  const duration = session.endedAt
    ? ((session.endedAt - session.startedAt) / 1000).toFixed(1)
    : '?';

  return `You are an agent that performs the task "${session.name}".

Task Description:
This workflow involves ${session.actions.length} steps taking approximately ${duration} seconds.
The main actions used are: ${actionTypes.join(', ')}.

Instructions:
1. Start by taking a screenshot to understand the current state
2. Follow the recorded workflow steps in order
3. After each major action, take a screenshot to verify the result
4. If something doesn't look right, use askLLM to reason about the best recovery action
5. Log progress at key checkpoints

Key Behaviors:
${session.actions
  .filter((a) => ['open_app', 'navigate', 'terminal_command'].includes(a.type))
  .map((a) => `- ${a.type}: ${JSON.stringify(a.params)}`)
  .join('\n') || '- Execute the recorded click and keyboard sequence precisely'}

Error Handling:
- If a click target is not found, take a screenshot and ask the LLM where the element moved
- If a dialog appears unexpectedly, close it and retry the last action
- Always confirm completion by taking a final screenshot

Prompt Caching: This prompt should be cached for repeated use with cache key "${session.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}".`;
}
