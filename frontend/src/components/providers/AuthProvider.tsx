'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { wsClient } from '@/lib/websocket';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { loadUser, isAuthenticated, logout } = useAuthStore();

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  // Listen for session-expired events from api.ts (instead of full page reload)
  useEffect(() => {
    const handleSessionExpired = () => {
      useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
      router.replace('/');
    };
    window.addEventListener('auth:session-expired', handleSessionExpired);
    return () => window.removeEventListener('auth:session-expired', handleSessionExpired);
  }, [router]);

  useEffect(() => {
    if (isAuthenticated) {
      const token = localStorage.getItem('accessToken');
      if (token) wsClient.connect(token);
    } else {
      wsClient.disconnect();
    }
    return () => wsClient.disconnect();
  }, [isAuthenticated]);

  return <>{children}</>;
}
