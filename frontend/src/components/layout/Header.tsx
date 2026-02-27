'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { api } from '@/lib/api';
import { Bell, User, LogOut, LogIn, Check, CheckCheck } from 'lucide-react';
import { useState, useRef, useEffect, useCallback } from 'react';
import { formatRelativeTime } from '@/lib/utils';

export function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isAuthenticated, logout } = useAuthStore();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isMobileView, setIsMobileView] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  // Define ALL functions BEFORE any early return to avoid TDZ issues
  const loadNotifications = useCallback(async () => {
    try {
      const res = await api.getNotifications();
      const data = res?.data || {};
      const items = Array.isArray(data.notifications) ? data.notifications : [];
      setNotifications(items);
      setUnreadCount(data.unreadCount ?? items.filter((n: any) => !n.read).length);
    } catch {
      // Silently fail - notifications are non-critical
    }
  }, []);

  const handleMarkRead = useCallback(async (id: string) => {
    try {
      await api.markNotificationRead(id);
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch {}
  }, []);

  const handleMarkAllRead = useCallback(async () => {
    try {
      await api.markAllNotificationsRead();
      setNotifications(prev => prev.map(n => ({ ...n, read: true })));
      setUnreadCount(0);
    } catch {}
  }, []);

  const getPageTitle = useCallback(() => {
    if (pathname === '/marketplace') return 'Marketplace';
    if (pathname === '/workspace') return 'Workspace';
    if (pathname === '/dashboard') return 'Dashboard';
    if (pathname === '/developer') return 'Developer Portal';
    if (pathname === '/settings') return 'Settings';
    if (pathname?.startsWith('/marketplace/')) return 'Agent Details';
    return 'ogenti';
  }, [pathname]);

  // Hydration-safe mobile detection (avoids SSR/CSR mismatch)
  useEffect(() => {
    const check = () => setIsMobileView(window.innerWidth < 768);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      loadNotifications();
      const interval = setInterval(loadNotifications, 30000);
      return () => clearInterval(interval);
    }
  }, [isAuthenticated, loadNotifications]);

  // Hide on auth pages (must be after all hooks AND all function definitions)
  if (pathname?.startsWith('/auth')) return null;

  return (
    <header className={`h-14 bg-bg-secondary border-b border-border-primary flex items-center justify-between ${isMobileView ? 'px-14' : 'px-6'}`}
      style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}
    >
      <h1 className="text-sm font-medium text-text-primary truncate">{getPageTitle()}</h1>

      <div className={`flex items-center gap-3 ${isMobileView ? '' : 'pr-36'}`}>
        {isAuthenticated ? (
          <>
            {/* Notifications */}
            <div className="relative" ref={notifRef}>
              <button
                onClick={() => setNotifOpen(!notifOpen)}
                className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors relative"
              >
                <Bell size={18} />
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-error text-[9px] font-bold text-white rounded-full flex items-center justify-center">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>

              {notifOpen && (
                <div className="absolute right-0 top-full mt-2 w-80 bg-bg-elevated border border-border-primary rounded-xl shadow-2xl z-50 animate-fade-in overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-3 border-b border-border-primary">
                    <span className="text-sm font-semibold">Notifications</span>
                    {unreadCount > 0 && (
                      <button
                        onClick={handleMarkAllRead}
                        className="text-[11px] text-accent hover:underline flex items-center gap-1"
                      >
                        <CheckCheck size={12} />
                        Mark all read
                      </button>
                    )}
                  </div>
                  <div className="max-h-80 overflow-y-auto">
                    {notifications.length === 0 ? (
                      <div className="py-8 text-center text-text-tertiary text-sm">
                        No notifications yet
                      </div>
                    ) : (
                      notifications.slice(0, 20).map((notif) => (
                        <button
                          key={notif.id}
                          onClick={() => !notif.read && handleMarkRead(notif.id)}
                          className={`w-full text-left px-4 py-3 border-b border-border-primary last:border-0 hover:bg-bg-hover transition-colors ${
                            !notif.read ? 'bg-bg-active/30' : ''
                          }`}
                        >
                          <div className="flex items-start gap-2">
                            {!notif.read && (
                              <span className="w-2 h-2 rounded-full bg-accent mt-1.5 flex-shrink-0" />
                            )}
                            <div className={!notif.read ? '' : 'ml-4'}>
                              <p className="text-sm font-medium text-text-primary">{notif.title}</p>
                              <p className="text-xs text-text-tertiary mt-0.5 line-clamp-2">{notif.message}</p>
                              <p className="text-[10px] text-text-tertiary mt-1">{formatRelativeTime(notif.createdAt)}</p>
                            </div>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                  <Link
                    href="/settings#notifications"
                    onClick={() => setNotifOpen(false)}
                    className="block text-center py-2 text-xs text-text-tertiary hover:text-text-primary border-t border-border-primary transition-colors"
                  >
                    Notification Settings
                  </Link>
                </div>
              )}
            </div>

            {/* User Menu */}
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-bg-elevated transition-colors"
              >
                <div className="w-7 h-7 bg-bg-elevated rounded-full flex items-center justify-center border border-border-primary">
                  <User size={14} className="text-text-secondary" />
                </div>
                <span className="text-sm text-text-secondary hidden md:inline">{user?.displayName}</span>
              </button>

              {userMenuOpen && (
                <div className="absolute right-0 top-full mt-2 w-48 bg-bg-elevated border border-border-primary rounded-xl shadow-2xl py-1 z-50 animate-fade-in">
                  <div className="px-4 py-2 border-b border-border-primary">
                    <p className="text-sm font-medium text-text-primary">{user?.displayName}</p>
                    <p className="text-xs text-text-tertiary">{user?.email}</p>
                  </div>
                  <Link
                    href="/dashboard"
                    className="flex items-center gap-2 px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
                    onClick={() => setUserMenuOpen(false)}
                  >
                    <User size={14} />
                    Dashboard
                  </Link>
                  <Link
                    href="/settings"
                    className="flex items-center gap-2 px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
                    onClick={() => setUserMenuOpen(false)}
                  >
                    Settings
                  </Link>
                  <button
                    onClick={async () => {
                      setUserMenuOpen(false);
                      await logout();
                      router.replace('/');
                    }}
                    className="flex items-center gap-2 w-full px-4 py-2 text-sm text-gray-400 hover:bg-black/5 transition-colors"
                  >
                    <LogOut size={14} />
                    Logout
                  </button>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex items-center gap-2">
            <Link href="/auth/login" className="btn-ghost text-sm flex items-center gap-2">
              <LogIn size={16} />
              Login
            </Link>
            <Link href="/auth/register" className="btn-primary text-sm">
              Sign Up
            </Link>
          </div>
        )}
      </div>
    </header>
  );
}
