'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { api, Memory, UserMemoryStats } from '@/lib/api';
import {
  Layers,
  Search,
  Pin,
  Trash2,
  Archive,
  RefreshCw,
  Plus,
  Shield,
  Clock,
  RotateCcw,
  Sparkles,
  Sliders,
  Filter,
  Check,
  X,
  AlertTriangle,
  Brain,
  Edit3,
} from 'lucide-react';

export default function MemoryExplorerPage() {
  const router = useRouter();
  const { profile, loading: authLoading } = useAuth();

  const [memories, setMemories] = useState<Memory[]>([]);
  const [memoryStats, setMemoryStats] = useState<UserMemoryStats | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // New Memory Modal state
  const [showAddModal, setShowAddModal] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newImportance, setNewImportance] = useState(0.5);
  const [newCategory, setNewCategory] = useState('fact');
  const [newPinned, setNewPinned] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Edit Memory Modal state
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [editImportance, setEditImportance] = useState<number>(0.5);
  const [editContent, setEditContent] = useState<string>('');

  // Delete Confirmation Modal state
  const [deletingMemoryId, setDeletingMemoryId] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !profile) {
      router.push('/login');
    }
  }, [profile, authLoading, router]);

  useEffect(() => {
    if (profile) {
      loadMemories();
      loadMemoryStats();
    }
  }, [profile, selectedStatus, selectedCategory]);

  const loadMemoryStats = async () => {
    try {
      const stats = await api.getMemoryStats();
      setMemoryStats(stats);
    } catch (err) {
      console.error('Failed to load memory stats:', err);
    }
  };

  const loadMemories = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await api.listMemories(selectedStatus, selectedCategory);
      setMemories(data);
    } catch (err: any) {
      console.error('Failed to load memories:', err);
      setErrorMessage(err?.message || 'Failed to load memories.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      loadMemories();
      return;
    }
    setIsLoading(true);
    try {
      const results = await api.searchMemories(searchQuery.trim());
      setMemories(results);
    } catch (err: any) {
      console.error('Search failed:', err);
      setErrorMessage(err?.message || 'Vector semantic search failed.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleTogglePin = async (mem: Memory) => {
    try {
      if (mem.is_pinned) {
        await api.unpinMemory(mem.id);
      } else {
        await api.pinMemory(mem.id);
      }
      await loadMemories();
      await loadMemoryStats();
    } catch (err: any) {
      console.error('Failed to toggle pin:', err);
      setErrorMessage(err?.message || 'Failed to toggle pin status.');
    }
  };

  const handleArchive = async (id: string) => {
    try {
      await api.archiveMemory(id, 'User requested archival');
      setSuccessMessage('Memory archived to cold storage.');
      setTimeout(() => setSuccessMessage(null), 3000);
      await loadMemories();
      await loadMemoryStats();
    } catch (err: any) {
      console.error('Failed to archive:', err);
      setErrorMessage(err?.message || 'Failed to archive memory.');
    }
  };

  const handleRestore = async (id: string) => {
    try {
      await api.restoreMemory(id);
      setSuccessMessage('Memory restored to active working context.');
      setTimeout(() => setSuccessMessage(null), 3000);
      await loadMemories();
      await loadMemoryStats();
    } catch (err: any) {
      console.error('Failed to restore:', err);
      setErrorMessage(err?.message || 'Failed to restore memory.');
    }
  };

  const confirmDelete = async () => {
    if (!deletingMemoryId) return;
    try {
      await api.deleteMemory(deletingMemoryId, true);
      setDeletingMemoryId(null);
      setSuccessMessage('Memory permanently pruned.');
      setTimeout(() => setSuccessMessage(null), 3000);
      await loadMemories();
      await loadMemoryStats();
    } catch (err: any) {
      console.error('Failed to delete memory:', err);
      setErrorMessage(err?.message || 'Failed to permanently prune memory.');
    }
  };

  const handleCreateMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) return;
    setIsSubmitting(true);
    try {
      await api.createMemory({
        content: newContent.trim(),
        importance: newImportance,
        category: newCategory,
        is_pinned: newPinned,
      });
      setShowAddModal(false);
      setNewContent('');
      setNewImportance(0.5);
      setNewPinned(false);
      setSuccessMessage('Memory created and indexed into Qdrant.');
      setTimeout(() => setSuccessMessage(null), 3000);
      await loadMemories();
      await loadMemoryStats();
    } catch (err: any) {
      console.error('Failed to create memory:', err);
      setErrorMessage(err?.message || 'Failed to create memory.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!editingMemory) return;
    setIsSubmitting(true);
    try {
      if (editImportance !== editingMemory.importance) {
        await api.updateImportance(editingMemory.id, editImportance);
      }
      if (editContent.trim() && editContent !== editingMemory.content) {
        await api.updateMemory(editingMemory.id, { content: editContent.trim() });
      }
      setEditingMemory(null);
      setSuccessMessage('Memory record updated.');
      setTimeout(() => setSuccessMessage(null), 3000);
      await loadMemories();
      await loadMemoryStats();
    } catch (err: any) {
      console.error('Failed to update memory:', err);
      setErrorMessage(err?.message || 'Failed to update memory.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (authLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-slate-400">
        <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Real counts strictly derived from stats or filtered array
  const activeCount = memoryStats
    ? memoryStats.active_count
    : memories.filter((m) => m.retention_status === 'active').length;
  const summarizedCount = memoryStats
    ? memoryStats.summarized_count
    : memories.filter((m) => m.retention_status === 'summarized').length;
  const archivedCount = memoryStats
    ? memoryStats.archived_count
    : memories.filter((m) => m.retention_status === 'archived').length;
  const protectedCount = memoryStats
    ? memoryStats.pinned_count + memoryStats.critical_count + memoryStats.permanent_count
    : memories.filter((m) => m.is_pinned || m.is_critical || m.retention_status === 'permanent').length;

  return (
    <div className="flex-1 h-full min-h-0 overflow-y-auto p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full space-y-6">
      
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Layers className="w-6 h-6 text-indigo-600" />
            <span>Memory Explorer</span>
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            Real-time cognitive memory bank indexed by Qdrant vector embeddings and mathematical retention decay.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => loadMemories()}
            className="p-2 text-slate-500 hover:text-slate-800 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors"
            title="Refresh memory list"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Add Memory</span>
          </button>
        </div>
      </div>

      {/* Alert Notices */}
      {errorMessage && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            <span className="font-medium">{errorMessage}</span>
          </div>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-rose-600 hover:text-rose-800 text-xs font-semibold"
          >
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
          <button
            onClick={() => setSuccessMessage(null)}
            className="text-emerald-600 hover:text-emerald-800 text-xs font-semibold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Compact Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex items-center gap-3 shadow-xs">
          <div className="w-9 h-9 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center font-bold text-sm shrink-0 border border-emerald-100">
            {activeCount}
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">Active</span>
            <span className="text-xs text-slate-700 truncate block">In working prompt</span>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex items-center gap-3 shadow-xs">
          <div className="w-9 h-9 rounded-lg bg-purple-50 text-purple-700 flex items-center justify-center font-bold text-sm shrink-0 border border-purple-100">
            {summarizedCount}
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">Summarized</span>
            <span className="text-xs text-slate-700 truncate block">Synthesized clusters</span>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex items-center gap-3 shadow-xs">
          <div className="w-9 h-9 rounded-lg bg-amber-50 text-amber-700 flex items-center justify-center font-bold text-sm shrink-0 border border-amber-100">
            {archivedCount}
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">Archived</span>
            <span className="text-xs text-slate-700 truncate block">Cold Qdrant storage</span>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex items-center gap-3 shadow-xs">
          <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-700 flex items-center justify-center font-bold text-sm shrink-0 border border-indigo-100">
            {protectedCount}
          </div>
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">Protected</span>
            <span className="text-xs text-slate-700 truncate block">Pinned / Critical</span>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-3 space-y-3 shadow-xs">
        <div className="grid grid-cols-1 sm:grid-cols-12 gap-2.5">
          {/* Search Box */}
          <form onSubmit={handleSearch} className="sm:col-span-6 relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search memories via semantic dense retrieval..."
              className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white"
            />
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
          </form>

          {/* Status Filter */}
          <div className="sm:col-span-3">
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="w-full px-2.5 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-700 focus:outline-none focus:border-indigo-500"
            >
              <option value="ALL">Status: All (Excl. Forgotten)</option>
              <option value="active">Active Only</option>
              <option value="archived">Archived</option>
              <option value="summarized">Summarized</option>
              <option value="permanent">Permanent / Pinned</option>
            </select>
          </div>

          {/* Category Filter */}
          <div className="sm:col-span-3">
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="w-full px-2.5 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-700 focus:outline-none focus:border-indigo-500"
            >
              <option value="ALL">Category: All</option>
              <option value="fact">Fact</option>
              <option value="preference">Preference</option>
              <option value="conversation">Conversation</option>
              <option value="task_context">Task Context</option>
            </select>
          </div>
        </div>
      </div>

      {/* Memory List */}
      <div className="space-y-2.5">
        {isLoading ? (
          <div className="py-16 text-center text-xs text-slate-400 flex flex-col items-center gap-2">
            <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
            <span>Loading cognitive memories...</span>
          </div>
        ) : memories.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-xs text-slate-500 space-y-2 shadow-xs">
            <Layers className="w-8 h-8 text-slate-300 mx-auto" />
            <p className="font-semibold text-slate-700 text-sm">No memories found</p>
            <p className="text-slate-400 max-w-sm mx-auto">
              No memory records match the selected filters or search query. Click &ldquo;Add Memory&rdquo; to insert a new knowledge item.
            </p>
          </div>
        ) : (
          memories.map((mem) => {
            const statusBadge =
              mem.retention_status === 'active'
                ? 'badge-active'
                : mem.retention_status === 'archived'
                ? 'badge-archived'
                : mem.retention_status === 'summarized'
                ? 'badge-summarized'
                : 'badge-forgotten';

            return (
              <div
                key={mem.id}
                className="bg-white border border-slate-200 hover:border-slate-300 rounded-xl p-4 space-y-3 shadow-xs transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1.5 flex-1 min-w-0">
                    {/* Badges line */}
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded ${statusBadge}`}>
                        {mem.retention_status}
                      </span>
                      <span className="text-[10px] uppercase font-semibold text-slate-700 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                        {mem.category}
                      </span>
                      {mem.is_pinned && (
                        <span className="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded flex items-center gap-1">
                          <Pin className="w-3 h-3" /> Pinned
                        </span>
                      )}
                      {mem.is_critical && (
                        <span className="text-[10px] font-bold text-rose-700 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded flex items-center gap-1">
                          <Shield className="w-3 h-3" /> Critical
                        </span>
                      )}
                      {mem.tags?.map((t) => (
                        <span key={t} className="text-[9px] text-slate-500 bg-slate-50 border border-slate-200 px-1.5 py-0.5 rounded">
                          #{t}
                        </span>
                      ))}
                    </div>

                    {/* Content */}
                    <p className="text-xs sm:text-sm text-slate-800 leading-relaxed font-normal">
                      {mem.content}
                    </p>
                  </div>

                  {/* Contextual Actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => handleTogglePin(mem)}
                      className={`p-1.5 rounded-lg border border-transparent hover:border-slate-200 hover:bg-slate-50 transition-colors ${
                        mem.is_pinned ? 'text-amber-500' : 'text-slate-400 hover:text-slate-700'
                      }`}
                      title={mem.is_pinned ? 'Unpin memory' : 'Pin memory'}
                    >
                      <Pin className="w-3.5 h-3.5" />
                    </button>

                    <button
                      onClick={() => {
                        setEditingMemory(mem);
                        setEditImportance(mem.importance);
                        setEditContent(mem.content);
                      }}
                      className="p-1.5 rounded-lg border border-transparent hover:border-slate-200 hover:bg-slate-50 text-slate-400 hover:text-slate-700 transition-colors"
                      title="Edit importance & content"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                    </button>

                    {mem.retention_status === 'active' ? (
                      <button
                        onClick={() => handleArchive(mem.id)}
                        className="p-1.5 rounded-lg border border-transparent hover:border-slate-200 hover:bg-slate-50 text-slate-400 hover:text-amber-600 transition-colors"
                        title="Demote to Archive"
                      >
                        <Archive className="w-3.5 h-3.5" />
                      </button>
                    ) : mem.retention_status === 'archived' ? (
                      <button
                        onClick={() => handleRestore(mem.id)}
                        className="p-1.5 rounded-lg border border-transparent hover:border-slate-200 hover:bg-slate-50 text-slate-400 hover:text-emerald-600 transition-colors"
                        title="Restore to Active context"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                      </button>
                    ) : null}

                    <button
                      onClick={() => setDeletingMemoryId(mem.id)}
                      className="p-1.5 rounded-lg border border-transparent hover:border-slate-200 hover:bg-rose-50 text-slate-400 hover:text-rose-600 transition-colors"
                      title="Permanently prune"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Score & Provenance Metadata Line */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 pt-2 border-t border-slate-100 text-[11px] text-slate-500">
                  <div>
                    <span className="text-[10px] uppercase font-medium text-slate-400 block">Retention Score</span>
                    <span className="font-mono font-semibold text-slate-900">
                      {mem.retention_score ? mem.retention_score.toFixed(3) : 'Active'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-medium text-slate-400 block">Importance</span>
                    <span className="font-mono text-slate-700">{mem.importance.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-medium text-slate-400 block">Accesses</span>
                    <span className="font-mono text-slate-700">{mem.access_count}</span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-medium text-slate-400 block">Recorded</span>
                    <span className="text-slate-600">{new Date(mem.created_at).toLocaleDateString()}</span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-medium text-slate-400 block">Est. Tokens</span>
                    <span className="font-mono text-slate-700">~{Math.max(1, Math.floor(mem.content.length / 4))}</span>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Add Memory Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-semibold text-slate-900 text-sm">Add New Memory</h3>
              <button onClick={() => setShowAddModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateMemory} className="space-y-4 text-xs">
              <div className="space-y-1">
                <label className="font-medium text-slate-700">Content</label>
                <textarea
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  placeholder="Enter the factual statement, preference, or context..."
                  rows={3}
                  required
                  className="w-full p-2.5 rounded-lg border border-slate-200 bg-slate-50 text-slate-900 focus:outline-none focus:border-indigo-500 focus:bg-white resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="font-medium text-slate-700">Category</label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    className="w-full p-2 rounded-lg border border-slate-200 bg-slate-50 text-slate-800 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="fact">Fact</option>
                    <option value="preference">Preference</option>
                    <option value="conversation">Conversation</option>
                    <option value="task_context">Task Context</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <div className="flex justify-between items-center">
                    <label className="font-medium text-slate-700">Importance</label>
                    <span className="font-mono text-slate-500">{newImportance.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={newImportance}
                    onChange={(e) => setNewImportance(parseFloat(e.target.value))}
                    className="w-full accent-indigo-600 mt-2"
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="pinCheck"
                  checked={newPinned}
                  onChange={(e) => setNewPinned(e.target.checked)}
                  className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="pinCheck" className="text-slate-700 select-none cursor-pointer">
                  Pin memory (exempt from automated forgetting decay)
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || !newContent.trim()}
                  className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium shadow-xs disabled:opacity-50"
                >
                  {isSubmitting ? 'Saving...' : 'Save Memory'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Memory Modal */}
      {editingMemory && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-semibold text-slate-900 text-sm">Edit Memory Record</h3>
              <button onClick={() => setEditingMemory(null)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div className="space-y-1">
                <label className="font-medium text-slate-700">Content</label>
                <textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  rows={3}
                  className="w-full p-2.5 rounded-lg border border-slate-200 bg-slate-50 text-slate-900 focus:outline-none focus:border-indigo-500 focus:bg-white resize-none"
                />
              </div>

              <div className="space-y-1">
                <div className="flex justify-between items-center">
                  <label className="font-medium text-slate-700">Importance Weight</label>
                  <span className="font-mono text-indigo-600 font-semibold">{editImportance.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={editImportance}
                  onChange={(e) => setEditImportance(parseFloat(e.target.value))}
                  className="w-full accent-indigo-600 mt-2"
                />
                <span className="text-[10px] text-slate-400">
                  Higher importance weights increase the memory&apos;s mathematical retention score.
                </span>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setEditingMemory(null)}
                  className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveEdit}
                  disabled={isSubmitting}
                  className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium shadow-xs disabled:opacity-50"
                >
                  {isSubmitting ? 'Saving...' : 'Update Record'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete / Permanent Prune Confirmation Modal */}
      {deletingMemoryId && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-rose-200 rounded-2xl max-w-md w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center shrink-0 border border-rose-100">
                <Trash2 className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900 text-sm">Permanent Prune Confirmation</h3>
                <p className="text-xs text-slate-500">This action cannot be undone.</p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Are you sure you want to permanently delete this memory? It will be immediately purged from
              authoritative SQLite storage and its semantic embedding removed from the Qdrant index.
            </p>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setDeletingMemoryId(null)}
                className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 text-xs"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold shadow-xs"
              >
                Permanently Delete
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
