/**
 * Agent Management Store — Multi-Brain LLM Assignment
 * 
 * Manages per-agent LLM configuration for the multi-brain architecture.
 * Each agent can be assigned a different LLM (GPT-4, Claude, Gemini, etc.)
 * enabling genuine multi-AI collaboration instead of single-brain role-play.
 */

import { create } from 'zustand';
import { api } from '../lib/api';

export interface AgentLLMAssignment {
  agentId: string;
  agentName: string;
  agentSlug: string;
  agentCategory: string;
  llmConfigId: string | null;
  llmConfigName: string | null;
  llmProvider: string | null;
  llmModel: string | null;
}

export interface LLMConfigOption {
  id: string;
  name: string;
  provider: string;
  model: string;
}

interface AgentManagementState {
  // State
  assignments: AgentLLMAssignment[];
  purchasedAgents: any[];
  llmConfigs: LLMConfigOption[];
  isLoading: boolean;
  isSaving: Record<string, boolean>;  // per-agent save state
  error: string | null;
  lastSaved: string | null;

  // Persona state
  personas: Record<string, string>;          // agentId → persona text
  personaLoading: Record<string, boolean>;   // per-agent loading
  personaSaving: Record<string, boolean>;    // per-agent save state
  expandedPersona: string | null;            // which agent's persona editor is open

  // Actions
  fetchAll: () => Promise<void>;
  assignLLM: (agentId: string, llmConfigId: string | null) => Promise<void>;
  clearLLM: (agentId: string) => Promise<void>;
  getAssignment: (agentId: string) => AgentLLMAssignment | undefined;
  getMultiBrainStats: () => { total: number; assigned: number; providers: string[] };

  // Persona actions
  fetchPersona: (agentId: string) => Promise<void>;
  savePersona: (agentId: string, persona: string) => Promise<void>;
  setExpandedPersona: (agentId: string | null) => void;
  setLocalPersona: (agentId: string, text: string) => void;
}

export const useAgentManagementStore = create<AgentManagementState>((set, get) => ({
  assignments: [],
  purchasedAgents: [],
  llmConfigs: [],
  isLoading: false,
  isSaving: {},
  error: null,
  lastSaved: null,

  // Persona state
  personas: {},
  personaLoading: {},
  personaSaving: {},
  expandedPersona: null,

  fetchAll: async () => {
    try {
      set({ isLoading: true, error: null });

      // Fetch purchased agents, LLM configs, and current assignments in parallel
      const [purchasedRes, configsRes, assignmentsRes] = await Promise.all([
        api.getPurchasedAgents().catch(() => ({ data: [] })),
        api.getLLMConfigs().catch(() => ({ data: [] })),
        api.getAllLLMAssignments().catch(() => ({ data: [] })),
      ]);

      const rawPurchased = purchasedRes?.data ?? purchasedRes ?? [];
      const purchased = Array.isArray(rawPurchased)
        ? rawPurchased.map((p: any) => p.agent || p).filter(Boolean)
        : [];

      const rawConfigs = configsRes?.data ?? configsRes ?? [];
      const configs: LLMConfigOption[] = (Array.isArray(rawConfigs) ? rawConfigs : []).map((c: any) => ({
        id: c.id,
        name: c.name,
        provider: c.provider,
        model: c.model,
      }));

      const assignmentMap = new Map<string, any>();
      const rawAssignmentsArr = assignmentsRes?.data ?? assignmentsRes ?? [];
      const rawAssignments = Array.isArray(rawAssignmentsArr) ? rawAssignmentsArr : [];
      for (const a of rawAssignments) {
        assignmentMap.set(a.id, a);
      }

      // Build unified assignment list from purchased agents
      const assignments: AgentLLMAssignment[] = purchased.map((agent: any) => {
        const assigned = assignmentMap.get(agent.id);
        const llmConfig = assigned?.llmConfig || null;
        return {
          agentId: agent.id,
          agentName: agent.name || agent.slug || agent.id,
          agentSlug: agent.slug || '',
          agentCategory: agent.category || 'general',
          llmConfigId: llmConfig?.id || null,
          llmConfigName: llmConfig?.name || null,
          llmProvider: llmConfig?.provider || null,
          llmModel: llmConfig?.model || null,
        };
      });

      set({
        purchasedAgents: purchased,
        llmConfigs: configs,
        assignments,
        isLoading: false,
      });
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
    }
  },

  assignLLM: async (agentId: string, llmConfigId: string | null) => {
    try {
      set((s) => ({ isSaving: { ...s.isSaving, [agentId]: true }, error: null }));

      await api.assignAgentLLM(agentId, llmConfigId);

      // Update local state optimistically
      const { llmConfigs } = get();
      const config = llmConfigs.find((c) => c.id === llmConfigId) || null;

      set((s) => ({
        assignments: s.assignments.map((a) =>
          a.agentId === agentId
            ? {
                ...a,
                llmConfigId: config?.id || null,
                llmConfigName: config?.name || null,
                llmProvider: config?.provider || null,
                llmModel: config?.model || null,
              }
            : a
        ),
        isSaving: { ...s.isSaving, [agentId]: false },
        lastSaved: agentId,
      }));
    } catch (error: any) {
      set((s) => ({ error: error.message, isSaving: { ...s.isSaving, [agentId]: false } }));
      throw error;
    }
  },

  clearLLM: async (agentId: string) => {
    await get().assignLLM(agentId, null);
  },

  getAssignment: (agentId: string) => {
    return get().assignments.find((a) => a.agentId === agentId);
  },

  getMultiBrainStats: () => {
    const { assignments } = get();
    const assigned = assignments.filter((a) => a.llmConfigId !== null);
    const providers = [...new Set(assigned.map((a) => a.llmProvider).filter(Boolean))] as string[];
    return {
      total: assignments.length,
      assigned: assigned.length,
      providers,
    };
  },

  // ── Persona actions ──────────────────────────────────────────
  setExpandedPersona: (agentId: string | null) => {
    set({ expandedPersona: agentId });
    // Auto-fetch persona when expanding
    if (agentId && !(agentId in get().personas)) {
      get().fetchPersona(agentId);
    }
  },

  setLocalPersona: (agentId: string, text: string) => {
    set((s) => ({ personas: { ...s.personas, [agentId]: text } }));
  },

  fetchPersona: async (agentId: string) => {
    try {
      set((s) => ({ personaLoading: { ...s.personaLoading, [agentId]: true } }));
      const res = await api.getAgentPersona(agentId);
      set((s) => ({
        personas: { ...s.personas, [agentId]: (res as any)?.persona || '' },
        personaLoading: { ...s.personaLoading, [agentId]: false },
      }));
    } catch {
      set((s) => ({
        personas: { ...s.personas, [agentId]: '' },
        personaLoading: { ...s.personaLoading, [agentId]: false },
      }));
    }
  },

  savePersona: async (agentId: string, persona: string) => {
    try {
      set((s) => ({ personaSaving: { ...s.personaSaving, [agentId]: true } }));
      await api.saveAgentPersona(agentId, persona);
      set((s) => ({
        personas: { ...s.personas, [agentId]: persona },
        personaSaving: { ...s.personaSaving, [agentId]: false },
      }));
    } catch (error: any) {
      set((s) => ({ personaSaving: { ...s.personaSaving, [agentId]: false } }));
      throw error;
    }
  },
}));
