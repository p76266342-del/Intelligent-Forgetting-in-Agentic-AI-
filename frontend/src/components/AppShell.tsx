'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { api } from '@/lib/api';
import {
  Brain,
  MessageSquare,
  Layers,
  Activity,
  Settings,
  ShieldCheck,
  LogOut,
  Menu,
  X,
  ChevronDown,
} from 'lucide-react';

interface AppShellProps {
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const pathname = usePathname();
  const router = useRouter();
  const { profile, logout } = useAuth();
  
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);

  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mounted = true;
    api.getHealth()
      .then(() => {
        if (mounted) setBackendHealthy(true);
      })
      .catch(() => {
        if (mounted) setBackendHealthy(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  // Close mobile sidebar on route change
  useEffect(() => {
    setMobileSidebarOpen(false);
    setUserDropdownOpen(false);
  }, [pathname]);

  // Click outside listener for dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setUserDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // For unauthenticated standalone pages (/login, /signup), render children cleanly without workspace shell
  const isAuthPage = pathname === '/login' || pathname === '/signup';
  if (isAuthPage) {
    return (
      <div className="h-screen h-[100dvh] w-screen overflow-y-auto bg-slate-50 flex flex-col justify-center items-center">
        {children}
      </div>
    );
  }

  const navItems = [
    { href: '/chat', label: 'Chat', icon: MessageSquare },
    { href: '/memories', label: 'Memory Explorer', icon: Layers },
    { href: '/lifecycle', label: 'Lifecycle Activity', icon: Activity },
    { href: '/settings', label: 'Settings', icon: Settings },
    ...(profile?.role === 'admin'
      ? [{ href: '/admin', label: 'Admin Console', icon: ShieldCheck }]
      : []),
  ];

  // Derive current page title
  const getPageInfo = () => {
    if (pathname.startsWith('/chat')) return { title: 'Chat Workspace', subtitle: 'Interactive agent conversation with semantic memory recall' };
    if (pathname.startsWith('/memories')) return { title: 'Memory Explorer', subtitle: 'Search, filter, and inspect cognitive retention scores' };
    if (pathname.startsWith('/lifecycle')) return { title: 'Lifecycle Activity & Decisions', subtitle: 'Verified audit timeline and cognitive pruning recommendations' };
    if (pathname.startsWith('/settings')) return { title: 'Settings', subtitle: 'Manage your profile and data privacy controls' };
    if (pathname.startsWith('/admin')) return { title: 'Admin Console', subtitle: 'System health, tenant oversight, and reinforcement learning telemetry' };
    if (pathname === '/') return { title: 'Overview', subtitle: 'Cognitive retention and pruning platform' };
    return { title: 'Workspace', subtitle: 'Intelligent Forgetting Platform' };
  };

  const pageInfo = getPageInfo();

  const handleLogout = async () => {
    await logout();
    router.push('/login');
  };

  // User initials
  const initials = profile?.display_name
    ? profile.display_name.slice(0, 2).toUpperCase()
    : profile?.email
    ? profile.email.slice(0, 2).toUpperCase()
    : 'U';

  return (
    <div className="h-screen h-[100dvh] w-screen overflow-hidden bg-slate-50 text-slate-900 flex flex-row font-sans antialiased">
      
      {/* Mobile Sidebar Backdrop */}
      {mobileSidebarOpen && (
        <div
          onClick={() => setMobileSidebarOpen(false)}
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-40 lg:hidden transition-opacity"
          aria-hidden="true"
        />
      )}

      {/* Left Sidebar: strictly fixed height and non-scrolling except navigation items */}
      <aside
        className={`
          fixed lg:static inset-y-0 left-0 z-50
          w-64 h-full shrink-0 bg-white border-r border-slate-200
          flex flex-col justify-between overflow-hidden
          transition-transform duration-200 ease-in-out
          ${mobileSidebarOpen ? 'translate-x-0 shadow-xl' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        {/* Brand Logo Area (Sole location for application branding) */}
        <div className="p-4 border-b border-slate-100 flex items-center justify-between shrink-0">
          <Link href="/chat" className="flex items-center gap-3 group">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-sm transition-transform group-hover:scale-105">
              <Brain className="w-4 h-4" />
            </div>
            <div className="flex flex-col">
              <span className="font-semibold text-sm tracking-tight text-slate-900">
                Agentic Memory
              </span>
              <span className="text-[10px] text-indigo-600 font-medium tracking-wide">
                Intelligent Forgetting
              </span>
            </div>
          </Link>

          <button
            onClick={() => setMobileSidebarOpen(false)}
            className="lg:hidden p-1.5 text-slate-400 hover:text-slate-600 rounded-md hover:bg-slate-100"
            aria-label="Close navigation sidebar"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Navigation Links List */}
        <nav className="flex-1 min-h-0 px-3 py-4 space-y-1 overflow-y-auto">
          <div className="px-3 pb-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
            Workspace
          </div>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`
                  flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-colors
                  ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-700 font-semibold border-l-2 border-indigo-600'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/80'
                  }
                `}
              >
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-indigo-600' : 'text-slate-400'}`} />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Bottom System & Profile Card */}
        <div className="p-3 border-t border-slate-100 space-y-2 bg-slate-50/50 shrink-0">
          {/* System Health Indicator */}
          <div className="px-3 py-1.5 rounded-md bg-white border border-slate-200/80 flex items-center justify-between text-[11px]">
            <span className="text-slate-500 font-medium">Engine Status</span>
            <div className="flex items-center gap-1.5 font-medium">
              <span
                className={`w-2 h-2 rounded-full ${
                  backendHealthy === true
                    ? 'bg-emerald-500 ring-2 ring-emerald-100'
                    : backendHealthy === false
                    ? 'bg-rose-500 ring-2 ring-rose-100'
                    : 'bg-amber-400 animate-pulse'
                }`}
              />
              <span className={backendHealthy ? 'text-emerald-700' : 'text-slate-500'}>
                {backendHealthy === true ? 'Ready' : backendHealthy === false ? 'Offline' : 'Connecting'}
              </span>
            </div>
          </div>

          {/* Quick Profile Summary */}
          {profile ? (
            <div className="flex items-center gap-2.5 p-2 rounded-lg bg-white border border-slate-200/80">
              <div className="w-7 h-7 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-xs shrink-0">
                {initials}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold text-slate-800 truncate">
                  {profile.display_name || profile.email || 'User'}
                </div>
                <div className="text-[10px] text-slate-400 capitalize">
                  {profile.role || 'Member'}
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded"
                title="Sign out"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="w-full flex items-center justify-center gap-2 py-1.5 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-all"
            >
              Sign In
            </Link>
          )}
        </div>
      </aside>

      {/* Main Content Column */}
      <div className="flex-1 flex flex-col h-full min-w-0 overflow-hidden">
        
        {/* Global Compact Header: strictly fixed at top, never moves */}
        <header className="h-14 shrink-0 bg-white border-b border-slate-200 px-4 sm:px-6 flex items-center justify-between z-30">
          {/* Left: Mobile Toggle & Page Info */}
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setMobileSidebarOpen(true)}
              className="lg:hidden p-1.5 rounded-md text-slate-500 hover:text-slate-700 hover:bg-slate-100"
              aria-label="Open navigation sidebar"
            >
              <Menu className="w-5 h-5" />
            </button>

            <div className="flex flex-col min-w-0">
              <h1 className="text-sm sm:text-base font-semibold text-slate-900 tracking-tight truncate">
                {pageInfo.title}
              </h1>
              <p className="text-[11px] text-slate-500 hidden sm:block truncate">
                {pageInfo.subtitle}
              </p>
            </div>
          </div>

          {/* Right: Authenticated User Menu & Actions */}
          <div className="flex items-center gap-2 sm:gap-3">
            {profile ? (
              <div className="relative" ref={dropdownRef}>
                <button
                  onClick={() => setUserDropdownOpen(!userDropdownOpen)}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-slate-200 hover:border-slate-300 bg-white hover:bg-slate-50 transition-colors"
                >
                  <div className="w-6 h-6 rounded-full bg-indigo-600 text-white font-medium text-[11px] flex items-center justify-center">
                    {initials}
                  </div>
                  <span className="text-xs font-medium text-slate-700 hidden sm:inline max-w-[120px] truncate">
                    {profile.display_name || profile.email}
                  </span>
                  <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 hidden md:inline">
                    {profile.role}
                  </span>
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                </button>

                {/* Dropdown Menu */}
                {userDropdownOpen && (
                  <div className="absolute right-0 mt-1.5 w-56 bg-white border border-slate-200 rounded-xl shadow-lg p-1.5 z-50 text-xs animate-in fade-in slide-in-from-top-1 duration-150">
                    <div className="px-3 py-2 border-b border-slate-100 mb-1">
                      <p className="font-semibold text-slate-900 truncate">
                        {profile.display_name || 'Signed In User'}
                      </p>
                      <p className="text-slate-500 text-[11px] truncate">
                        {profile.email}
                      </p>
                    </div>

                    <Link
                      href="/settings"
                      onClick={() => setUserDropdownOpen(false)}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg text-slate-700 hover:bg-slate-100 transition-colors"
                    >
                      <Settings className="w-3.5 h-3.5 text-slate-400" />
                      <span>Account Settings</span>
                    </Link>

                    {profile.role === 'admin' && (
                      <Link
                        href="/admin"
                        onClick={() => setUserDropdownOpen(false)}
                        className="flex items-center gap-2 px-3 py-2 rounded-lg text-slate-700 hover:bg-slate-100 transition-colors"
                      >
                        <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
                        <span>Admin Console</span>
                      </Link>
                    )}

                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-rose-600 hover:bg-rose-50 transition-colors text-left"
                    >
                      <LogOut className="w-3.5 h-3.5" />
                      <span>Sign Out</span>
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Link
                  href="/login"
                  className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Sign In
                </Link>
                <Link
                  href="/signup"
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm"
                >
                  Get Started
                </Link>
              </div>
            )}
          </div>
        </header>

        {/* Page Content Container: Constrained to viewport, overflow-hidden so child views manage their scrolling */}
        <main className="flex-1 min-h-0 overflow-hidden flex flex-col relative">
          {children}
        </main>
      </div>
    </div>
  );
};
