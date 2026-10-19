'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { api } from '@/lib/api';
import {
  Brain,
  MessageSquare,
  Sparkles,
  Settings,
  ShieldCheck,
  LogOut,
  LogIn,
  Activity,
  Menu,
  X,
} from 'lucide-react';

export const Navbar: React.FC = () => {
  const pathname = usePathname();
  const { profile, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isBackendHealthy, setIsBackendHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;
    api.getHealth()
      .then(() => {
        if (mounted) setIsBackendHealthy(true);
      })
      .catch(() => {
        if (mounted) setIsBackendHealthy(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const navLinks = [
    { href: '/chat', label: 'Chat', icon: MessageSquare, authRequired: true },
    { href: '/memories', label: 'Memories & Lifecycle', icon: Sparkles, authRequired: true },
    { href: '/settings', label: 'Settings', icon: Settings, authRequired: true },
    ...(profile?.role === 'admin'
      ? [{ href: '/admin', label: 'Admin', icon: ShieldCheck, authRequired: true }]
      : []),
  ];

  return (
    <nav className="glass-nav sticky top-0 z-50 px-4 sm:px-6 py-3 border-b border-white/10">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-indigo-500/20 group-hover:scale-105 transition-transform">
            <Brain className="w-5 h-5 text-white" />
          </div>
          <div className="flex flex-col">
            <span className="font-semibold text-sm sm:text-base tracking-tight text-white flex items-center gap-1.5">
              Intelligent Forgetting
              <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                Agentic AI
              </span>
            </span>
            <span className="text-[11px] text-slate-400 hidden sm:inline">
              Cognitive Retention & Pruning Platform
            </span>
          </div>
        </Link>

        {/* Desktop Navigation Links */}
        <div className="hidden md:flex items-center gap-1 bg-slate-900/60 p-1 rounded-xl border border-white/5">
          {profile &&
            navLinks.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    isActive
                      ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                      : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {item.label}
                </Link>
              );
            })}
        </div>

        {/* Right Status & User controls */}
        <div className="hidden md:flex items-center gap-3">
          {/* Health indicator */}
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] border bg-slate-900/70 border-white/10"
            title={
              isBackendHealthy === null
                ? 'Connecting to FastAPI...'
                : isBackendHealthy
                ? 'FastAPI Backend Live'
                : 'Backend Unreachable'
            }
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isBackendHealthy === null
                  ? 'bg-amber-400 animate-pulse'
                  : isBackendHealthy
                  ? 'bg-emerald-400'
                  : 'bg-rose-400'
              }`}
            />
            <Activity className="w-3 h-3 text-slate-400" />
            <span className="text-slate-400 font-mono">
              {isBackendHealthy ? 'API Active' : 'API Connecting'}
            </span>
          </div>

          {profile ? (
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-slate-800/60 border border-white/5 text-xs text-slate-200">
                <span className="w-2 h-2 rounded-full bg-indigo-400" />
                <span className="font-medium truncate max-w-[120px]">
                  {profile.display_name || profile.email?.split('@')[0] || 'User'}
                </span>
                {profile.role === 'admin' && (
                  <span className="text-[10px] font-bold text-amber-300 bg-amber-500/20 px-1 py-0.2 rounded border border-amber-500/30">
                    Admin
                  </span>
                )}
              </div>
              <button
                onClick={() => logout()}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/60 transition-colors border border-transparent hover:border-white/10"
                title="Sign Out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link
                href="/login"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors"
              >
                <LogIn className="w-3.5 h-3.5" />
                Sign In
              </Link>
              <Link
                href="/signup"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/30 transition-all"
              >
                Get Started
              </Link>
            </div>
          )}
        </div>

        {/* Mobile menu trigger */}
        <div className="md:hidden flex items-center gap-2">
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-800/60 rounded-lg"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="md:hidden pt-3 pb-2 border-t border-white/10 mt-3 space-y-1">
          {profile ? (
            <>
              {navLinks.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
                      isActive ? 'bg-indigo-600 text-white' : 'text-slate-300 hover:bg-slate-800/60'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    {item.label}
                  </Link>
                );
              })}
              <div className="pt-2 flex items-center justify-between px-3 text-xs text-slate-400">
                <span>{profile.email}</span>
                <button
                  onClick={() => {
                    logout();
                    setMobileMenuOpen(false);
                  }}
                  className="flex items-center gap-1 text-rose-400 hover:underline"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  Sign Out
                </button>
              </div>
            </>
          ) : (
            <div className="flex flex-col gap-2 pt-2">
              <Link
                href="/login"
                onClick={() => setMobileMenuOpen(false)}
                className="text-center px-4 py-2 rounded-lg text-sm font-medium bg-slate-800 text-white"
              >
                Sign In
              </Link>
              <Link
                href="/signup"
                onClick={() => setMobileMenuOpen(false)}
                className="text-center px-4 py-2 rounded-lg text-sm font-semibold bg-indigo-600 text-white"
              >
                Get Started
              </Link>
            </div>
          )}
        </div>
      )}
    </nav>
  );
};
