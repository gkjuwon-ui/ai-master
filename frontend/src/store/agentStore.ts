import { create } from 'zustand';
import { api } from '../lib/api';

interface Agent {
  id: string;
  name: string;
  slug: string;
  description: string;
  longDescription: string;
  category: string;
  tags: string[];
  capabilities: string[];
  tier?: string;
  price: number;
  pricingModel: string;
  icon?: string;
  thumbnailUrl?: string;
  screenshots: string[];
  developer: {
    id: string;
    username: string;
    displayName: string;
    name?: string;
    avatar?: string;
    verified: boolean;
    agentCount?: number;
  };
  stats: {
    downloads: number;
    rating: number;
    reviewCount: number;
  };
  rating?: number;
  reviewCount?: number;
  downloadCount?: number;
  verified?: boolean;
  version?: string;
  updatedAt?: string;
  status: string;
  createdAt: string;
}

interface AgentState {
  agents: Agent[];
  currentAgent: Agent | null;
  purchasedAgents: any[];
  total: number;
  totalAgents: number;
  isLoading: boolean;
  error: string | null;
  filters: {
    search: string;
    category: string;
    sortBy: string;
    page: number;
  };
  fetchAgents: (query?: Record<string, any>) => Promise<void>;
  fetchAgent: (id: string) => Promise<void>;
  fetchAgentBySlug: (slug: string) => Promise<void>;
  fetchPurchasedAgents: () => Promise<void>;
  setFilter: (key: string, value: any) => void;
  clearFilters: () => void;
}

export const useAgentStore = create<AgentState>((set, get) => ({
  agents: [],
  currentAgent: null,
  purchasedAgents: [],
  total: 0,
  totalAgents: 0,
  isLoading: false,
  error: null,
  filters: {
    search: '',
    category: '',
    sortBy: 'popular',
    page: 1,
  },

  fetchAgents: async (query) => {
    try {
      set({ isLoading: true, error: null });
      const { filters } = get();
      const params: Record<string, any> = query || {
        page: filters.page.toString(),
        limit: '20',
        sortBy: filters.sortBy,
      };
      if (!query) {
        if (filters.search) params.search = filters.search;
        if (filters.category) params.category = filters.category;
      }

      const response = await api.getAgents(params);
      const data = response?.data ?? response;
      set({
        agents: data.agents || [],
        total: data.total || 0,
        totalAgents: data.total || 0,
        isLoading: false,
      });
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
    }
  },

  fetchAgent: async (id) => {
    try {
      set({ isLoading: true, error: null });
      const response = await api.getAgent(id);
      set({ currentAgent: response?.data ?? response, isLoading: false });
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
    }
  },

  fetchAgentBySlug: async (slug) => {
    try {
      set({ isLoading: true, error: null });
      const response = await api.getAgentBySlug(slug);
      set({ currentAgent: response?.data ?? response, isLoading: false });
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
    }
  },

  fetchPurchasedAgents: async () => {
    try {
      const response = await api.getPurchasedAgents();
      const purchases = response?.data ?? response ?? [];
      // Extract agent objects from purchase records
      const agents = Array.isArray(purchases)
        ? purchases.map((p: any) => p.agent || p).filter(Boolean)
        : [];
      set({ purchasedAgents: agents });
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  setFilter: (key, value) => {
    set((state) => ({
      filters: { ...state.filters, [key]: value, ...(key !== 'page' ? { page: 1 } : {}) },
    }));
    get().fetchAgents();
  },

  clearFilters: () => {
    set({
      filters: { search: '', category: '', sortBy: 'popular', page: 1 },
    });
    get().fetchAgents();
  },
}));
