/**
 * Credits Store — State management for Ogenti Credit System
 * 
 * Replaces subscription store. Manages credit balance, ledger, purchases.
 */

import { create } from 'zustand';
import { api } from '../lib/api';

interface CreditLedgerEntry {
  id: string;
  amount: number;
  reason: string;
  referenceId?: string;
  balance: number;
  createdAt: string;
}

interface CreditBreakdown {
  reason: string;
  total: number;
  count: number;
}

interface CreditsState {
  balance: number;
  totalEarned: number;
  totalSpent: number;
  recentTransactions: CreditLedgerEntry[];
  breakdown: CreditBreakdown[];
  isLoading: boolean;
  error: string | null;

  fetchBalance: () => Promise<void>;
  fetchSummary: () => Promise<void>;
  purchaseAgent: (agentId: string) => Promise<{ success: boolean; remaining: number }>;
}

export const useCreditsStore = create<CreditsState>((set) => ({
  balance: 0,
  totalEarned: 0,
  totalSpent: 0,
  recentTransactions: [],
  breakdown: [],
  isLoading: false,
  error: null,

  fetchBalance: async () => {
    try {
      const response = await api.credits.getBalance();
      const data = response?.data || response;
      set({ balance: data.balance ?? 0 });
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  fetchSummary: async () => {
    try {
      set({ isLoading: true, error: null });
      const response = await api.credits.getSummary();
      const data = response?.data || response;
      set({
        balance: data.balance ?? 0,
        totalEarned: data.totalEarned ?? 0,
        totalSpent: data.totalSpent ?? 0,
        recentTransactions: data.recentTransactions ?? [],
        breakdown: data.breakdown ?? [],
        isLoading: false,
      });
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
    }
  },

  purchaseAgent: async (agentId: string) => {
    try {
      set({ error: null });
      const response = await api.credits.purchase(agentId);
      const data = response?.data || response;
      set({ balance: data.remaining ?? 0 });
      return { success: true, remaining: data.remaining };
    } catch (error: any) {
      set({ error: error.message });
      throw error;
    }
  },
}));
