'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import {
  api,
  AdminOverview,
  UserRecord,
  RLExperiment,
  AuditLogItem,
} from '@/lib/api';
import {
  ShieldCheck,
  Users,
  Database,
  Cpu,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw,
  Search,
  FileText,
  Lock,
  Layers,
  ArrowRight,
} from 'lucide-react';

export default function AdminPage() {
  const router = useRouter();
  const { profile, loading: authLoading } = useAuth();

  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [experiments, setExperiments] = useState<RLExperiment[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [userSearch, setUserSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'overview' | 'users' | 'rl' | 'audit'>('overview');
  const [isTriggeringRL, setIsTriggeringRL] = useState(false);
  const [rlMessage, setRlMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!authLoading && !profile) {
      router.push('/login');
    }
  }, [profile, authLoading, router]);

  useEffect(() => {
    if (profile?.role === 'admin') {
      loadData();
    } else if (profile) {
      setIsLoading(false);
    }
  }, [profile]);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [ovRes, uListRes, expListRes, logsRes] = await Promise.allSettled([
        api.getAdminOverview(),
        api.listAdminUsers(),
        api.listRLExperiments(),
        api.getAuditLogs(),
      ]);
      if (ovRes.status === 'fulfilled') setOverview(ovRes.value);
      if (uListRes.status === 'fulfilled') setUsers(uListRes.value);
      if (expListRes.status === 'fulfilled') setExperiments(expListRes.value);
      if (logsRes.status === 'fulfilled') setAuditLogs(logsRes.value);
    } catch (err) {
      console.error('Failed to load admin telemetry:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleStatus = async (uid: string, currentStatus: string) => {
    const nextStatus = currentStatus === 'active' ? 'disabled' : 'active';
    try {
      await api.updateUserStatus(uid, nextStatus as any);
      const updated = await api.listAdminUsers(userSearch);
      setUsers(updated);
    } catch (err) {
      console.error('Status update failed:', err);
    }
  };

  const handleToggleRole = async (uid: string, currentRole: string) => {
    const nextRole = currentRole === 'admin' ? 'user' : 'admin';
    if (!confirm(`Are you sure you want to change user role to ${nextRole.toUpperCase()}?`)) return;
    try {
      await api.updateUserRole(uid, nextRole as any);
      const updated = await api.listAdminUsers(userSearch);
      setUsers(updated);
    } catch (err) {
      console.error('Role update failed:', err);
    }
  };

  const handleTriggerRL = async () => {
    setIsTriggeringRL(true);
    setRlMessage(null);
    try {
      const exp = await api.triggerRLExperiment(50);
      setRlMessage(`Experiment #${exp.id.slice(0, 8)} completed. Mean Reward: ${exp.mean_reward.toFixed(3)}`);
      const updatedExp = await api.listRLExperiments();
      setExperiments(updatedExp);
    } catch (err: any) {
      setRlMessage(`Experiment execution failed: ${err.message}`);
    } finally {
      setIsTriggeringRL(false);
    }
  };

  if (authLoading || isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-slate-400">
        <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Role Gate
  if (profile?.role !== 'admin') {
    return (
      <div className="flex-1 flex items-center justify-center p-4">
        <div className="bg-white border border-slate-200 rounded-2xl p-8 text-center max-w-md space-y-4 shadow-sm">
          <div className="w-12 h-12 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center mx-auto border border-amber-200">
            <Lock className="w-6 h-6" />
          </div>
          <h1 className="text-lg font-bold text-slate-900">Administrative Access Required</h1>
          <p className="text-xs text-slate-500 leading-relaxed">
            This console is restricted to authenticated administrators.
            Your current account role is <span className="font-semibold text-slate-700">{profile?.role || 'user'}</span>.
          </p>
          <div className="pt-2">
            <Link
              href="/chat"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs"
            >
              Return to Chat Workspace
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const filteredUsers = users.filter((u) => {
    if (!userSearch.trim()) return true;
    const q = userSearch.toLowerCase();
    return u.uid.toLowerCase().includes(q) || (u.email && u.email.toLowerCase().includes(q));
  });

  return (
    <div className="flex-1 h-full min-h-0 overflow-y-auto p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full space-y-6">
      
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-indigo-600" />
            <span>Admin Console & Telemetry</span>
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            Multi-tenant oversight, cognitive memory distribution, and contextual bandit reinforcement learning.
          </p>
        </div>

        <button
          onClick={loadData}
          className="self-start sm:self-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium shadow-xs transition-colors"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Refresh Metrics</span>
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200">
        {[
          { key: 'overview', label: 'Platform Overview', icon: Activity },
          { key: 'users', label: `Users (${users.length})`, icon: Users },
          { key: 'rl', label: 'Reinforcement Learning', icon: Cpu },
          { key: 'audit', label: `System Audit Logs (${auditLogs.length})`, icon: FileText },
        ].map((t) => {
          const Icon = t.icon;
          const isActive = activeTab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key as any)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all ${
                isActive
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-900'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{t.label}</span>
            </button>
          );
        })}
      </div>

      {/* TAB 1: OVERVIEW */}
      {activeTab === 'overview' && overview && (
        <div className="space-y-6">
          {/* Top KPI Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-1">
              <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Total Users</span>
              <div className="text-2xl font-bold text-slate-900">{overview.users.total}</div>
              <span className="text-[11px] text-emerald-600 font-medium">{overview.users.active} active accounts</span>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-1">
              <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Total Memories</span>
              <div className="text-2xl font-bold text-slate-900">{overview.memories.total}</div>
              <span className="text-[11px] text-indigo-600 font-medium">{overview.memories.active} in active prompt</span>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-1">
              <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Active Tokens</span>
              <div className="text-2xl font-bold text-slate-900 font-mono">
                ~{overview.memories.estimated_active_tokens.toLocaleString()}
              </div>
              <span className="text-[11px] text-slate-500">Working prompt context</span>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-1">
              <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Database Size</span>
              <div className="text-2xl font-bold text-slate-900 font-mono">
                {(overview.memories.storage_size_bytes / 1024).toFixed(1)} KB
              </div>
              <span className="text-[11px] text-slate-500">SQLite + Qdrant</span>
            </div>
          </div>

          {/* Memory Lifecycle Breakdown */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-xs">
            <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
              <Database className="w-4 h-4 text-indigo-600" />
              <span>Memory Lifecycle State Distribution</span>
            </h2>

            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-100 text-center">
                <span className="text-[10px] font-bold text-emerald-800 uppercase block">ACTIVE</span>
                <div className="text-xl font-bold text-emerald-900 mt-1">{overview.memories.active}</div>
              </div>

              <div className="p-3 rounded-lg bg-purple-50 border border-purple-100 text-center">
                <span className="text-[10px] font-bold text-purple-800 uppercase block">SUMMARIZED</span>
                <div className="text-xl font-bold text-purple-900 mt-1">{overview.memories.summarized}</div>
              </div>

              <div className="p-3 rounded-lg bg-amber-50 border border-amber-100 text-center">
                <span className="text-[10px] font-bold text-amber-800 uppercase block">ARCHIVED</span>
                <div className="text-xl font-bold text-amber-900 mt-1">{overview.memories.archived}</div>
              </div>

              <div className="p-3 rounded-lg bg-rose-50 border border-rose-100 text-center">
                <span className="text-[10px] font-bold text-rose-800 uppercase block">FORGOTTEN</span>
                <div className="text-xl font-bold text-rose-900 mt-1">{overview.memories.forgotten}</div>
              </div>

              <div className="p-3 rounded-lg bg-indigo-50 border border-indigo-100 text-center">
                <span className="text-[10px] font-bold text-indigo-800 uppercase block">PROTECTED</span>
                <div className="text-xl font-bold text-indigo-900 mt-1">{overview.memories.permanent}</div>
              </div>
            </div>
          </div>

          {/* Backend Service Status Cards */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-xs">
            <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-600" />
              <span>Core Integrations & Engine Health</span>
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200/80 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-slate-600 font-medium">Google Gemini</span>
                  <span
                    className={`font-semibold text-[11px] ${
                      overview.services.gemini_live ? 'text-emerald-700' : 'text-amber-700'
                    }`}
                  >
                    {overview.services.gemini_live ? 'Live' : 'Simulation'}
                  </span>
                </div>
                <span className="text-[11px] font-mono text-slate-800 block">
                  Model: {overview.services.model_configured}
                </span>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200/80 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-slate-600 font-medium">Qdrant Cloud</span>
                  <span
                    className={`font-semibold text-[11px] ${
                      overview.services.qdrant_healthy ? 'text-emerald-700' : 'text-rose-700'
                    }`}
                  >
                    {overview.services.qdrant_healthy ? 'Connected' : 'Unavailable'}
                  </span>
                </div>
                <span className="text-[11px] font-mono text-slate-800 block truncate">
                  Collection: {overview.services.qdrant_collection}
                </span>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200/80 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-slate-600 font-medium">Embedding Engine</span>
                  <span className="font-semibold text-[11px] text-indigo-700">FastEmbed ONNX</span>
                </div>
                <span className="text-[11px] font-mono text-slate-800 block truncate">
                  {overview.services.embedding_model}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: USERS */}
      {activeTab === 'users' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3 bg-white p-3 rounded-xl border border-slate-200 shadow-xs">
            <div className="relative flex-1 max-w-sm">
              <input
                type="text"
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                placeholder="Search user by UID or email..."
                className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-800 focus:outline-none focus:border-indigo-500 focus:bg-white"
              />
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto shadow-xs">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 text-[10px] uppercase font-bold text-slate-500 border-b border-slate-200">
                <tr>
                  <th className="p-3">User UID</th>
                  <th className="p-3">Email</th>
                  <th className="p-3">Display Name</th>
                  <th className="p-3">Role</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Last Active</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredUsers.map((u) => (
                  <tr key={u.uid} className="hover:bg-slate-50 transition-colors">
                    <td className="p-3 font-mono text-indigo-600 text-[11px]">{u.uid}</td>
                    <td className="p-3">{u.email || 'N/A'}</td>
                    <td className="p-3 font-medium text-slate-900">{u.display_name || 'N/A'}</td>
                    <td className="p-3">
                      <span
                        className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${
                          u.role === 'admin'
                            ? 'bg-amber-50 text-amber-800 border-amber-200'
                            : 'bg-slate-100 text-slate-700 border-slate-200'
                        }`}
                      >
                        {u.role}
                      </span>
                    </td>
                    <td className="p-3">
                      <span
                        className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${
                          u.status === 'active'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-rose-50 text-rose-700 border-rose-200'
                        }`}
                      >
                        {u.status}
                      </span>
                    </td>
                    <td className="p-3 text-slate-500 text-[11px]">
                      {new Date(u.last_active_at).toLocaleString()}
                    </td>
                    <td className="p-3 text-right space-x-2">
                      <button
                        onClick={() => handleToggleStatus(u.uid, u.status)}
                        className="text-[11px] font-medium text-indigo-600 hover:text-indigo-800 underline"
                      >
                        {u.status === 'active' ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        onClick={() => handleToggleRole(u.uid, u.role)}
                        className="text-[11px] font-medium text-amber-700 hover:text-amber-900 underline"
                      >
                        Make {u.role === 'admin' ? 'User' : 'Admin'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 3: REINFORCEMENT LEARNING */}
      {activeTab === 'rl' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl bg-white border border-slate-200 shadow-xs">
            <div className="space-y-0.5">
              <h3 className="font-semibold text-slate-900 text-sm">
                LinUCB Contextual Bandit Engine
              </h3>
              <p className="text-xs text-slate-500">
                Dynamically balances retrieval quality, context token economy, and critical information safety.
              </p>
            </div>
            <button
              onClick={handleTriggerRL}
              disabled={isTriggeringRL}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs flex items-center gap-1.5 shrink-0 disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5" />
              <span>{isTriggeringRL ? 'Training Policy...' : 'Run 50-Step Benchmark'}</span>
            </button>
          </div>

          {rlMessage && (
            <div className="p-3.5 rounded-lg bg-indigo-50 border border-indigo-200 text-xs text-indigo-900">
              {rlMessage}
            </div>
          )}

          <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto shadow-xs">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 text-[10px] uppercase font-bold text-slate-500 border-b border-slate-200">
                <tr>
                  <th className="p-3">Run ID</th>
                  <th className="p-3">Policy</th>
                  <th className="p-3">Steps</th>
                  <th className="p-3">Mean Reward</th>
                  <th className="p-3">Critical Retention</th>
                  <th className="p-3">Retrieval Success</th>
                  <th className="p-3">Storage Saved</th>
                  <th className="p-3">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {experiments.map((exp) => (
                  <tr key={exp.id} className="hover:bg-slate-50">
                    <td className="p-3 font-mono text-indigo-600">#{exp.id.slice(0, 8)}</td>
                    <td className="p-3 font-mono text-[11px]">{exp.policy_version}</td>
                    <td className="p-3 font-mono">{exp.iterations}</td>
                    <td className="p-3 font-mono text-emerald-700 font-semibold">{exp.mean_reward.toFixed(3)}</td>
                    <td className="p-3 font-mono">{(exp.critical_retention_rate * 100).toFixed(1)}%</td>
                    <td className="p-3 font-mono">{(exp.retrieval_success_rate * 100).toFixed(1)}%</td>
                    <td className="p-3 font-mono">{(exp.storage_reduction_rate * 100).toFixed(1)}%</td>
                    <td className="p-3 text-slate-500 text-[11px]">
                      {new Date(exp.timestamp).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 4: AUDIT LOGS */}
      {activeTab === 'audit' && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto shadow-xs">
          <table className="w-full text-left text-xs text-slate-700">
            <thead className="bg-slate-50 text-[10px] uppercase font-bold text-slate-500 border-b border-slate-200">
              <tr>
                <th className="p-3">Timestamp</th>
                <th className="p-3">Actor UID</th>
                <th className="p-3">Action</th>
                <th className="p-3">Target</th>
                <th className="p-3">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {auditLogs.map((log) => (
                <tr key={log.id} className="hover:bg-slate-50">
                  <td className="p-3 text-slate-500 font-mono text-[11px]">
                    {new Date(log.timestamp).toLocaleString()}
                  </td>
                  <td className="p-3 font-mono text-indigo-600">{log.actor_uid}</td>
                  <td className="p-3">
                    <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                      {log.action}
                    </span>
                  </td>
                  <td className="p-3 text-slate-800 font-mono text-[11px]">
                    {log.target_type} {log.target_id ? `(#${log.target_id.slice(0, 8)})` : ''}
                  </td>
                  <td className="p-3 text-slate-500 font-mono text-[10px] max-w-xs truncate">
                    {JSON.stringify(log.details)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

    </div>
  );
}
