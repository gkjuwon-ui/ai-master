import { create } from 'zustand';
import { wsClient } from '../lib/websocket';
import { api } from '../lib/api';

interface IdleActivity {
  agentId: string;
  agentName: string;
  activity: string;   // browsing, thinking, voting, voted, commenting, commented, writing, posted, idle, error
  detail: string;
  timestamp: string;
}

interface IdleActivityLog extends IdleActivity {
  id: string; // unique log entry id
}

interface IdleActivityState {
  activities: Record<string, IdleActivity>;   // keyed by agentId (latest per agent)
  logs: IdleActivityLog[];                    // recent activity log (newest first)
  subscribe: () => () => void;
  loadHistory: () => Promise<void>;
}

const ACTIVITY_LABELS: Record<string, string> = {
  starting: 'Starting up...',
  loading: 'Loading agents...',
  ready: 'Ready',
  no_agents: 'No agents configured',
  monitoring: 'Monitoring...',
  browsing: 'Browsing community...',
  thinking: 'Thinking...',
  voting: 'Voting...',
  voted: 'Voted!',
  commenting: 'Writing comment...',
  commented: 'Commented!',
  writing: 'Writing post...',
  posted: 'Published!',
  reading: 'Reading knowledge feed...',
  idle: 'Idle',
  error: 'Error',
};

export function getActivityLabel(activity: string, detail?: string): string {
  if (detail) return detail;
  return ACTIVITY_LABELS[activity] || activity;
}

export function isActiveActivity(activity: string): boolean {
  return ['browsing', 'thinking', 'voting', 'commenting', 'writing', 'reading', 'starting', 'loading', 'monitoring'].includes(activity);
}

const STALE_MS = 5 * 60 * 1000; // 5 minutes
const MAX_LOGS = 50;

let _logCounter = 0;

export const useIdleActivityStore = create<IdleActivityState>((set, get) => ({
  activities: {},
  logs: [],

  subscribe: () => {
    const cleanup = wsClient.on('agent_idle_activity', (data: IdleActivity) => {
      if (!data?.agentId) return;
      const entry: IdleActivity = {
        agentId: data.agentId,
        agentName: data.agentName || 'Agent',
        activity: data.activity,
        detail: data.detail || '',
        timestamp: data.timestamp || new Date().toISOString(),
      };
      const logEntry: IdleActivityLog = {
        ...entry,
        id: `idle_${++_logCounter}_${Date.now()}`,
      };
      set((state) => ({
        activities: {
          ...state.activities,
          [data.agentId]: entry,
        },
        logs: [logEntry, ...state.logs].slice(0, MAX_LOGS),
      }));
    });

    // Periodic cleanup of stale per-agent entries
    const interval = setInterval(() => {
      set((state) => {
        const now = Date.now();
        const cleaned: Record<string, IdleActivity> = {};
        for (const [id, act] of Object.entries(state.activities)) {
          if (now - new Date(act.timestamp).getTime() < STALE_MS) {
            cleaned[id] = act;
          }
        }
        return { activities: cleaned };
      });
    }, 60_000);

    return () => {
      cleanup();
      clearInterval(interval);
    };
  },

  loadHistory: async () => {
    try {
      const res = await api.get('/api/community/idle-activity-history');
      const items: IdleActivity[] = res?.data ?? res ?? [];
      if (!Array.isArray(items) || items.length === 0) return;

      const existingIds = new Set(get().logs.map(l => l.timestamp));
      const newLogs: IdleActivityLog[] = [];
      const newActivities: Record<string, IdleActivity> = {};

      for (const item of items) {
        if (!item?.agentId || existingIds.has(item.timestamp)) continue;
        const entry: IdleActivity = {
          agentId: item.agentId,
          agentName: item.agentName || 'Agent',
          activity: item.activity,
          detail: item.detail || '',
          timestamp: item.timestamp || new Date().toISOString(),
        };
        newLogs.push({ ...entry, id: `hist_${++_logCounter}_${Date.now()}` });
        newActivities[item.agentId] = entry;
      }

      if (newLogs.length === 0) return;

      set((state) => ({
        activities: { ...newActivities, ...state.activities },
        logs: [...state.logs, ...newLogs]
          .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
          .slice(0, MAX_LOGS),
      }));
    } catch {}
  },
}));
