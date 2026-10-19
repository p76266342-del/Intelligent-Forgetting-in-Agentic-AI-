'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { api } from '@/lib/api';
import {
  Settings,
  User,
  Shield,
  Download,
  Trash2,
  LogOut,
  AlertTriangle,
  Check,
  Brain,
  Database,
  Cpu,
} from 'lucide-react';

export default function SettingsPage() {
  const router = useRouter();
  const { profile, logout, refreshProfile, loading: authLoading } = useAuth();

  const [displayName, setDisplayName] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateSuccess, setUpdateSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [backendServices, setBackendServices] = useState<any>(null);

  useEffect(() => {
    if (!authLoading && !profile) {
      router.push('/login');
    }
    if (profile) {
      setDisplayName(profile.display_name || '');
    }
    api.getHealth()
      .then((data) => setBackendServices(data.services))
      .catch(() => {});
  }, [profile, authLoading, router]);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsUpdating(true);
    setErrorMsg(null);
    setUpdateSuccess(false);
    try {
      await api.updateProfile({ display_name: displayName.trim() });
      await refreshProfile();
      setUpdateSuccess(true);
      setTimeout(() => setUpdateSuccess(false), 3000);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to update profile.');
    } finally {
      setIsUpdating(false);
    }
  };

  const handleExportData = async () => {
    try {
      const [convs, mems] = await Promise.all([
        api.listConversations(),
        api.listMemories('ALL', 'ALL'),
      ]);

      const exportPayload = {
        exported_at: new Date().toISOString(),
        user_profile: profile,
        conversations: convs,
        memories: mems,
      };

      const blob = new Blob([JSON.stringify(exportPayload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `intelligent_forgetting_export_${profile?.uid || 'user'}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Data export failed:', err);
      alert('Failed to generate export file.');
    }
  };

  const handleDeleteAccount = async () => {
    const confirmation = prompt(
      'Are you sure you want to permanently delete your account? This will purge all your conversations, chat messages, and Qdrant semantic vectors. Type "DELETE" to confirm:'
    );
    if (confirmation !== 'DELETE') return;

    setIsDeleting(true);
    try {
      await api.deleteAccount();
      await logout();
      router.push('/');
    } catch (err: any) {
      alert(`Account deletion failed: ${err?.message}`);
      setIsDeleting(false);
    }
  };

  if (authLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-slate-400">
        <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex-1 h-full min-h-0 overflow-y-auto p-4 sm:p-6 lg:p-8 max-w-4xl mx-auto w-full space-y-6">
      
      {/* Page Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-slate-900 flex items-center gap-2">
          <Settings className="w-6 h-6 text-indigo-600" />
          <span>Account & Memory Settings</span>
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
          Manage your personal profile, review connected engine infrastructure, and export conversation history.
        </p>
      </div>

      {/* Alert Notices */}
      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            <span className="font-medium">{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-rose-600 hover:text-rose-800 text-xs font-semibold">
            Dismiss
          </button>
        </div>
      )}

      {updateSuccess && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
          <Check className="w-4 h-4 text-emerald-600 shrink-0" />
          <span className="font-medium">Profile successfully updated.</span>
        </div>
      )}

      {/* Profile Information Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-xs">
        <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
          <User className="w-4 h-4 text-indigo-600" />
          <h2 className="font-semibold text-slate-900 text-sm">Profile Information</h2>
        </div>

        <form onSubmit={handleUpdateProfile} className="space-y-4 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="font-medium text-slate-700">Display Name</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Your Name"
                className="w-full px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-indigo-500 focus:bg-white"
              />
            </div>

            <div className="space-y-1">
              <label className="font-medium text-slate-700">Email Address</label>
              <input
                type="text"
                value={profile?.email || 'N/A'}
                disabled
                className="w-full px-3 py-2 rounded-lg bg-slate-100 border border-slate-200 text-slate-500 cursor-not-allowed"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="font-medium text-slate-700">User ID (Tenant UID)</label>
              <input
                type="text"
                value={profile?.uid || 'N/A'}
                disabled
                className="w-full px-3 py-2 rounded-lg bg-slate-100 border border-slate-200 font-mono text-slate-500 text-[11px] cursor-not-allowed"
              />
            </div>

            <div className="space-y-1">
              <label className="font-medium text-slate-700">Role & Access Tier</label>
              <div className="pt-1.5 flex items-center gap-2">
                <span className="font-semibold uppercase tracking-wider text-[10px] px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
                  {profile?.role || 'user'}
                </span>
                <span className="text-[11px] text-slate-500">
                  {profile?.role === 'admin' ? 'Administrative and system privileges' : 'Standard member access'}
                </span>
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={isUpdating}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-xs transition-colors disabled:opacity-50"
            >
              {isUpdating ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>

      {/* Connected Architecture & Engine Status */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-xs">
        <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
          <Brain className="w-4 h-4 text-indigo-600" />
          <h2 className="font-semibold text-slate-900 text-sm">Active Cognitive Infrastructure</h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200/80 space-y-1">
            <div className="flex items-center gap-2 text-slate-700 font-semibold">
              <Database className="w-3.5 h-3.5 text-indigo-600" />
              <span>Vector Store</span>
            </div>
            <p className="text-[11px] text-slate-500">Qdrant Cloud Dense Vectors</p>
            <div className="text-[10px] font-mono text-emerald-700 font-semibold pt-1">
              {backendServices?.qdrant ? 'Healthy & Connected' : 'Ready'}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200/80 space-y-1">
            <div className="flex items-center gap-2 text-slate-700 font-semibold">
              <Cpu className="w-3.5 h-3.5 text-indigo-600" />
              <span>Language Model</span>
            </div>
            <p className="text-[11px] text-slate-500">Google Gemini 2.5 Flash</p>
            <div className="text-[10px] font-mono text-emerald-700 font-semibold pt-1">
              Live & Streaming (SSE)
            </div>
          </div>

          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200/80 space-y-1">
            <div className="flex items-center gap-2 text-slate-700 font-semibold">
              <Shield className="w-3.5 h-3.5 text-indigo-600" />
              <span>Persistence & Cache</span>
            </div>
            <p className="text-[11px] text-slate-500">SQLite Lockstep + Firestore</p>
            <div className="text-[10px] font-mono text-emerald-700 font-semibold pt-1">
              Multi-Tenant Isolated
            </div>
          </div>
        </div>
      </div>

      {/* Data Management & Privacy Controls */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-xs">
        <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
          <Download className="w-4 h-4 text-indigo-600" />
          <h2 className="font-semibold text-slate-900 text-sm">Data & Privacy Controls</h2>
        </div>

        <div className="space-y-4 text-xs">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-lg bg-slate-50 border border-slate-200/80">
            <div>
              <h3 className="font-semibold text-slate-800">Export All Personal Data</h3>
              <p className="text-[11px] text-slate-500">
                Download a complete JSON export of your profile, conversation transcripts, and cognitive memories.
              </p>
            </div>
            <button
              onClick={handleExportData}
              className="px-3.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-medium shadow-xs transition-colors shrink-0"
            >
              Export JSON
            </button>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-lg bg-rose-50/60 border border-rose-200">
            <div>
              <h3 className="font-semibold text-rose-900">Delete Account & Purge Memory</h3>
              <p className="text-[11px] text-rose-700">
                Permanently purge your account, conversations, chat transcripts, and semantic vectors from both SQLite and Qdrant.
              </p>
            </div>
            <button
              onClick={handleDeleteAccount}
              disabled={isDeleting}
              className="px-3.5 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white font-semibold shadow-xs transition-colors shrink-0 disabled:opacity-50"
            >
              {isDeleting ? 'Deleting...' : 'Delete Account'}
            </button>
          </div>
        </div>
      </div>

    </div>
  );
}
