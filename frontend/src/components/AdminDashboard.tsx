import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  Users,
  Database,
  Cpu,
  Activity,
  ArrowLeft,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Play,
  RotateCcw,
  Search,
  FileText
} from 'lucide-react';
import {
  api,
  AdminOverview,
  UserRecord,
  RLExperiment,
  AuditLogItem
} from '../api';

interface AdminDashboardProps {
  onBackToChat: () => void;
}

export const AdminDashboard: React.FC<AdminDashboardProps> = ({ onBackToChat }) => {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [experiments, setExperiments] = useState<RLExperiment[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [userSearch, setUserSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'overview' | 'users' | 'rl' | 'audit'>('overview');
  const [isTriggeringRL, setIsTriggeringRL] = useState(false);
  const [rlMessage, setRlMessage] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [ov, uList, expList, logs] = await Promise.all([
        api.getAdminOverview(),
        api.listAdminUsers(),
        api.listRLExperiments(),
        api.getAuditLogs(),
      ]);
      setOverview(ov);
      setUsers(uList);
      setExperiments(expList);
      setAuditLogs(logs);
    } catch (err) {
      console.error('Failed to load admin data:', err);
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
      setRlMessage(`Experiment ${exp.id.slice(0, 8)} completed. Mean Reward: ${exp.mean_reward}`);
      const updatedExp = await api.listRLExperiments();
      setExperiments(updatedExp);
    } catch (err: any) {
      setRlMessage(`Experiment failed: ${err.message}`);
    } finally {
      setIsTriggeringRL(false);
    }
  };

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-primary)' }}>
      {/* Top Header */}
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
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <ShieldCheck size={20} color="#fff" />
            </div>
            <div>
              <h1 style={{ fontSize: '1.1rem', fontWeight: 700 }}>System Administration Portal</h1>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Multi-Tenant Monitoring, Qdrant Vectors, Reinforcement Learning & Security Audits
              </p>
            </div>
          </div>
        </div>

        <button className="btn btn-secondary btn-sm" onClick={loadData}>
          <RotateCcw size={14} /> Refresh Metrics
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border-color)', padding: '0 24px', backgroundColor: 'var(--bg-secondary)' }}>
        {[
          { key: 'overview', label: 'System Overview', icon: Activity },
          { key: 'users', label: 'User Management', icon: Users },
          { key: 'rl', label: 'Reinforcement Learning', icon: Cpu },
          { key: 'audit', label: 'Security & Audit Logs', icon: FileText },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '12px 18px',
                background: 'none',
                border: 'none',
                borderBottom: isActive ? '2px solid var(--primary)' : '2px solid transparent',
                color: isActive ? '#fff' : 'var(--text-muted)',
                fontWeight: isActive ? 600 : 400,
                fontSize: '0.85rem',
                cursor: 'pointer',
              }}
            >
              <Icon size={16} color={isActive ? 'var(--primary)' : 'var(--text-sub)'} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Content Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px', maxWidth: '1200px', margin: '0 auto', width: '100%' }}>
        {/* OVERVIEW TAB */}
        {activeTab === 'overview' && overview && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Top Stat Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
              <div className="glass-panel" style={{ padding: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-sub)', fontWeight: 600 }}>REGISTERED USERS</span>
                  <Users size={16} color="var(--primary)" />
                </div>
                <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{overview.users.total}</div>
                <div style={{ fontSize: '0.75rem', color: '#34d399', marginTop: '4px' }}>
                  {overview.users.active} active accounts
                </div>
              </div>

              <div className="glass-panel" style={{ padding: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-sub)', fontWeight: 600 }}>ACTIVE MEMORIES</span>
                  <Database size={16} color="var(--accent)" />
                </div>
                <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{overview.memories.active}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  Total: {overview.memories.total} across tenants
                </div>
              </div>

              <div className="glass-panel" style={{ padding: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-sub)', fontWeight: 600 }}>COGNITIVE CONTEXT</span>
                  <Activity size={16} color="#c084fc" />
                </div>
                <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>~{overview.memories.estimated_active_tokens}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  Active tokens in context pool
                </div>
              </div>

              <div className="glass-panel" style={{ padding: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-sub)', fontWeight: 600 }}>PRUNED / FORGOTTEN</span>
                  <AlertTriangle size={16} color="#f87171" />
                </div>
                <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{overview.memories.forgotten}</div>
                <div style={{ fontSize: '0.75rem', color: '#fbbf24', marginTop: '4px' }}>
                  {overview.memories.archived} cold archived
                </div>
              </div>
            </div>

            {/* Subsystem Health Grid */}
            <div className="glass-panel" style={{ padding: '20px' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '14px' }}>Subsystem Health & Infrastructure</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                <div style={{ padding: '12px', borderRadius: 'var(--radius-md)', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>Google Gemini AI</span>
                    {overview.services.gemini_live ? <CheckCircle2 size={16} color="#34d399" /> : <AlertTriangle size={16} color="#fbbf24" />}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Model: {overview.services.model_configured} ({overview.services.gemini_live ? 'Live Inference' : 'Simulation Mode'})
                  </div>
                </div>

                <div style={{ padding: '12px', borderRadius: 'var(--radius-md)', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>Qdrant Vector DB</span>
                    {overview.services.qdrant_healthy ? <CheckCircle2 size={16} color="#34d399" /> : <XCircle size={16} color="#f87171" />}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Collection: {overview.services.qdrant_collection}
                  </div>
                </div>

                <div style={{ padding: '12px', borderRadius: 'var(--radius-md)', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>RL Decision Engine</span>
                    <CheckCircle2 size={16} color="#34d399" />
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Execution Mode: {overview.services.rl_mode.toUpperCase()} (LinUCB)
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* USERS TAB */}
        {activeTab === 'users' && (
          <div className="glass-panel" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Registered User Directory</h3>
              <div style={{ position: 'relative', width: '260px' }}>
                <Search size={14} color="var(--text-sub)" style={{ position: 'absolute', left: '10px', top: '10px' }} />
                <input
                  type="text"
                  className="input-field"
                  placeholder="Search user email or UID..."
                  value={userSearch}
                  onChange={async (e) => {
                    setUserSearch(e.target.value);
                    const res = await api.listAdminUsers(e.target.value);
                    setUsers(res);
                  }}
                  style={{ paddingLeft: '32px', fontSize: '0.8rem', height: '34px' }}
                />
              </div>
            </div>

            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-sub)', textAlign: 'left' }}>
                  <th style={{ padding: '10px' }}>User</th>
                  <th style={{ padding: '10px' }}>Role</th>
                  <th style={{ padding: '10px' }}>Status</th>
                  <th style={{ padding: '10px' }}>Registered</th>
                  <th style={{ padding: '10px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.uid} style={{ borderBottom: '1px solid rgba(148,163,184,0.1)' }}>
                    <td style={{ padding: '12px 10px' }}>
                      <div style={{ fontWeight: 600, color: '#fff' }}>{u.display_name || 'User'}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-sub)' }}>{u.email || u.uid}</div>
                    </td>
                    <td style={{ padding: '12px 10px' }}>
                      <span className={`badge ${u.role === 'admin' ? 'badge-pinned' : 'badge-active'}`}>
                        {u.role}
                      </span>
                    </td>
                    <td style={{ padding: '12px 10px' }}>
                      <span className={`badge ${u.status === 'active' ? 'badge-active' : 'badge-forgotten'}`}>
                        {u.status}
                      </span>
                    </td>
                    <td style={{ padding: '12px 10px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                    <td style={{ padding: '12px 10px', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleToggleRole(u.uid, u.role)}
                          title="Toggle Admin Privilege"
                        >
                          {u.role === 'admin' ? 'Demote' : 'Make Admin'}
                        </button>
                        <button
                          className={`btn ${u.status === 'active' ? 'btn-danger' : 'btn-primary'} btn-sm`}
                          onClick={() => handleToggleStatus(u.uid, u.status)}
                        >
                          {u.status === 'active' ? 'Disable' : 'Enable'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* RL TAB */}
        {activeTab === 'rl' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div>
                  <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Reinforcement Learning Optimization</h3>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Contextual Bandit policy (LinUCB) learning optimal retention, summarization, and pruning actions.
                  </p>
                </div>
                <button
                  className="btn btn-primary"
                  onClick={handleTriggerRL}
                  disabled={isTriggeringRL}
                >
                  <Play size={14} />
                  <span>{isTriggeringRL ? 'Training Policy...' : 'Run RL Experiment (50 Epochs)'}</span>
                </button>
              </div>

              {rlMessage && (
                <div style={{ padding: '10px 14px', borderRadius: 'var(--radius-md)', background: 'rgba(99,102,241,0.2)', border: '1px solid var(--border-focus)', fontSize: '0.85rem', color: '#c7d2fe', marginBottom: '14px' }}>
                  {rlMessage}
                </div>
              )}

              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-sub)', textAlign: 'left' }}>
                    <th style={{ padding: '8px' }}>Version</th>
                    <th style={{ padding: '8px' }}>Timestamp</th>
                    <th style={{ padding: '8px' }}>Iterations</th>
                    <th style={{ padding: '8px' }}>Mean Reward</th>
                    <th style={{ padding: '8px' }}>Crit Retention</th>
                    <th style={{ padding: '8px' }}>Storage Saved</th>
                    <th style={{ padding: '8px' }}>Safety Violations</th>
                  </tr>
                </thead>
                <tbody>
                  {experiments.map((exp) => (
                    <tr key={exp.id} style={{ borderBottom: '1px solid rgba(148,163,184,0.1)' }}>
                      <td style={{ padding: '10px 8px', fontWeight: 600 }}>{exp.policy_version}</td>
                      <td style={{ padding: '10px 8px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                        {new Date(exp.timestamp).toLocaleString()}
                      </td>
                      <td style={{ padding: '10px 8px' }}>{exp.iterations}</td>
                      <td style={{ padding: '10px 8px', color: '#34d399', fontWeight: 600 }}>
                        {exp.mean_reward}
                      </td>
                      <td style={{ padding: '10px 8px' }}>{exp.critical_retention_rate}%</td>
                      <td style={{ padding: '10px 8px', color: 'var(--accent)' }}>{exp.storage_reduction_rate}%</td>
                      <td style={{ padding: '10px 8px' }}>
                        <span className={`badge ${exp.safety_violations === 0 ? 'badge-active' : 'badge-forgotten'}`}>
                          {exp.safety_violations}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* AUDIT TAB */}
        {activeTab === 'audit' && (
          <div className="glass-panel" style={{ padding: '20px' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '14px' }}>Security & System Audit Log</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-sub)', textAlign: 'left' }}>
                  <th style={{ padding: '8px' }}>Timestamp</th>
                  <th style={{ padding: '8px' }}>Actor</th>
                  <th style={{ padding: '8px' }}>Action</th>
                  <th style={{ padding: '8px' }}>Target</th>
                  <th style={{ padding: '8px' }}>Details</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.map((log) => (
                  <tr key={log.id} style={{ borderBottom: '1px solid rgba(148,163,184,0.1)' }}>
                    <td style={{ padding: '8px', color: 'var(--text-sub)' }}>
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </td>
                    <td style={{ padding: '8px', fontWeight: 500 }}>{log.actor_uid}</td>
                    <td style={{ padding: '8px' }}>
                      <span className="badge badge-active">{log.action}</span>
                    </td>
                    <td style={{ padding: '8px', color: 'var(--text-muted)' }}>
                      {log.target_type}: {log.target_id}
                    </td>
                    <td style={{ padding: '8px', fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--text-sub)' }}>
                      {JSON.stringify(log.details)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
