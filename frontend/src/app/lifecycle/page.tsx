'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import {
  api,
  LifecycleActivityItem,
  ForgettingEvaluationResult,
} from '@/lib/api';
import {
  Activity,
  Sliders,
  RefreshCw,
  Clock,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Layers,
  Shield,
  Check,
  X,
  Archive,
  Trash2,
  Minimize2,
  Play,
  RotateCcw,
  Info,
} from 'lucide-react';

export default function LifecyclePage() {
  const router = useRouter();
  const { profile, loading: authLoading } = useAuth();

  const [activeTab, setActiveTab] = useState<'activity_log' | 'decisions'>('activity_log');

  // Activity Log State
  const [activityLogs, setActivityLogs] = useState<LifecycleActivityItem[]>([]);
  const [lifecycleStats, setLifecycleStats] = useState<{
    total_operations: number;
    measured_token_savings: number;
    estimated_token_savings: number;
    unique_memories_affected: number;
    kept_count: number;
    archived_count: number;
    compressed_count: number;
    pruned_count: number;
    calculation_method: string;
  } | null>(null);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [opFilter, setOpFilter] = useState<string>('ALL');
  const [resultFilter, setResultFilter] = useState<string>('ALL');

  // Decisions State
  const [evalResult, setEvalResult] = useState<ForgettingEvaluationResult | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [applySummary, setApplySummary] = useState<{
    retained: number;
    summarized: number;
    archived: number;
    forgotten: number;
    keep?: number;
    compress?: number;
    prune?: number;
    details?: any[];
  } | null>(null);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !profile) {
      router.push('/login');
    }
  }, [profile, authLoading, router]);

  useEffect(() => {
    if (profile) {
      loadActivityLogs();
    }
  }, [profile]);

  const loadActivityLogs = async () => {
    setLoadingLogs(true);
    setErrorMessage(null);
    try {
      const [logs, stats] = await Promise.all([
        api.getActivityLog(150, 0),
        api.getLifecycleStats().catch(() => null),
      ]);
      setActivityLogs(logs);
      if (stats) setLifecycleStats(stats);
    } catch (err: any) {
      console.error('Failed to load activity logs:', err);
      setErrorMessage(err?.message || 'Failed to fetch lifecycle activity logs.');
    } finally {
      setLoadingLogs(false);
    }
  };

  const handleRunEvaluation = async () => {
    setIsEvaluating(true);
    setErrorMessage(null);
    try {
      const res = await api.evaluateForgetting(true);
      setEvalResult(res);
      setApplySummary(null);
      setActiveTab('decisions');
    } catch (err: any) {
      console.error('Evaluation failed:', err);
      setErrorMessage(err?.message || 'Forgetting evaluation failed.');
    } finally {
      setIsEvaluating(false);
    }
  };

  const handleConfirmApply = async () => {
    if (!evalResult) return;
    setIsApplying(true);
    setErrorMessage(null);
    try {
      const res = await api.applyForgetting(
        evalResult.actions_proposed,
        undefined,
        evalResult.evaluation_id
      );
      setApplySummary(res);
      setEvalResult(null);
      setShowApplyModal(false);
      setSuccessMessage('Lifecycle actions applied to authoritative SQLite storage and Qdrant index.');
      setTimeout(() => setSuccessMessage(null), 4000);
      await loadActivityLogs();
    } catch (err: any) {
      console.error('Failed to apply forgetting actions:', err);
      setErrorMessage(err?.message || 'Failed to apply forgetting actions.');
    } finally {
      setIsApplying(false);
    }
  };

  if (authLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-slate-400">
        <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Filter logs
  const filteredLogs = activityLogs.filter((log) => {
    if (opFilter !== 'ALL' && log.operation.toUpperCase() !== opFilter) return false;
    if (resultFilter !== 'ALL' && log.result.toUpperCase() !== resultFilter) return false;
    return true;
  });

  // Calculate metrics with net unique memory accounting to prevent duplicate accumulation on repeated cycles
  const memoryNetSavings = new Map<string, number>();
  const chronologicalLogs = [...activityLogs].reverse();
  let successfulCompressions = 0;
  let successfulArchivals = 0;
  let successfulPrunes = 0;

  for (const log of chronologicalLogs) {
    if (log.result !== 'success') continue;
    const op = log.operation.toUpperCase();
    const memId = log.memory_id;
    
    if (op === 'KEEP') {
      // KEEP never saves tokens
      if (!memoryNetSavings.has(memId)) memoryNetSavings.set(memId, 0);
    } else if (op === 'RESTORE') {
      // Restoring back to active context un-saves previous cold storage tokens
      memoryNetSavings.set(memId, 0);
    } else if (op === 'ARCHIVE') {
      successfulArchivals++;
      memoryNetSavings.set(memId, Math.max(0, log.token_savings || 0));
    } else if (op === 'PRUNE') {
      successfulPrunes++;
      memoryNetSavings.set(memId, Math.max(0, log.token_savings || 0));
    } else if (op === 'COMPRESS') {
      successfulCompressions++;
      memoryNetSavings.set(memId, Math.max(0, log.token_savings || 0));
    }
  }

  const computedSavings = Array.from(memoryNetSavings.values()).reduce((sum, v) => sum + v, 0);
  const totalTokensSaved = lifecycleStats?.measured_token_savings ?? computedSavings;
  const compressionCount = lifecycleStats?.compressed_count ?? successfulCompressions;
  const archivalCount = lifecycleStats?.archived_count ?? successfulArchivals;
  const pruneCount = lifecycleStats?.pruned_count ?? successfulPrunes;

  return (
    <div className="flex-1 h-full min-h-0 overflow-y-auto p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full space-y-6">
      
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Activity className="w-6 h-6 text-indigo-600" />
            <span>Lifecycle Activity & Decisions</span>
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            Verified operational audit logs and cognitive pruning policy recommendations.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {activeTab === 'activity_log' ? (
            <button
              onClick={loadActivityLogs}
              disabled={loadingLogs}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium shadow-xs transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingLogs ? 'animate-spin' : ''}`} />
              <span>Refresh Log</span>
            </button>
          ) : (
            <button
              onClick={handleRunEvaluation}
              disabled={isEvaluating}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs transition-colors disabled:opacity-50"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>{isEvaluating ? 'Evaluating...' : 'Run Dry-Run Preview'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Alert Notices */}
      {errorMessage && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            <span className="font-medium">{errorMessage}</span>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-rose-600 hover:text-rose-800 text-xs font-semibold">
            Dismiss
          </button>
        </div>
      )}

      {successMessage && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Check className="w-4 h-4 text-emerald-600 shrink-0" />
            <span className="font-medium">{successMessage}</span>
          </div>
          <button onClick={() => setSuccessMessage(null)} className="text-emerald-600 hover:text-emerald-800 text-xs font-semibold">
            Dismiss
          </button>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200">
        <button
          onClick={() => setActiveTab('activity_log')}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all ${
            activeTab === 'activity_log'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          }`}
        >
          <Activity className="w-4 h-4" />
          <span>Activity Audit Log ({activityLogs.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('decisions')}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all ${
            activeTab === 'decisions'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          }`}
        >
          <Sliders className="w-4 h-4" />
          <span>
            Lifecycle & Pruning Decisions {evalResult ? `(${evalResult.actions_proposed.length} previewed)` : ''}
          </span>
        </button>
      </div>

      {/* TAB 1: ACTIVITY LOG */}
      {activeTab === 'activity_log' && (
        <div className="space-y-6">
          {/* Real Metrics Highlights */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-white border border-slate-200 rounded-xl p-3.5 shadow-xs">
              <span className="text-[10px] font-medium uppercase text-slate-400 block tracking-wider">Total Operations</span>
              <div className="text-lg font-bold text-slate-900 mt-0.5">{activityLogs.length}</div>
              <span className="text-[11px] text-slate-500">Recorded mutations</span>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl p-3.5 shadow-xs">
              <span className="text-[10px] font-medium uppercase text-emerald-600 block tracking-wider">Measured Tokens Saved</span>
              <div className="text-lg font-bold text-emerald-700 mt-0.5">{totalTokensSaved > 0 ? `~${totalTokensSaved}` : '0'}</div>
              <span className="text-[11px] text-slate-500">Net verified prompt reduction</span>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl p-3.5 shadow-xs">
              <span className="text-[10px] font-medium uppercase text-purple-600 block tracking-wider">Compressions</span>
              <div className="text-lg font-bold text-purple-700 mt-0.5">{compressionCount}</div>
              <span className="text-[11px] text-slate-500">Synthesized groups</span>
            </div>

            <div className="bg-white border border-slate-200 rounded-xl p-3.5 shadow-xs">
              <span className="text-[10px] font-medium uppercase text-amber-600 block tracking-wider">Archivals & Prunes</span>
              <div className="text-lg font-bold text-amber-700 mt-0.5">{archivalCount + pruneCount}</div>
              <span className="text-[11px] text-slate-500">{archivalCount} cold, {pruneCount} pruned</span>
            </div>
          </div>

          {/* Filters Bar */}
          <div className="bg-white border border-slate-200 rounded-xl p-3 flex flex-col sm:flex-row items-center justify-between gap-3 shadow-xs">
            <div className="flex items-center gap-2 w-full sm:w-auto">
              <span className="text-xs font-medium text-slate-600 shrink-0">Filter Operation:</span>
              <select
                value={opFilter}
                onChange={(e) => setOpFilter(e.target.value)}
                className="px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-800 focus:outline-none focus:border-indigo-500"
              >
                <option value="ALL">All Operations</option>
                <option value="KEEP">KEEP</option>
                <option value="COMPRESS">COMPRESS</option>
                <option value="ARCHIVE">ARCHIVE</option>
                <option value="PRUNE">PRUNE</option>
                <option value="RESTORE">RESTORE</option>
              </select>
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
              <span className="text-xs font-medium text-slate-600 shrink-0">Result:</span>
              <select
                value={resultFilter}
                onChange={(e) => setResultFilter(e.target.value)}
                className="px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-800 focus:outline-none focus:border-indigo-500"
              >
                <option value="ALL">All Results</option>
                <option value="SUCCESS">Success Only</option>
                <option value="FAILED">Failed Only</option>
              </select>
            </div>
          </div>

          {/* Activity Table / Timeline */}
          {loadingLogs ? (
            <div className="py-16 text-center text-xs text-slate-400 flex flex-col items-center gap-2">
              <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
              <span>Loading verified audit trail...</span>
            </div>
          ) : filteredLogs.length === 0 ? (
            <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-xs text-slate-500 space-y-2 shadow-xs">
              <Activity className="w-8 h-8 text-slate-300 mx-auto" />
              <p className="font-semibold text-slate-700 text-sm">No lifecycle activity events recorded</p>
              <p className="text-slate-400 max-w-md mx-auto">
                Mutations are written to this audit log whenever memory compression, archival, restoration, or pruning actions are persistently executed. Dry-run previews are never logged as mutations.
              </p>
            </div>
          ) : (
            <div className="space-y-2.5">
              {filteredLogs.map((log) => {
                const op = log.operation.toUpperCase();
                const isKeep = op === 'KEEP' || op === 'RETAIN';
                const isCompress = op === 'COMPRESS' || op === 'SUMMARIZED';
                const isArchive = op === 'ARCHIVE' || op === 'ARCHIVED';
                const isPrune = op === 'PRUNE' || op === 'PRUNED_PERMANENTLY' || op === 'DELETED_PERMANENTLY';
                const isRestore = op === 'RESTORE' || op === 'RESTORED';

                const badgeClass = isKeep
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : isCompress
                  ? 'bg-purple-50 text-purple-700 border-purple-200'
                  : isArchive
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : isPrune
                  ? 'bg-rose-50 text-rose-700 border-rose-200'
                  : 'bg-indigo-50 text-indigo-700 border-indigo-200';

                return (
                  <div
                    key={log.id}
                    className="bg-white border border-slate-200 hover:border-slate-300 rounded-xl p-4 space-y-2.5 shadow-xs transition-colors text-xs"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${badgeClass}`}>
                          {op}
                        </span>

                        <span className="font-mono font-medium text-slate-700 text-xs">
                          Memory #{log.memory_id.slice(0, 8)}
                        </span>

                        <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-50 border border-slate-200 text-[10px] font-mono text-slate-600">
                          <span>{log.previous_status}</span>
                          <ArrowRight className="w-3 h-3 text-slate-400" />
                          <span className="font-semibold text-slate-900">{log.new_status}</span>
                        </div>

                        {log.result === 'success' ? (
                          <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                            <CheckCircle2 className="w-3 h-3" />
                            Successfully applied operation
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-[10px] font-semibold text-rose-700 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200">
                            <AlertTriangle className="w-3 h-3" />
                            Failed operation
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2.5 text-slate-400 text-[11px]">
                        {log.token_savings > 0 && (
                          <span className="font-medium text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-100">
                            ~{log.token_savings} measured tokens saved
                          </span>
                        )}
                        <span className="flex items-center gap-1 text-slate-500">
                          <Clock className="w-3 h-3 text-slate-400" />
                          {new Date(log.timestamp).toLocaleString()}
                        </span>
                      </div>
                    </div>

                    {/* Operational Details */}
                    {isCompress && (
                      <div className="p-2.5 rounded-lg bg-purple-50/60 border border-purple-100 text-[11px] text-purple-900 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-purple-800">Consolidated Record:</span>
                          <span className="font-mono bg-purple-100 px-1.5 py-0.5 rounded text-purple-900 font-semibold">
                            #{log.consolidated_memory_id ? log.consolidated_memory_id.slice(0, 8) : log.memory_id.slice(0, 8)}
                          </span>
                          <span className="text-purple-600">(Retained in active working context)</span>
                        </div>
                        {log.source_memory_ids && log.source_memory_ids.length > 0 && (
                          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                            <span className="font-medium text-purple-700">Source Memories:</span>
                            {log.source_memory_ids.map((sid) => (
                              <span key={sid} className="font-mono bg-white px-1.5 py-0.5 rounded border border-purple-200 text-purple-900 text-[10px]">
                                #{sid.slice(0, 8)}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {log.reason && (
                      <div className="text-[11px] text-slate-500 italic">
                        Reason: {log.reason}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: LIFECYCLE & PRUNING DECISIONS */}
      {activeTab === 'decisions' && (
        <div className="space-y-6">
          {/* Policy Overview Explanation Card */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-5 space-y-3 shadow-xs">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1">
                <h3 className="font-semibold text-slate-900 text-sm flex items-center gap-2">
                  <Shield className="w-4 h-4 text-indigo-600" />
                  Cognitive Forgetting Engine Policies
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed max-w-2xl">
                  Evaluates memory items via a mathematical retention formula combining importance, recency decay,
                  retrieval frequency, and semantic redundancy. Pinned and critical items are strictly protected.
                </p>
              </div>

              <button
                onClick={handleRunEvaluation}
                disabled={isEvaluating}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs transition-colors shrink-0 disabled:opacity-50"
              >
                {isEvaluating ? 'Evaluating...' : 'Run Dry-Run Preview'}
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-100 text-[11px]">
              <div className="p-2 rounded-lg bg-emerald-50/60 border border-emerald-100 text-emerald-900">
                <span className="font-bold block">1. KEEP</span>
                <span className="text-emerald-700">Score &gt; Threshold or Pinned/Critical</span>
              </div>
              <div className="p-2 rounded-lg bg-purple-50/60 border border-purple-100 text-purple-900">
                <span className="font-bold block">2. COMPRESS</span>
                <span className="text-purple-700">Token similarity &ge; 0.65 cluster</span>
              </div>
              <div className="p-2 rounded-lg bg-amber-50/60 border border-amber-100 text-amber-900">
                <span className="font-bold block">3. ARCHIVE</span>
                <span className="text-amber-700">Demoted to cold Qdrant storage</span>
              </div>
              <div className="p-2 rounded-lg bg-rose-50/60 border border-rose-100 text-rose-900">
                <span className="font-bold block">4. PRUNE</span>
                <span className="text-rose-700">Score &lt; Forget threshold (ephemeral)</span>
              </div>
            </div>
          </div>

          {/* Applied Results Banner if present */}
          {applySummary && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-2.5">
                <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                <div>
                  <h4 className="font-semibold text-emerald-900 text-xs sm:text-sm">
                    Decisions Successfully Applied Persistently
                  </h4>
                  <p className="text-[11px] text-emerald-700">
                    Authoritative SQLite storage and Qdrant Cloud semantic vectors synchronized in lockstep.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                <div className="bg-white p-2.5 rounded-lg border border-emerald-200 text-center">
                  <span className="text-[10px] font-bold uppercase text-emerald-700 block">KEPT</span>
                  <span className="text-base font-bold text-slate-900">{applySummary.keep ?? applySummary.retained}</span>
                </div>
                <div className="bg-white p-2.5 rounded-lg border border-emerald-200 text-center">
                  <span className="text-[10px] font-bold uppercase text-purple-700 block">COMPRESSED</span>
                  <span className="text-base font-bold text-slate-900">{applySummary.compress ?? applySummary.summarized}</span>
                </div>
                <div className="bg-white p-2.5 rounded-lg border border-emerald-200 text-center">
                  <span className="text-[10px] font-bold uppercase text-amber-700 block">ARCHIVED</span>
                  <span className="text-base font-bold text-slate-900">{applySummary.archived}</span>
                </div>
                <div className="bg-white p-2.5 rounded-lg border border-emerald-200 text-center">
                  <span className="text-[10px] font-bold uppercase text-rose-700 block">PRUNED</span>
                  <span className="text-base font-bold text-slate-900">{applySummary.prune ?? applySummary.forgotten}</span>
                </div>
              </div>
            </div>
          )}

          {/* Dry Run Recommendations Preview */}
          {!evalResult ? (
            !applySummary && (
              <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-xs text-slate-500 space-y-3 shadow-xs">
                <Sparkles className="w-8 h-8 text-indigo-400 mx-auto" />
                <h4 className="font-semibold text-slate-800 text-sm">No Dry-Run Evaluation Active</h4>
                <p className="text-slate-400 max-w-md mx-auto leading-relaxed">
                  Click &ldquo;Run Dry-Run Preview&rdquo; to simulate cognitive retention, compression, archival,
                  and pruning decisions across your active memories without mutating stored records.
                </p>
                <button
                  onClick={handleRunEvaluation}
                  disabled={isEvaluating}
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-xs transition-colors"
                >
                  {isEvaluating ? 'Evaluating...' : 'Run Dry-Run Preview'}
                </button>
              </div>
            )
          ) : (
            <div className="space-y-4">
              {/* Summary Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <div className="bg-white border border-slate-200 rounded-xl p-3 text-center shadow-xs">
                  <span className="text-[10px] font-bold uppercase text-emerald-700 block">KEEP</span>
                  <div className="text-lg font-bold text-slate-900 mt-0.5">{evalResult.keep_count ?? evalResult.retained_count}</div>
                  <span className="text-[10px] text-slate-400">Retain active</span>
                </div>
                <div className="bg-white border border-slate-200 rounded-xl p-3 text-center shadow-xs">
                  <span className="text-[10px] font-bold uppercase text-purple-700 block">COMPRESS</span>
                  <div className="text-lg font-bold text-slate-900 mt-0.5">{evalResult.compress_count ?? evalResult.summarized_count}</div>
                  <span className="text-[10px] text-slate-400">Synthesize cluster</span>
                </div>
                <div className="bg-white border border-slate-200 rounded-xl p-3 text-center shadow-xs">
                  <span className="text-[10px] font-bold uppercase text-amber-700 block">ARCHIVE</span>
                  <div className="text-lg font-bold text-slate-900 mt-0.5">{evalResult.archived_count}</div>
                  <span className="text-[10px] text-slate-400">Cold storage</span>
                </div>
                <div className="bg-white border border-slate-200 rounded-xl p-3 text-center shadow-xs">
                  <span className="text-[10px] font-bold uppercase text-rose-700 block">PRUNE</span>
                  <div className="text-lg font-bold text-slate-900 mt-0.5">{evalResult.prune_count ?? evalResult.forgotten_count}</div>
                  <span className="text-[10px] text-slate-400">Cognitive forget</span>
                </div>
                <div className="bg-white border border-slate-200 rounded-xl p-3 text-center shadow-xs">
                  <span className="text-[10px] font-bold uppercase text-indigo-700 block">SAVINGS</span>
                  <div className="text-lg font-bold text-indigo-600 mt-0.5">~{evalResult.estimated_token_savings}</div>
                  <span className="text-[10px] text-slate-400">Est. tokens saved</span>
                </div>
              </div>

              {/* Action Toolbar */}
              <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-xs text-xs">
                <div className="flex items-center gap-2 text-slate-700">
                  <Info className="w-4 h-4 text-indigo-600 shrink-0" />
                  <span>
                    <strong className="text-slate-900">Dry-Run Preview:</strong> Database has NOT been modified.
                  </span>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-auto">
                  <button
                    onClick={handleRunEvaluation}
                    disabled={isEvaluating}
                    className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 font-medium"
                  >
                    Re-run Preview
                  </button>
                  <button
                    onClick={() => setShowApplyModal(true)}
                    disabled={isApplying}
                    className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold shadow-xs flex items-center gap-1.5 disabled:opacity-50"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Apply Recommendations</span>
                  </button>
                </div>
              </div>

              {/* Proposed Actions List */}
              <div className="space-y-2">
                {evalResult.actions_proposed.map((item, idx) => {
                  const act = (item.action || '').toLowerCase();
                  const isKeep = act === 'keep' || act === 'retain';
                  const isCompress = act === 'compress' || act === 'summarize';
                  const isArchive = act === 'archive';
                  const isPrune = act === 'prune' || act === 'forget';

                  const badgeClass = isKeep
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : isCompress
                    ? 'bg-purple-50 text-purple-700 border-purple-200'
                    : isArchive
                    ? 'bg-amber-50 text-amber-700 border-amber-200'
                    : 'bg-rose-50 text-rose-700 border-rose-200';

                  const actionName = isKeep ? 'KEEP' : isCompress ? 'COMPRESS' : isArchive ? 'ARCHIVE' : isPrune ? 'PRUNE' : item.action.toUpperCase();

                  return (
                    <div
                      key={idx}
                      className="bg-white border border-slate-200 rounded-xl p-3.5 space-y-2 text-xs shadow-xs"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${badgeClass}`}>
                            Recommended action: {actionName}
                          </span>
                          <span className="text-[10px] font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                            Previewed operation
                          </span>
                          <span className="font-mono text-slate-600 text-xs">
                            ID: #{item.memory_id.slice(0, 8)}
                          </span>
                          <span className="font-mono text-slate-800 font-semibold text-xs">
                            Score: {item.score.toFixed(3)}
                          </span>
                        </div>
                        <div className="text-slate-500 italic text-[11px]">{item.reason}</div>
                      </div>

                      {item.target_summary_content && (
                        <div className="p-2.5 rounded-lg bg-purple-50 border border-purple-100 text-[11px] text-purple-900">
                          <span className="font-semibold text-purple-800">Synthesized Content: </span>
                          &ldquo;{item.target_summary_content}&rdquo;
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Confirmation Modal for Applying Decisions */}
      {showApplyModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0 border border-indigo-100">
                <CheckCircle2 className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900 text-sm">Apply Lifecycle Decisions?</h3>
                <p className="text-xs text-slate-500">Persistent database mutation</p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Applying these recommendations will execute state mutations across SQLite storage and synchronize the Qdrant Cloud semantic vector index:
            </p>

            {evalResult && (
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-1 font-mono text-slate-700">
                <div>KEEP: {evalResult.keep_count ?? evalResult.retained_count} records</div>
                <div>COMPRESS: {evalResult.compress_count ?? evalResult.summarized_count} records</div>
                <div>ARCHIVE: {evalResult.archived_count} records</div>
                <div>PRUNE: {evalResult.prune_count ?? evalResult.forgotten_count} records</div>
                <div className="text-indigo-600 font-bold">Estimated Token Savings: ~{evalResult.estimated_token_savings}</div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setShowApplyModal(false)}
                className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 text-xs font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmApply}
                disabled={isApplying}
                className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-xs disabled:opacity-50"
              >
                {isApplying ? 'Applying Mutations...' : 'Confirm & Apply'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
