import { create } from 'zustand';
import { api } from '../lib/api';

interface LLMConfig {
  id: string;
  name: string;
  provider: string;
  model: string;
  apiKey: string;
  baseUrl?: string;
  isDefault: boolean;
}

interface Provider {
  id: string;
  name: string;
  models: { id: string; name: string; contextWindow: number }[];
}

interface SettingsState {
  settings: any;
  llmConfigs: LLMConfig[];
  providers: Provider[];
  isLoading: boolean;
  error: string | null;
  fetchSettings: () => Promise<void>;
  updateSettings: (data: any) => Promise<void>;
  fetchLLMConfigs: () => Promise<void>;
  fetchProviders: () => Promise<void>;
  createLLMConfig: (data: any) => Promise<void>;
  updateLLMConfig: (id: string, data: any) => Promise<void>;
  saveLLMConfig: (data: any) => Promise<void>;
  deleteLLMConfig: (id: string) => Promise<void>;
  testLLMConfig: (id: string) => Promise<any>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  settings: null,
  llmConfigs: [],
  providers: [],
  isLoading: false,
  error: null,

  fetchSettings: async () => {
    try {
      const response = await api.getSettings();
      set({ settings: response?.data ?? response });
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  updateSettings: async (data) => {
    try {
      const response = await api.updateSettings(data);
      set({ settings: response?.data ?? response });
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  fetchLLMConfigs: async () => {
    try {
      set({ isLoading: true });
      const response = await api.getLLMConfigs();
      const configs = response?.data ?? response ?? [];
      set({ llmConfigs: Array.isArray(configs) ? configs : [], isLoading: false });
    } catch (error: any) {
      set({ error: error.message, isLoading: false, llmConfigs: [] });
    }
  },

  fetchProviders: async () => {
    try {
      const response = await api.getLLMProviders();
      set({ providers: response?.data ?? response });
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  createLLMConfig: async (data) => {
    try {
      await api.createLLMConfig(data);
      await get().fetchLLMConfigs();
    } catch (error: any) {
      set({ error: error.message });
      throw error;
    }
  },

  updateLLMConfig: async (id, data) => {
    try {
      await api.updateLLMConfig(id, data);
      await get().fetchLLMConfigs();
    } catch (error: any) {
      set({ error: error.message });
      throw error;
    }
  },

  saveLLMConfig: async (data) => {
    try {
      if (data.id) {
        await api.updateLLMConfig(data.id, data);
      } else {
        await api.createLLMConfig(data);
      }
      await get().fetchLLMConfigs();
    } catch (error: any) {
      set({ error: error.message });
      throw error;
    }
  },

  deleteLLMConfig: async (id) => {
    try {
      await api.deleteLLMConfig(id);
      set((state) => ({ llmConfigs: state.llmConfigs.filter((c) => c.id !== id) }));
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  testLLMConfig: async (id) => {
    try {
      const response = await api.testLLMConfig(id);
      return response?.data ?? response;
    } catch (error: any) {
      set({ error: error.message });
      throw error;
    }
  },
}));
