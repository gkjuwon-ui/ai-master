import { create } from 'zustand';
import { api } from '../lib/api';

interface User {
  id: string;
  email: string;
  username: string;
  displayName: string;
  avatar?: string;
  role: string;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  pendingVerificationEmail: string | null;
  pendingVerificationCode: string | null; // For display when SMTP not configured
  login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; username: string; password: string; displayName: string }) => Promise<void>;
  verifyEmail: (email: string, code: string) => Promise<void>;
  resendVerification: (email: string) => Promise<string | null>;
  logout: () => Promise<void>;
  loadUser: () => Promise<void>;
  clearError: () => void;
  clearPendingVerification: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,
  pendingVerificationEmail: null,
  pendingVerificationCode: null,

  login: async (email, password) => {
    try {
      set({ isLoading: true, error: null });
      const response = await api.login(email, password);
      const data = response?.data || response;
      const user = data?.user;
      const tokens = data?.tokens;
      if (!user || !tokens?.accessToken) {
        throw new Error('Invalid response from server');
      }
      localStorage.setItem('accessToken', tokens.accessToken);
      localStorage.setItem('refreshToken', tokens.refreshToken);
      set({ user, isAuthenticated: true, isLoading: false });
    } catch (error: any) {
      // Handle EMAIL_NOT_VERIFIED: redirect to verify-email page
      if (error.code === 'EMAIL_NOT_VERIFIED' || error.message?.includes('not verified')) {
        // Try to extract data from the error response
        const errData = error.responseData?.data || {};
        set({
          isLoading: false,
          pendingVerificationEmail: errData.email || email,
          pendingVerificationCode: null,
        });
        throw error;
      }
      set({ error: error.message, isLoading: false });
      throw error;
    }
  },

  register: async (data) => {
    try {
      set({ isLoading: true, error: null });
      const response = await api.register(data);
      const respData = response?.data || response;

      // Desktop mode: server auto-verified and returned user+tokens directly
      if (respData?.autoVerified && respData?.user && respData?.tokens) {
        localStorage.setItem('accessToken', respData.tokens.accessToken);
        localStorage.setItem('refreshToken', respData.tokens.refreshToken);
        set({ user: respData.user, isAuthenticated: true, isLoading: false });
        return;
      }

      // Cloud mode: server returns requiresVerification — go to verification page
      if (respData?.requiresVerification) {
        set({
          isLoading: false,
          pendingVerificationEmail: respData.email || data.email,
          pendingVerificationCode: null,
        });
        return;
      }

      // Fallback: if server returns user+tokens directly (backward compat)
      const user = respData?.user;
      const tokens = respData?.tokens;
      if (user && tokens?.accessToken) {
        localStorage.setItem('accessToken', tokens.accessToken);
        localStorage.setItem('refreshToken', tokens.refreshToken);
        set({ user, isAuthenticated: true, isLoading: false });
      }
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
      throw error;
    }
  },

  verifyEmail: async (email, code) => {
    try {
      set({ isLoading: true, error: null });
      const response = await api.verifyEmail(email, code);
      const respData = response?.data || response;
      const user = respData?.user;
      const tokens = respData?.tokens;
      if (!user || !tokens?.accessToken) {
        throw new Error('Verification failed');
      }
      localStorage.setItem('accessToken', tokens.accessToken);
      localStorage.setItem('refreshToken', tokens.refreshToken);
      set({ user, isAuthenticated: true, isLoading: false, pendingVerificationEmail: null });
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
      throw error;
    }
  },

  resendVerification: async (email) => {
    try {
      const response = await api.resendVerification(email);
      const respData = response?.data || response;
      const code = respData?.verificationCode || null;
      if (code) {
        set({ pendingVerificationCode: code });
      }
      return code;
    } catch (error: any) {
      throw error;
    }
  },

  logout: async () => {
    try {
      await api.logout();
    } catch {
      // Ignore logout errors
    }
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
    set({ user: null, isAuthenticated: false });
  },

  loadUser: async () => {
    const token = localStorage.getItem('accessToken');
    if (!token) {
      set({ isLoading: false });
      return;
    }
    try {
      const response = await api.getMe();
      const user = response?.data || response;
      if (user?.id) {
        set({ user, isAuthenticated: true, isLoading: false });
      } else {
        throw new Error('Invalid user data');
      }
    } catch {
      localStorage.removeItem('accessToken');
      localStorage.removeItem('refreshToken');
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },

  clearError: () => set({ error: null }),

  clearPendingVerification: () => set({ pendingVerificationEmail: null, pendingVerificationCode: null }),
}));
