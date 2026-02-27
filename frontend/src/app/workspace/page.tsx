'use client';

import { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Play, Pause, Square, Plus, X, Send, Monitor,
  Terminal, Clock, Cpu, Image, ChevronRight,
  AlertCircle, CheckCircle2,
  Loader2, RotateCcw, Trash2,
  ShoppingCart, Star, Download, ExternalLink, ShieldAlert, ArrowRight, Brain
} from 'lucide-react';
import { useExecutionStore } from '@/store/executionStore';
import { useAgentStore } from '@/store/agentStore';
import { useAuthStore } from '@/store/authStore';
import { useSettingsStore } from '@/store/settingsStore';
import { Button } from '@/components/common/Button';
import { Loading, EmptyState } from '@/components/common/Loading';
import { Modal } from '@/components/common/Modal';
import { formatRelativeTime, truncate, formatPrice } from '@/lib/utils';
import { api } from '@/lib/api';
import Link from 'next/link';
import toast from 'react-hot-toast';

export default function WorkspacePage() {
  return (
    <Suspense fallback={<Loading />}>
      <WorkspaceContent />
    </Suspense>
  );
}

function WorkspaceContent() {
  const searchParams = useSearchParams();
  const { isAuthenticated } = useAuthStore();
  const { purchasedAgents, fetchPurchasedAgents } = useAgentStore();
  const { llmConfigs, fetchLLMConfigs } = useSettingsStore();
  const {
    sessions, currentSession, logs, selectedAgentIds,
    isExecuting, screenshot,
    setSelectedAgents, createSession, startExecution,
    pauseExecution, cancelExecution, fetchSessions,
  } = useExecutionStore();

  const [prompt, setPrompt] = useState('');
  const [showAgentPicker, setShowAgentPicker] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [selectedLLMConfig, setSelectedLLMConfig] = useState('');
  const [showCapabilityMismatch, setShowCapabilityMismatch] = useState(false);
  const [capabilityCheckResult, setCapabilityCheckResult] = useState<any>(null);
  const [isCheckingCapabilities, setIsCheckingCapabilities] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isAuthenticated) {
      fetchPurchasedAgents();
      fetchSessions();
      fetchLLMConfigs();
    }
  }, [isAuthenticated, fetchPurchasedAgents, fetchSessions, fetchLLMConfigs]);

  // Pre-select agents from URL
  useEffect(() => {
    const agentIds = searchParams.get('agents');
    if (agentIds) {
      setSelectedAgents(agentIds.split(','));
    }
  }, [searchParams, setSelectedAgents]);

  // Auto-select first LLM config
  useEffect(() => {
    if (llmConfigs.length > 0 && !selectedLLMConfig) {
      setSelectedLLMConfig(llmConfigs[0].id);
    }
  }, [llmConfigs, selectedLLMConfig]);

  // Auto-scroll logs
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const handleStart = async () => {
    if (!prompt.trim()) { toast.error('Enter a prompt'); return; }
    if (selectedAgentIds.length === 0) { toast.error('Select at least one agent'); return; }
    if (!selectedLLMConfig && llmConfigs.length === 0) { toast.error('Please configure LLM in Settings first'); return; }

    // ── Capability pre-check ──
    try {
      setIsCheckingCapabilities(true);
      const checkRes = await api.checkCapabilities({
        prompt: prompt.trim(),
        agentIds: selectedAgentIds,
      });
      const check = checkRes;
      if (!check.ok) {
        // Mismatch detected → show marketplace suggestion popup
        setCapabilityCheckResult(check);
        setShowCapabilityMismatch(true);
        setIsCheckingCapabilities(false);
        return;
      }
    } catch {
      // If check fails, allow execution anyway
    } finally {
      setIsCheckingCapabilities(false);
    }

    await executeNow();
  };

  const executeNow = async () => {
    try {
      const session = await createSession({
        prompt: prompt.trim(),
        agentIds: selectedAgentIds,
        llmConfigId: selectedLLMConfig,
      });
      if (session) {
        await startExecution(session.id);
        toast.success('Execution started');
      }
    } catch (err: any) {
      toast.error(err.message || 'Failed to start execution');
    }
  };

  const handlePause = () => {
    if (currentSession) pauseExecution(currentSession.id);
  };

  const handleCancel = () => {
    if (currentSession) cancelExecution(currentSession.id);
  };

  const toggleAgent = (id: string) => {
    const newIds = selectedAgentIds.includes(id)
      ? selectedAgentIds.filter((a) => a !== id)
      : [...selectedAgentIds, id];
    setSelectedAgents(newIds);
  };

  if (!isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-full">
        <EmptyState
          icon={<Terminal size={48} />}
          title="Sign in to use Workspace"
          description="The workspace requires authentication to run agents."
          action={{ label: 'Sign In', onClick: () => window.location.href = '/auth/login' }}
        />
      </div>
    );
  }

  const statusColor = (status?: string) => {
    switch (status) {
      case 'RUNNING': return 'text-success';
      case 'PAUSED': return 'text-warning';
      case 'COMPLETED': return 'text-accent';
      case 'FAILED': return 'text-error';
      case 'CANCELLED': return 'text-text-tertiary';
      default: return 'text-text-secondary';
    }
  };

  const statusIcon = (status?: string) => {
    switch (status) {
      case 'RUNNING': return <Loader2 size={14} className="animate-spin text-success" />;
      case 'PAUSED': return <Pause size={14} className="text-warning" />;
      case 'COMPLETED': return <CheckCircle2 size={14} className="text-accent" />;
      case 'FAILED': return <AlertCircle size={14} className="text-error" />;
      case 'CANCELLED': return <Square size={14} className="text-text-tertiary" />;
      default: return <Clock size={14} className="text-text-secondary" />;
    }
  };

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-primary flex-shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">Workspace</h1>
          {currentSession && (
            <div className="flex items-center gap-2 text-sm">
              {statusIcon(currentSession.status)}
              <span className={statusColor(currentSession.status)}>
                {currentSession.status}
              </span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-all border border-border-primary"
          >
            <Clock size={14} />
            History
          </button>

        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* History sidebar (collapsible) */}
        <AnimatePresence>
          {showHistory && (
            <motion.div
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 280, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              className="border-r border-border-primary overflow-hidden flex-shrink-0"
            >
              <div className="w-[280px] h-full flex flex-col">
                <div className="p-3 border-b border-border-primary flex items-center justify-between">
                  <span className="text-xs font-semibold text-text-tertiary uppercase tracking-wider">Sessions</span>
                  <div className="flex items-center gap-1">
                    {sessions.length > 0 && (
                      <button
                        onClick={async () => {
                          if (!confirm('Clear all sessions?')) return;
                          const store = useExecutionStore.getState();
                          for (const s of sessions) {
                            await store.deleteSession(s.id);
                          }
                          toast.success('All sessions cleared');
                        }}
                        className="p-1 rounded hover:bg-bg-elevated text-text-tertiary hover:text-error transition-colors"
                        title="Clear all"
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                    <button onClick={() => setShowHistory(false)}>
                      <X size={14} className="text-text-tertiary hover:text-text-primary" />
                    </button>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto p-2 space-y-1">
                  {sessions.length === 0 ? (
                    <p className="text-xs text-text-tertiary text-center py-4">No sessions yet</p>
                  ) : (
                    sessions.map((session) => (
                      <div
                        key={session.id}
                        className={`group relative w-full text-left p-2.5 rounded-lg text-xs transition-all ${
                          currentSession?.id === session.id
                            ? 'bg-bg-active border border-border-active'
                            : 'hover:bg-bg-elevated'
                        }`}
                      >
                        <button
                          onClick={() => useExecutionStore.getState().loadSession(session.id)}
                          className="w-full text-left"
                        >
                          <div className="flex items-center gap-2 mb-1">
                            {statusIcon(session.status)}
                            <span className="font-medium truncate">{truncate(session.prompt || 'No prompt', 30)}</span>
                          </div>
                          <div className="text-text-tertiary flex items-center gap-2">
                            <span>{session.agents?.length || 0} agents</span>
                            <span>·</span>
                            <span>{formatRelativeTime(session.createdAt)}</span>
                          </div>
                        </button>
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            await useExecutionStore.getState().deleteSession(session.id);
                            toast.success('Session deleted');
                          }}
                          className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-bg-elevated text-text-tertiary hover:text-error transition-all"
                          title="Delete session"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Main workspace */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Prompt & Controls */}
          <div data-tour="ws-prompt" className="p-4 border-b border-border-primary space-y-3 flex-shrink-0">
            {/* Agent chips */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-text-tertiary">Agents:</span>
              {selectedAgentIds.length === 0 ? (
                <span className="text-xs text-text-tertiary italic">None selected</span>
              ) : (
                selectedAgentIds.map((id) => {
                  const agent = purchasedAgents.find(a => a.id === id);
                  return (
                    <span key={id} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs bg-bg-elevated border border-border-primary text-text-secondary">
                      {agent?.name || id.slice(0, 8)}
                      <button onClick={() => toggleAgent(id)} className="hover:text-error transition-colors">
                        <X size={10} />
                      </button>
                    </span>
                  );
                })
              )}
              <button
                onClick={() => setShowAgentPicker(true)}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs text-text-tertiary hover:text-text-primary hover:bg-bg-elevated border border-dashed border-border-primary transition-all"
              >
                <Plus size={10} />
                Add
              </button>
              {selectedAgentIds.length > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] text-text-tertiary ml-auto" title="Agents learn from community activity and apply knowledge to tasks">
                  <Brain size={10} />
                  Community-enhanced
                </span>
              )}
            </div>

            {/* Prompt input */}
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Describe what you want the agents to do..."
                  className="input-field w-full h-20 resize-none pr-12"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                      handleStart();
                    }
                  }}
                />
                <div className="absolute bottom-2 right-2 text-[10px] text-text-tertiary">
                  Ctrl+Enter to run
                </div>
              </div>
              <div className="flex flex-col gap-2">
                {!isExecuting ? (
                  <Button onClick={handleStart} icon={isCheckingCapabilities ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} className="h-full" disabled={isCheckingCapabilities}>
                    {isCheckingCapabilities ? 'Checking...' : 'Run'}
                  </Button>
                ) : (
                  <>
                    <Button variant="secondary" size="sm" onClick={handlePause} icon={<Pause size={14} />}>
                      Pause
                    </Button>
                    <Button variant="danger" size="sm" onClick={handleCancel} icon={<Square size={14} />}>
                      Stop
                    </Button>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Execution area — Unified Activity Feed */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Activity header */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border-primary bg-bg-secondary/30">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <Cpu size={14} className="text-text-tertiary" />
                  <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Activity</span>
                </div>
                {logs.length > 0 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-bg-elevated text-text-tertiary border border-border-primary tabular-nums">
                    {logs.length}
                  </span>
                )}
                {isExecuting && (
                  <span className="flex items-center gap-1.5 text-[10px] px-2 py-0.5 rounded-full bg-success/10 text-success border border-success/20">
                    <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
                    Live
                  </span>
                )}
              </div>
              {currentSession && (
                <div className="flex items-center gap-3 text-[11px] text-text-tertiary">
                  {currentSession.startedAt && (
                    <span className="flex items-center gap-1">
                      <Clock size={11} />
                      {formatRelativeTime(currentSession.startedAt)}
                    </span>
                  )}
                  <span className="flex items-center gap-1">
                    <Cpu size={11} />
                    {currentSession.agents?.length || 0} agent{(currentSession.agents?.length || 0) !== 1 ? 's' : ''}
                  </span>
                </div>
              )}
            </div>

            {/* Activity feed */}
            <div className="flex-1 overflow-y-auto">
              {logs.length === 0 && !isExecuting ? (
                <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-4">
                  <div className="w-16 h-16 rounded-2xl bg-bg-elevated border border-border-primary flex items-center justify-center">
                    <Play size={24} className="text-text-tertiary opacity-40" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-text-secondary mb-1">No activity yet</p>
                    <p className="text-xs text-text-tertiary max-w-[280px]">
                      Select agents, enter a prompt and click Run to start execution
                    </p>
                    <p className="text-[10px] text-text-tertiary max-w-[320px] mt-3 leading-relaxed">
                      Your agents apply skills learned from community interactions to every task, improving accuracy and speed over time.
                    </p>
                  </div>
                </div>
              ) : logs.length === 0 && isExecuting ? (
                <div className="flex flex-col items-center justify-center h-full gap-3">
                  <Loader2 size={24} className="animate-spin text-text-tertiary" />
                  <p className="text-sm text-text-tertiary">Connecting to agent runtime...</p>
                </div>
              ) : (
                <div className="p-3 space-y-0.5">
                  {logs.map((log, i) => (
                    <ActivityItem key={log.id || i} log={log} isLast={i === logs.length - 1} />
                  ))}
                  {currentSession?.status === 'COMPLETED' && (
                    <a
                      href="/dashboard"
                      className="flex items-center gap-2 mt-2 p-2.5 rounded-lg bg-black/10 border border-white/[0.03] text-[11px] text-text-tertiary hover:text-text-secondary transition-colors"
                    >
                      <Brain size={12} />
                      <span>This agent applied community-learned knowledge to this task.</span>
                      <ArrowRight size={10} className="ml-auto" />
                    </a>
                  )}
                  <div ref={logEndRef} />
                </div>
              )}
            </div>

            {/* Bottom status bar */}
            {currentSession && (
              <div className="flex items-center justify-between px-4 py-2 border-t border-border-primary bg-bg-secondary/30 text-[11px] text-text-tertiary">
                <div className="flex items-center gap-3">
                  {currentSession.agents?.map((agent: any) => (
                    <span key={agent.agentId} className="flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full ${
                        agent.status === 'RUNNING' ? 'bg-success animate-pulse' :
                        agent.status === 'COMPLETED' ? 'bg-accent' :
                        agent.status === 'FAILED' ? 'bg-error' :
                        'bg-text-tertiary/30'
                      }`} />
                      <span className={agent.status === 'RUNNING' ? 'text-text-secondary' : ''}>{agent.name}</span>
                    </span>
                  ))}
                </div>
                <span>
                  {currentSession.status === 'COMPLETED' && currentSession.result?.duration
                    ? `Completed in ${Number(currentSession.result.duration).toFixed(1)}s`
                    : currentSession.status
                  }
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Agent picker modal */}
      <Modal
        isOpen={showAgentPicker}
        onClose={() => setShowAgentPicker(false)}
        title="Select Agents"
        size="lg"
      >
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {purchasedAgents.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-text-tertiary mb-3">No agents available</p>
              <Link href="/marketplace">
                <Button variant="secondary" size="sm">Browse Marketplace</Button>
              </Link>
            </div>
          ) : (
            purchasedAgents.map((agent) => {
              const isSelected = selectedAgentIds.includes(agent.id);
              return (
                <button
                  key={agent.id}
                  onClick={() => toggleAgent(agent.id)}
                  className={`w-full flex items-center gap-3 p-3 rounded-lg transition-all text-left ${
                    isSelected
                      ? 'bg-bg-active border border-border-active'
                      : 'bg-bg-secondary border border-border-primary hover:border-border-secondary'
                  }`}
                >
                  <div className={`w-5 h-5 rounded border flex items-center justify-center flex-shrink-0 ${
                    isSelected ? 'bg-white border-white' : 'border-border-secondary'
                  }`}>
                    {isSelected && <CheckCircle2 size={14} className="text-black" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{agent.name}</div>
                    <div className="text-xs text-text-tertiary truncate">{agent.shortDescription || agent.description}</div>
                  </div>
                  <span className="text-[10px] text-text-tertiary px-2 py-0.5 rounded bg-bg-elevated border border-border-primary">
                    {agent.category}
                  </span>
                </button>
              );
            })
          )}
        </div>
        <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-border-primary">
          <Button variant="secondary" onClick={() => setShowAgentPicker(false)}>Cancel</Button>
          <Button onClick={() => setShowAgentPicker(false)}>
            Done ({selectedAgentIds.length} selected)
          </Button>
        </div>
      </Modal>

      {/* Capability Mismatch Modal — Marketplace Suggestion */}
      <Modal
        isOpen={showCapabilityMismatch}
        onClose={() => setShowCapabilityMismatch(false)}
        title="Agent Capability Mismatch"
        size="xl"
      >
        {capabilityCheckResult && (
          <div className="space-y-5">
            {/* Warning banner */}
            <div className="flex items-start gap-3 p-4 rounded-xl bg-warning/5 border border-warning/20">
              <ShieldAlert size={22} className="text-warning flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-text-primary mb-1">
                  The selected agent cannot perform this task
                </p>
                <p className="text-xs text-text-secondary leading-relaxed">
                  {capabilityCheckResult.message}
                </p>
              </div>
            </div>

            {/* Required vs Missing */}
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 rounded-lg bg-bg-elevated border border-border-primary">
                <p className="text-[10px] text-text-tertiary uppercase tracking-wider font-semibold mb-2">Required Capabilities</p>
                <div className="flex flex-wrap gap-1.5">
                  {capabilityCheckResult.requiredCategories?.map((cat: string) => (
                    <span key={cat} className="px-2 py-0.5 rounded-md text-xs bg-accent/10 text-accent border border-accent/20">
                      {cat}
                    </span>
                  ))}
                </div>
              </div>
              <div className="p-3 rounded-lg bg-bg-elevated border border-border-primary">
                <p className="text-[10px] text-text-tertiary uppercase tracking-wider font-semibold mb-2">Missing Capabilities</p>
                <div className="flex flex-wrap gap-1.5">
                  {capabilityCheckResult.missingCategories?.map((cat: string) => (
                    <span key={cat} className="px-2 py-0.5 rounded-md text-xs bg-warning/10 text-warning border border-warning/20">
                      {cat}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Suggested agents */}
            {capabilityCheckResult.suggestedAgents?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-text-secondary mb-3 flex items-center gap-2">
                  <ShoppingCart size={14} />
                  Suggested Agents — Add from Marketplace
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-64 overflow-y-auto pr-1">
                  {capabilityCheckResult.suggestedAgents.map((agent: any) => (
                    <div
                      key={agent.id}
                      className="flex items-center gap-3 p-3 rounded-lg bg-bg-secondary border border-border-primary hover:border-border-secondary transition-all group"
                    >
                      <div className="w-10 h-10 rounded-lg bg-bg-elevated border border-border-primary flex items-center justify-center text-lg flex-shrink-0">
                        {agent.icon || ''}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-medium text-text-primary truncate">{agent.name}</span>
                          {agent.owned && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] bg-success/10 text-success border border-success/20 flex-shrink-0">
                              Owned
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-text-tertiary truncate">{agent.description}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="flex items-center gap-0.5 text-[10px] text-text-tertiary">
                            <Star size={9} className="text-warning fill-warning" />
                            {agent.rating?.toFixed(1) || '0.0'}
                          </span>
                          <span className="flex items-center gap-0.5 text-[10px] text-text-tertiary">
                            <Download size={9} />
                            {agent.downloads || 0}
                          </span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-tertiary border border-border-primary">
                            {agent.category}
                          </span>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                        <span className="text-xs font-semibold text-text-primary">
                          {agent.price === 0 ? 'Free' : `$${agent.price}`}
                        </span>
                        {agent.owned ? (
                          <button
                            onClick={() => {
                              // Add to selected agents and close modal
                              const newIds = [...selectedAgentIds, agent.id];
                              setSelectedAgents(newIds);
                              setShowCapabilityMismatch(false);
                              toast.success(`${agent.name} added`);
                            }}
                            className="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold bg-accent text-white hover:bg-accent-hover transition-colors"
                          >
                            <Plus size={10} />
                            Add
                          </button>
                        ) : (
                          <Link
                            href={`/marketplace/${agent.slug || agent.id}`}
                            onClick={() => setShowCapabilityMismatch(false)}
                            className="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold bg-accent text-white hover:bg-accent-hover transition-colors"
                          >
                            <ShoppingCart size={10} />
                            Buy
                          </Link>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* No suggested agents */}
            {(!capabilityCheckResult.suggestedAgents || capabilityCheckResult.suggestedAgents.length === 0) && (
              <div className="text-center py-6">
                <p className="text-sm text-text-tertiary mb-3">No agents with the required capabilities found on the marketplace.</p>
                <Link href="/marketplace">
                  <Button variant="secondary" size="sm" icon={<ExternalLink size={12} />}>
                    Browse Marketplace
                  </Button>
                </Link>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex justify-between items-center pt-4 border-t border-border-primary">
              <button
                onClick={() => {
                  setShowCapabilityMismatch(false);
                  executeNow();
                }}
                className="text-xs text-text-tertiary hover:text-text-secondary transition-colors underline underline-offset-2"
              >
                Run anyway
              </button>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setShowCapabilityMismatch(false)}>
                  Close
                </Button>
                <Link href="/marketplace">
                  <Button icon={<ArrowRight size={14} />} onClick={() => setShowCapabilityMismatch(false)}>
                    Go to Marketplace
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

function ActivityItem({ log, isLast }: { log: any; isLast: boolean }) {
  const levelStyles: Record<string, { dot: string; text: string }> = {
    INFO: { dot: 'bg-accent', text: 'text-text-secondary' },
    WARN: { dot: 'bg-warning', text: 'text-warning' },
    ERROR: { dot: 'bg-error', text: 'text-error' },
    DEBUG: { dot: 'bg-text-tertiary/40', text: 'text-text-tertiary' },
    SUCCESS: { dot: 'bg-success', text: 'text-success' },
  };

  const typeLabels: Record<string, { icon: React.ReactNode; label: string }> = {
    SYSTEM: { icon: <Cpu size={11} />, label: 'System' },
    AGENT: { icon: <Terminal size={11} />, label: 'Agent' },
    LLM: { icon: <Cpu size={11} />, label: 'LLM' },
    OS_ACTION: { icon: <Monitor size={11} />, label: 'Action' },
    USER: { icon: <ChevronRight size={11} />, label: 'User' },
    SCREENSHOT: { icon: <Image size={11} />, label: 'Screenshot' },
  };

  const style = levelStyles[log.level] || levelStyles.INFO;
  const typeMeta = typeLabels[log.type] || typeLabels.SYSTEM;

  // Skip screenshot-type log entries entirely (visual noise)
  if (log.type === 'SCREENSHOT') return null;

  return (
    <div className="flex gap-3 group">
      {/* Timeline connector */}
      <div className="flex flex-col items-center pt-1.5">
        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${style.dot}`} />
        {!isLast && <div className="w-px flex-1 bg-border-primary mt-1" />}
      </div>

      {/* Content */}
      <div className="flex-1 pb-3 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-[10px] text-text-tertiary tabular-nums flex-shrink-0">
            {new Date(log.timestamp || log.createdAt).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
          <span className="flex items-center gap-1 text-[10px] text-text-tertiary px-1.5 py-0.5 rounded bg-bg-elevated border border-border-primary flex-shrink-0">
            {typeMeta.icon}
            {typeMeta.label}
          </span>
          {log.agentName && (
            <span className="text-[10px] text-text-tertiary flex-shrink-0">{log.agentName}</span>
          )}
        </div>
        <p className={`text-xs leading-relaxed break-words ${style.text}`}>
          {log.message}
        </p>
      </div>
    </div>
  );
}
