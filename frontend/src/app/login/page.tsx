'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { Brain, LogIn, AlertCircle, ShieldCheck, User } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const { login, devLogin } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please provide both email and password.');
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.push('/chat');
    } catch (err: any) {
      setError(err?.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleQuickDemo = async (role: 'user' | 'admin') => {
    setError(null);
    setSubmitting(true);
    try {
      await devLogin(role);
      router.push('/chat');
    } catch (err: any) {
      setError(err?.message || 'Quick demo login failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-md p-6 sm:p-8 bg-white border border-slate-200 rounded-2xl shadow-lg space-y-6">
      <div className="text-center space-y-2">
        <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center mx-auto shadow-sm">
          <Brain className="w-5 h-5" />
        </div>
        <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
          Sign In to Workspace
        </h1>
        <p className="text-xs sm:text-sm text-slate-500">
          Agentic memory management with intelligent cognitive forgetting.
        </p>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 flex items-start gap-2.5 text-xs text-rose-800">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-600" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4 text-xs">
        <div className="space-y-1">
          <label className="font-medium text-slate-700">Email Address</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="user@example.com"
            required
            className="w-full px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-slate-900 text-xs focus:outline-none focus:border-indigo-500 focus:bg-white"
          />
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <label className="font-medium text-slate-700">Password</label>
          </div>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            className="w-full px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-slate-900 text-xs focus:outline-none focus:border-indigo-500 focus:bg-white"
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-xs transition-colors disabled:opacity-50"
        >
          <LogIn className="w-4 h-4" />
          <span>{submitting ? 'Authenticating...' : 'Sign In'}</span>
        </button>
      </form>

      {/* Quick Access */}
      <div className="pt-2 border-t border-slate-100 space-y-2">
        <div className="text-[11px] font-medium text-slate-400 text-center uppercase tracking-wider">
          Quick Demo Access
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => handleQuickDemo('user')}
            disabled={submitting}
            className="flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-medium transition-colors"
          >
            <User className="w-3.5 h-3.5 text-indigo-600" />
            <span>Demo User</span>
          </button>
          <button
            type="button"
            onClick={() => handleQuickDemo('admin')}
            disabled={submitting}
            className="flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-medium transition-colors"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" />
            <span>Admin Demo</span>
          </button>
        </div>
      </div>

      <div className="text-center text-xs text-slate-500 pt-1">
        Don&apos;t have an account?{' '}
        <Link href="/signup" className="text-indigo-600 hover:underline font-semibold">
          Create one now
        </Link>
      </div>
    </div>
  );
}
