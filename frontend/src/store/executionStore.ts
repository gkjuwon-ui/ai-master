import { create } from 'zustand';
import { api } from '../lib/api';
import { wsClient } from '../lib/websocket';

interface ExecutionAgent {
  agentId: string;
  name: string;
  icon: string;
  order: number;
  status: string;
}

interface ExecutionLog {
  id: string;
  agentId: string;
  level: string;
  type: string;
  message: string;
  data?: any;
  screenshot?: string;
  createdAt: string;
}

interface ExecutionSession {
  id: string;
  name: string;
  prompt: string;
  status: string;
  agents: ExecutionAgent[];
  config: any;
  logs: ExecutionLog[];
  result?: any;
  startedAt?: string;
  completedAt?: string;
  createdAt: string;
}

interface ExecutionState {
  sessions: ExecutionSession[];
  currentSession: ExecutionSession | null;
  logs: ExecutionLog[];
  screenshot: string | null;
  isLoading: boolean;
  isExecuting: boolean;
  error: string | null;
  selectedAgentIds: string[];

  createSession: (data: any) => Promise<ExecutionSession>;
  fetchSessions: () => Promise<void>;
  fetchSession: (id: string) => Promise<void>;
  loadSession: (id: string) => Promise<void>;
  startExecution: (id: string) => Promise<void>;
  pauseExecution: (id: string) => Promise<void>;
  cancelExecution: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  setSelectedAgents: (ids: string[]) => void;
  toggleAgent: (id: string) => void;
  addLog: (log: ExecutionLog) => void;
  updateSessionStatus: (status: string) => void;
  updateScreenshot: (screenshot: string) => void;
  subscribeToSession: (id: string) => void;
  unsubscribeFromSession: (id: string) => void;
}

export const useExecutionStore = create<ExecutionState>((set, get) => ({
  sessions: [],
  currentSession: null,
  logs: [],
  screenshot: null,
  isLoading: false,
  isExecuting: false,
  error: null,
  selectedAgentIds: [],

  createSession: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.createExecution(data);
      const session = response?.data ?? response;
      set((state) => ({
        sessions: [session, ...state.sessions],
        currentSession: session,
        isLoading: false,
      }));
      return session;
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
      throw error;
    }
  },

  fetchSessions: async () => {
    set({ isLoading: true });
    try {
      const response = await api.getExecutions();
      const rd = response?.data ?? response;
      const sessions = rd?.sessions ?? (Array.isArray(rd) ? rd : []);
      const sessionList = Array.isArray(sessions) ? sessions : [];
      set({ sessions: sessionList, isLoading: false });

      // Auto-detect a running session and restore execution state
      const running = sessionList.find((s: any) => s.status === 'RUNNING');
      if (running && !get().isExecuting) {
        get().loadSession(running.id);
      }
    } catch (error: any) {
      set({ error: error.message, isLoading: false, sessions: [] });
    }
  },

  fetchSession: async (id) => {
    set({ isLoading: true });
    try {
      const response = await api.getExecution(id);
      const s = response?.data ?? response;
      set({
        currentSession: s,
        logs: s?.logs || [],
        screenshot: null,
        isLoading: false,
        isExecuting: s?.status === 'RUNNING',
      });
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
    }
  },

  loadSession: async (id) => {
    set({ isLoading: true, screenshot: null });
    try {
      const response = await api.getExecution(id);
      const s = response?.data ?? response;
      set({
        currentSession: s,
        logs: s?.logs || [],
        isLoading: false,
        isExecuting: s?.status === 'RUNNING',
      });
      if (s?.status === 'RUNNING') {
        get().subscribeToSession(id);
      }
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
    }
  },

  startExecution: async (id) => {
    try {
      await api.startExecution(id);
      set({ isExecuting: true });
      get().subscribeToSession(id);
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  pauseExecution: async (id) => {
    try {
      await api.pauseExecution(id);
      set({ isExecuting: false });
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  cancelExecution: async (id) => {
    try {
      await api.cancelExecution(id);
      set({ isExecuting: false });
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  deleteSession: async (id) => {
    try {
      await api.deleteExecution(id);
      set((state) => ({
        sessions: state.sessions.filter((s) => s.id !== id),
        currentSession: state.currentSession?.id === id ? null : state.currentSession,
      }));
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  setSelectedAgents: (ids) => set({ selectedAgentIds: ids }),

  toggleAgent: (id) => {
    set((state) => {
      const exists = state.selectedAgentIds.includes(id);
      return {
        selectedAgentIds: exists
          ? state.selectedAgentIds.filter((i) => i !== id)
          : [...state.selectedAgentIds, id],
      };
    });
  },

  addLog: (log) => {
    set((state) => ({
      logs: [...state.logs, log],
    }));
  },

  updateSessionStatus: (status) => {
    set((state) => ({
      currentSession: state.currentSession
        ? { ...state.currentSession, status }
        : null,
      isExecuting: status === 'RUNNING',
    }));
  },

  updateScreenshot: (screenshot) => {
    set({ screenshot });
  },

  subscribeToSession: (id) => {
    // D16 fix: Remove old listeners before adding new ones to prevent duplicate handlers.
    // Each call to wsClient.on() creates a new closure, so Set<EventHandler> can't deduplicate.
    const state = get() as any;
    if (state._wsCleanups) {
      state._wsCleanups.forEach((fn: () => void) => fn());
    }

    wsClient.subscribeSession(id);

    const cleanups: (() => void)[] = [];

    cleanups.push(wsClient.on('execution_log', (data) => {
      get().addLog(data);
    }));

    cleanups.push(wsClient.on('execution_status', (data) => {
      get().updateSessionStatus(data.status);
    }));

    cleanups.push(wsClient.on('execution_screenshot', (data) => {
      get().updateScreenshot(data.screenshot);
      get().addLog({
        id: Date.now().toString(),
        agentId: data.agentId,
        level: 'INFO',
        type: 'SCREENSHOT',
        message: 'Screenshot captured',
        screenshot: data.screenshot,
        createdAt: new Date().toISOString(),
      });
    }));

    cleanups.push(wsClient.on('execution_completed', (data) => {
      set({
        isExecuting: false,
        currentSession: get().currentSession
          ? { ...get().currentSession!, status: 'COMPLETED', result: data.result }
          : null,
      });
    }));

    cleanups.push(wsClient.on('execution_error', (data) => {
      set({
        isExecuting: false,
        error: data.message,
        currentSession: get().currentSession
          ? { ...get().currentSession!, status: 'FAILED' }
          : null,
      });
    }));

    // Store cleanups for next call or unsubscribe
    set({ _wsCleanups: cleanups } as any);
  },

  unsubscribeFromSession: (id) => {
    const state = get() as any;
    if (state._wsCleanups) {
      state._wsCleanups.forEach((fn: () => void) => fn());
      set({ _wsCleanups: null } as any);
    }
    wsClient.unsubscribeSession(id);
  },
}));
