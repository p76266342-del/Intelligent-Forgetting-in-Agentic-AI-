import React, { useState, useEffect } from 'react';
import {
  Brain,
  Search,
  Pin,
  Trash2,
  Archive,
  RefreshCw,
  Plus,
  Shield,
  Clock,
  Activity,
  Layers,
  ArrowLeft,
  ChevronDown,
  Info
} from 'lucide-react';
import { api, Memory, ForgettingEvaluationResult } from '../api';

interface MemoryViewProps {
  onBackToChat: () => void;
}

export const MemoryView: React.FC<MemoryViewProps> = ({ onBackToChat }) => {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [isLoading, setIsLoading] = useState(false);
  const [evalResult, setEvalResult] = useState<ForgettingEvaluationResult | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);

  // New Memory Modal state
  const [showAddModal, setShowAddModal] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newImportance, setNewImportance] = useState(0.8);
  const [newCategory, setNewCategory] = useState('fact');
  const [newPinned, setNewPinned] = useState(false);

  useEffect(() => {
    loadMemories();
  }, [selectedStatus, selectedCategory]);

  const loadMemories = async () => {
    setIsLoading(true);
    try {
      const data = await api.listMemories(selectedStatus, selectedCategory);
      setMemories(data);
    } catch (err) {
      console.error('Failed to load memories:', err);
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
      const results = await api.searchMemories(searchQuery);
      setMemories(results);
    } catch (err) {
      console.error('Failed search:', err);
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
      loadMemories();
    } catch (err) {
      console.error('Failed to toggle pin:', err);
    }
  };

  const handleArchive = async (id: string) => {
    try {
      await api.archiveMemory(id);
      loadMemories();
    } catch (err) {
      console.error('Failed to archive:', err);
    }
  };

  const handleRestore = async (id: string) => {
    try {
      await api.restoreMemory(id);
      loadMemories();
    } catch (err) {
      console.error('Failed to restore:', err);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Permanently purge this memory from both SQLite and Qdrant vector index?')) return;
    try {
      await api.deleteMemory(id, true);
      loadMemories();
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  const handleRunEvaluation = async () => {
    setIsEvaluating(true);
    try {
      const res = await api.evaluateForgetting(true);
      setEvalResult(res);
    } catch (err) {
      console.error('Evaluation failed:', err);
    } finally {
      setIsEvaluating(false);
    }
  };

  const handleApplyEvaluation = async () => {
    if (!confirm('Apply recommended retention, summarization, archival, and forgetting operations?')) return;
    try {
      await api.applyForgetting();
      setEvalResult(null);
      loadMemories();
    } catch (err) {
      console.error('Failed to apply forgetting:', err);
    }
  };

  const handleCreateMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) return;
    try {
      await api.createMemory({
        content: newContent,
        importance: newImportance,
        category: newCategory,
        is_pinned: newPinned,
      });
      setShowAddModal(false);
      setNewContent('');
      loadMemories();
    } catch (err) {
      console.error('Failed to create memory:', err);
    }
  };

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-primary)' }}>
      {/* Top Navigation */}
      <div
        className="glass-nav"
        style={{
          padding: '16px 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <button onClick={onBackToChat} className="btn btn-secondary btn-sm" style={{ padding: '8px' }}>
            <ArrowLeft size={16} />
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'linear-gradient(135deg, #06b6d4, #6366f1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Brain size={20} color="#fff" />
            </div>
            <div>
              <h1 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Personal Memory Management</h1>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Inspect, pin, restore, or curate facts and preferences retained by your agent.
              </p>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button className="btn btn-secondary" onClick={handleRunEvaluation} disabled={isEvaluating}>
            <Activity size={16} color="var(--accent)" />
            <span>{isEvaluating ? 'Evaluating...' : 'Dry-Run Forgetting'}</span>
          </button>
          <button className="btn btn-primary" onClick={() => setShowAddModal(true)}>
            <Plus size={16} />
            <span>Add Memory</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px', maxWidth: '1200px', margin: '0 auto', width: '100%' }}>
        {/* Dry-Run Results Panel if triggered */}
        {evalResult && (
          <div
            className="glass-panel animate-fade-in"
            style={{
              padding: '20px',
              marginBottom: '24px',
              border: '1px solid rgba(6, 182, 212, 0.4)',
              background: 'rgba(15, 23, 42, 0.85)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent)', fontWeight: 600 }}>
                <Activity size={18} />
                <span>Dry-Run Evaluation Preview (Non-Mutating)</span>
              </div>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button className="btn btn-primary btn-sm" onClick={handleApplyEvaluation}>
                  Apply Recommended Actions
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => setEvalResult(null)}>
                  Dismiss
                </button>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '12px', marginBottom: '16px' }}>
              <div className="glass-panel" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)' }}>RETAINED</div>
                <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#34d399' }}>{evalResult.retained_count}</div>
              </div>
              <div className="glass-panel" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)' }}>SUMMARIZED</div>
                <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#38bdf8' }}>{evalResult.summarized_count}</div>
              </div>
              <div className="glass-panel" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)' }}>ARCHIVED</div>
                <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#fbbf24' }}>{evalResult.archived_count}</div>
              </div>
              <div className="glass-panel" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)' }}>PRUNED / FORGOTTEN</div>
                <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#f87171' }}>{evalResult.forgotten_count}</div>
              </div>
              <div className="glass-panel" style={{ padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)' }}>SAVED TOKENS</div>
                <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--accent)' }}>~{evalResult.estimated_token_savings}</div>
              </div>
            </div>
          </div>
        )}

        {/* Filter Controls */}
        <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
          <form onSubmit={handleSearch} style={{ flex: 1, minWidth: '280px', display: 'flex', gap: '8px' }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <Search size={16} color="var(--text-sub)" style={{ position: 'absolute', left: '12px', top: '12px' }} />
              <input
                type="text"
                className="input-field"
                placeholder="Semantic vector search across memories..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ paddingLeft: '38px' }}
              />
            </div>
            <button type="submit" className="btn btn-primary">Search</button>
          </form>

          <select
            className="input-field"
            style={{ width: '180px' }}
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
          >
            <option value="ALL">All Statuses</option>
            <option value="active">Active</option>
            <option value="summarized">Summarized</option>
            <option value="archived">Archived</option>
            <option value="forgotten">Forgotten</option>
          </select>

          <select
            className="input-field"
            style={{ width: '180px' }}
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
          >
            <option value="ALL">All Categories</option>
            <option value="fact">Fact</option>
            <option value="preference">Preference</option>
            <option value="task_context">Task Context</option>
            <option value="conversation">Conversation</option>
            <option value="general">General</option>
          </select>
        </div>

        {/* Memories Grid */}
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>
            <RefreshCw className="animate-spin" size={24} style={{ margin: '0 auto 12px' }} />
            <div>Loading personalized memories...</div>
          </div>
        ) : memories.length === 0 ? (
          <div className="glass-panel" style={{ padding: '60px 20px', textAlign: 'center' }}>
            <Brain size={48} color="var(--text-sub)" style={{ margin: '0 auto 16px' }} />
            <h3 style={{ fontSize: '1.1rem', marginBottom: '8px' }}>No Memories Found</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', maxWidth: '400px', margin: '0 auto 20px' }}>
              Memories are automatically created as you chat with the AI, or you can manually save important facts or preferences.
            </p>
            <button className="btn btn-primary" onClick={() => setShowAddModal(true)}>
              <Plus size={16} />
              <span>Add Your First Memory</span>
            </button>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '16px' }}>
            {memories.map((mem) => (
              <div
                key={mem.id}
                className="glass-panel"
                style={{
                  padding: '16px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  border: mem.is_pinned ? '1px solid rgba(168, 85, 247, 0.4)' : '1px solid var(--border-color)',
                  position: 'relative',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <span className={`badge badge-${mem.retention_status}`}>{mem.retention_status}</span>
                      <span className="badge" style={{ background: 'rgba(148, 163, 184, 0.1)', color: '#94a3b8' }}>
                        {mem.category}
                      </span>
                      {mem.is_pinned && <span className="badge badge-pinned"><Pin size={10} /> Pinned</span>}
                      {mem.is_critical && <span className="badge" style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#f87171' }}><Shield size={10} /> Critical</span>}
                    </div>

                    <div style={{ display: 'flex', gap: '4px' }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ padding: '4px 6px', color: mem.is_pinned ? '#c084fc' : 'var(--text-muted)' }}
                        onClick={() => handleTogglePin(mem)}
                        title={mem.is_pinned ? 'Unpin' : 'Pin Memory'}
                      >
                        <Pin size={13} />
                      </button>
                      {mem.retention_status === 'archived' ? (
                        <button
                          className="btn btn-secondary btn-sm"
                          style={{ padding: '4px 6px', color: '#34d399' }}
                          onClick={() => handleRestore(mem.id)}
                          title="Restore to Active"
                        >
                          <RefreshCw size={13} />
                        </button>
                      ) : (
                        <button
                          className="btn btn-secondary btn-sm"
                          style={{ padding: '4px 6px', color: '#fbbf24' }}
                          onClick={() => handleArchive(mem.id)}
                          title="Archive Memory"
                        >
                          <Archive size={13} />
                        </button>
                      )}
                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ padding: '4px 6px', color: '#f87171' }}
                        onClick={() => handleDelete(mem.id)}
                        title="Delete Permanently"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>

                  <p style={{ fontSize: '0.9rem', lineHeight: 1.5, color: '#f1f5f9', marginBottom: '12px' }}>
                    {mem.content}
                  </p>
                </div>

                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '10px', marginTop: '10px', fontSize: '0.72rem', color: 'var(--text-sub)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span>Importance: {(mem.importance * 100).toFixed(0)}%</span>
                    <span>Accesses: {mem.access_count}</span>
                  </div>
                  {mem.retention_score !== undefined && mem.retention_score !== null && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>Retention Score:</span>
                      <span style={{ fontWeight: 600, color: mem.retention_score >= 0.45 ? '#34d399' : mem.retention_score >= 0.25 ? '#fbbf24' : '#f87171' }}>
                        {(mem.retention_score * 100).toFixed(1)}%
                      </span>
                    </div>
                  )}
                  <div style={{ marginTop: '4px', fontSize: '0.68rem', color: 'var(--text-sub)' }}>
                    Created: {new Date(mem.created_at).toLocaleDateString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Manual Add Memory Modal */}
      {showAddModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div className="glass-panel" style={{ width: '100%', maxWidth: '500px', padding: '24px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '16px' }}>Add New Memory</h3>
            <form onSubmit={handleCreateMemory} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px', display: 'block' }}>Content</label>
                <textarea
                  className="input-field"
                  rows={3}
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  placeholder="e.g. User prefers concise bullet points for project roadmaps"
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px', display: 'block' }}>Category</label>
                  <select className="input-field" value={newCategory} onChange={(e) => setNewCategory(e.target.value)}>
                    <option value="fact">Fact</option>
                    <option value="preference">Preference</option>
                    <option value="task_context">Task Context</option>
                    <option value="general">General</option>
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px', display: 'block' }}>
                    Importance: {(newImportance * 100).toFixed(0)}%
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={newImportance}
                    onChange={(e) => setNewImportance(parseFloat(e.target.value))}
                    style={{ width: '100%', marginTop: '8px' }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="checkbox"
                  id="pinCheck"
                  checked={newPinned}
                  onChange={(e) => setNewPinned(e.target.checked)}
                />
                <label htmlFor="pinCheck" style={{ fontSize: '0.8rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
                  Pin this memory (guarantee immune from automated forgetting)
                </label>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '12px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowAddModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Save Memory</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
