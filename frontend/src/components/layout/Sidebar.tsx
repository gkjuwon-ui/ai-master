'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import {
  Store,
  Play,
  Settings,
  LayoutDashboard,
  Code2,
  ChevronLeft,
  ChevronRight,
  Users,
  Coins,
  ArrowRightLeft,
  CreditCard,
  Heart,
  Vote,
  MessageCircle,
  Menu,
  X,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { useAuthStore } from '@/store/authStore';

const navigation = [
  { name: 'Marketplace', href: '/marketplace', icon: Store },
  { name: 'Community', href: '/community', icon: Users },
  { name: 'Election', href: '/election', icon: Vote },
  { name: 'Social', href: '/social', icon: Heart },
  { name: 'Chat', href: '/chat', icon: MessageCircle },
  { name: 'Workspace', href: '/workspace', icon: Play },
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Credits', href: '/credits', icon: Coins },
  { name: 'Exchange', href: '/exchange', icon: ArrowRightLeft },
  { name: 'Subscription', href: '/subscription', icon: CreditCard },
  { name: 'Developer', href: '/developer', icon: Code2 },
  { name: 'Settings', href: '/settings', icon: Settings },
];

/** Detect mobile viewport (< 768px) */
function useIsMobile() {
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    const check = () => setMobile(window.innerWidth < 768);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);
  return mobile;
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();
  const { isAuthenticated, user } = useAuthStore();
  const isMobile = useIsMobile();

  // Close mobile menu on navigation
  // NOTE: must be BEFORE any early return to satisfy Rules of Hooks
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Hide sidebar on auth pages (after all hooks)
  if (pathname?.startsWith('/auth')) return null;

  const filteredNav = navigation.filter((item) => {
    if (item.href === '/developer' && user?.role !== 'DEVELOPER' && user?.role !== 'ADMIN') return false;
    if (['/dashboard', '/workspace', '/settings', '/developer', '/credits', '/exchange', '/subscription', '/social', '/chat'].includes(item.href) && !isAuthenticated) return false;
    return true;
  });

  // --- MOBILE: hamburger menu + overlay drawer ---
  if (isMobile) {
    return (
      <>
        {/* Hamburger button ??fixed top-left */}
        <button
          onClick={() => setMobileOpen(true)}
          className="fixed top-3 left-3 z-50 p-2 rounded-lg bg-bg-secondary border border-border-primary text-text-secondary hover:text-text-primary"
          aria-label="Open menu"
        >
          <Menu size={20} />
        </button>

        {/* Overlay backdrop */}
        {mobileOpen && (
          <div
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
        )}

        {/* Slide-in drawer */}
        <aside
          className={cn(
            'fixed top-0 left-0 z-50 h-screen w-64 bg-bg-secondary border-r border-border-primary flex flex-col transition-transform duration-200',
            mobileOpen ? 'translate-x-0' : '-translate-x-full'
          )}
        >
          {/* Header with close */}
          <div className="h-14 flex items-center justify-between px-4 border-b border-border-primary">
            <Link href="/" className="flex items-center gap-2 outline-none" onClick={() => setMobileOpen(false)}>
              <img src="/favicon.ico?v=app" alt="ogenti app logo" width={28} height={28} className="rounded-md block" />
              <span className="font-semibold text-sm text-text-primary tracking-tight">ogenti</span>
            </Link>
            <button onClick={() => setMobileOpen(false)} className="p-1 text-text-tertiary hover:text-text-primary">
              <X size={20} />
            </button>
          </div>

          {/* Nav items */}
          <nav className="flex-1 py-3 px-2 overflow-y-auto">
            <ul className="space-y-1">
              {filteredNav.map((item) => {
                const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');
                return (
                  <li key={item.name}>
                    <Link
                      href={item.href}
                      onClick={() => setMobileOpen(false)}
                      className={cn(
                        'flex items-center gap-3 px-3 py-3 rounded-lg text-sm transition-all duration-150',
                        isActive
                          ? 'text-white font-medium'
                          : 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated'
                      )}
                      style={isActive ? { background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)' } : undefined}
                    >
                      <item.icon size={18} />
                      <span>{item.name}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </aside>
      </>
    );
  }

  // --- DESKTOP: original sidebar ---
  return (
    <aside
      className={cn(
        'h-screen bg-bg-secondary border-r border-border-primary flex flex-col transition-all duration-200',
        collapsed ? 'w-16' : 'w-56'
      )}
    >
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-border-primary">
        <Link href="/" data-tour="logo" className="flex items-center gap-2 outline-none focus:outline-none focus-visible:outline-none">
          <img src="/favicon.ico?v=app" alt="ogenti app logo" width={32} height={32} className="rounded-md block" />
          {!collapsed && (
            <span className="font-semibold text-sm text-text-primary tracking-tight">ogenti</span>
          )}
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-2">
        <ul className="space-y-1">
          {filteredNav.map((item) => {
            const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');
            return (
              <li key={item.name}>
                <Link
                  href={item.href}
                  data-tour={item.href.replace('/', '')}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150 outline-none focus:outline-none focus-visible:outline-none',
                    isActive
                      ? 'text-white font-medium'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated'
                  )}
                  style={isActive ? { background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)' } : undefined}
                  title={collapsed ? item.name : undefined}
                >
                  <item.icon size={18} />
                  {!collapsed && <span>{item.name}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Collapse toggle */}
      <div className="p-2 border-t border-border-primary">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center py-2 rounded-lg text-text-tertiary hover:text-text-secondary hover:bg-bg-elevated transition-colors"
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
    </aside>
  );
}
