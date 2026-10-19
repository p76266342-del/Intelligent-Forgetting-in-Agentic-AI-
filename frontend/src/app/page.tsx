'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import {
  Brain,
  Sparkles,
  Zap,
  ShieldCheck,
  Database,
  Sliders,
  ArrowRight,
  CheckCircle2,
  Minimize2,
  Archive,
  Trash2,
  Cpu,
} from 'lucide-react';

export default function LandingPage() {
  const { profile } = useAuth();
  const [activeCycleTab, setActiveCycleTab] = useState<'keep' | 'compress' | 'archive' | 'prune'>('keep');

  const lifecycleDetails = {
    keep: {
      action: 'KEEP (Retain in Active Working Memory)',
      badgeClass: 'bg-emerald-50 text-emerald-800 border-emerald-200',
      icon: CheckCircle2,
      condition: 'Score > Retention Threshold OR Memory is Pinned/Critical',
      description:
        'Essential guidelines, active task constraints, user preferences, and frequently retrieved items are preserved in prime context with priority attention weights.',
      example: 'User preference: Always deploy database migrations with SSL and backward-compatible schemas.',
      tokenImpact: 'Zero loss of critical information. Intact working memory context.',
    },
    compress: {
      action: 'COMPRESS (Synthesize Redundant Clusters)',
      badgeClass: 'bg-purple-50 text-purple-800 border-purple-200',
      icon: Minimize2,
      condition: 'Jaccard Token Similarity ≥ 0.65 across multiple active records',
      description:
        'Duplicate or highly overlapping instructions across conversations are distilled into concise consolidated memories, reducing redundant context token overhead by up to 88%.',
      example: 'Merged 4 variations of "Deploy Kubernetes cluster with 3 replicas" into 1 synthesized directive.',
      tokenImpact: 'Drastic context window reduction without discarding underlying domain knowledge.',
    },
    archive: {
      action: 'ARCHIVE (Demote to Durable Storage)',
      badgeClass: 'bg-amber-50 text-amber-800 border-amber-200',
      icon: Archive,
      condition: 'Forget Threshold ≤ Score < Archive Threshold',
      description:
        'Older contextual observations, intermediate meeting logs, and less frequent interactions are removed from LLM active prompt tokens, but safely indexed for on-demand semantic search in Qdrant.',
      example: 'Historical project plan discussed 3 weeks ago; retrieved only if relevant query arises.',
      tokenImpact: 'Immediate prompt token savings while preserving historical provenance.',
    },
    prune: {
      action: 'PRUNE (Intelligent Cognitive Forgetting)',
      badgeClass: 'bg-rose-50 text-rose-800 border-rose-200',
      icon: Trash2,
      condition: 'Score < Forget Threshold (Decayed, unpinned, ephemeral chatter)',
      description:
        'Ephemeral scratchpad calculations, temporary tool output traces, and transient conversational noise are gracefully purged according to safety policies, mimicking biological forgetting.',
      example: 'Transient debug traces, temporary weather queries, or single-use scratchpad variables.',
      tokenImpact: 'Eliminates attention distraction and prevents working memory bloat.',
    },
  };

  const activeInfo = lifecycleDetails[activeCycleTab];
  const IconComp = activeInfo.icon;

  return (
    <div className="flex-1 h-full min-h-0 overflow-y-auto p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto w-full space-y-10">
      {/* Hero Section */}
      <section className="pt-6 sm:pt-10 text-center space-y-5">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold shadow-xs">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Reinforcement Learning & Vector Memory Engine</span>
        </div>

        <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-slate-900 leading-tight">
          Intelligent Forgetting in <br />
          <span className="text-indigo-600">Agentic AI Systems</span>
        </h1>

        <p className="max-w-2xl mx-auto text-sm sm:text-base text-slate-600 leading-relaxed">
          Autonomous AI agents cannot retain everything indefinitely. Our mathematical multi-factor
          memory engine dynamically evaluates importance, recency, frequency, and relevance—selectively
          retaining, summarizing, archiving, and pruning memories to optimize prompt token budgets.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
          {profile ? (
            <Link
              href="/chat"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-xs transition-colors"
            >
              Open AI Chat Workspace
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          ) : (
            <>
              <Link
                href="/signup"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-xs transition-colors"
              >
                Create Account
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
              <Link
                href="/login"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-semibold text-xs shadow-xs transition-colors"
              >
                Sign In
              </Link>
            </>
          )}
          <Link
            href="/memories"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-semibold text-xs shadow-xs transition-colors"
          >
            <Brain className="w-3.5 h-3.5 text-indigo-600" />
            <span>Explore Memory Engine</span>
          </Link>
        </div>
      </section>

      {/* Memory Lifecycle Visualizer */}
      <section className="bg-white border border-slate-200 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xs">
        <div className="text-center space-y-1.5">
          <span className="text-[11px] uppercase font-bold tracking-wider text-indigo-600">
            Cognitive Architecture
          </span>
          <h2 className="text-xl sm:text-2xl font-bold text-slate-900">
            The 4-Stage Memory Lifecycle
          </h2>
          <p className="text-xs text-slate-500 max-w-xl mx-auto">
            Inspect how the engine classifies every memory item based on composite mathematical retention scores.
          </p>
        </div>

        {/* Interactive Tabs */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-50 p-1.5 rounded-xl border border-slate-200">
          {(['keep', 'compress', 'archive', 'prune'] as const).map((key) => {
            const tab = lifecycleDetails[key];
            const Icon = tab.icon;
            const isSelected = activeCycleTab === key;
            return (
              <button
                key={key}
                onClick={() => setActiveCycleTab(key)}
                className={`flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition-colors ${
                  isSelected
                    ? 'bg-white text-slate-900 border border-slate-200 shadow-xs'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{key}</span>
              </button>
            );
          })}
        </div>

        {/* Active Lifecycle Details Card */}
        <div className="p-5 rounded-xl bg-slate-50 border border-slate-200 space-y-3.5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200/80 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-indigo-600 shadow-xs">
                <IconComp className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900 text-xs sm:text-sm">
                  {activeInfo.action}
                </h3>
                <span className="text-[11px] font-mono text-slate-500">
                  Policy Trigger: {activeInfo.condition}
                </span>
              </div>
            </div>
          </div>

          <p className="text-xs sm:text-sm text-slate-700 leading-relaxed">
            {activeInfo.description}
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1 text-xs">
            <div className="p-3 rounded-lg bg-white border border-slate-200 space-y-1 shadow-xs">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                Typical Application
              </span>
              <p className="text-slate-700 italic">
                &ldquo;{activeInfo.example}&rdquo;
              </p>
            </div>
            <div className="p-3 rounded-lg bg-white border border-slate-200 space-y-1 shadow-xs">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                Context Token Benefit
              </span>
              <p className="text-slate-700">
                {activeInfo.tokenImpact}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Architecture Grid */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-2 shadow-xs">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100">
            <Sliders className="w-4 h-4" />
          </div>
          <h3 className="font-semibold text-slate-900 text-sm">
            Mathematical Scoring
          </h3>
          <p className="text-xs text-slate-500 leading-relaxed">
            Integrates intrinsic importance, exponential recency decay (72h half-life),
            logarithmic frequency saturation, and task-specific relevance matching.
          </p>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-2 shadow-xs">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100">
            <Database className="w-4 h-4" />
          </div>
          <h3 className="font-semibold text-slate-900 text-sm">
            Qdrant Dense Vectors
          </h3>
          <p className="text-xs text-slate-500 leading-relaxed">
            Hybrid dense embeddings (FastEmbed ONNX) and lexical filtering with strict
            per-user tenant boundary verification on every search query.
          </p>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-2 shadow-xs">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100">
            <Cpu className="w-4 h-4" />
          </div>
          <h3 className="font-semibold text-slate-900 text-sm">
            Reinforcement Learning
          </h3>
          <p className="text-xs text-slate-500 leading-relaxed">
            LinUCB contextual bandit policy optimizing multi-objective reward trade-offs between
            token economy, retrieval precision, and critical memory safety.
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-auto py-6 border-t border-slate-200 text-center text-xs text-slate-400">
        <p>
          Intelligent Forgetting in Agentic AI &bull; Next.js + FastAPI + Firebase + Gemini + Qdrant
        </p>
      </footer>
    </div>
  );
}
