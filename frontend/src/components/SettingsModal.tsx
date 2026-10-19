import React, { useState } from 'react';
import { X, User, Shield, AlertTriangle, Trash2, Check } from 'lucide-react';
import { api, UserRecord } from '../api';

interface SettingsModalProps {
  user: UserRecord | null;
  onClose: () => void;
  onUserUpdated: (u: UserRecord) => void;
  onAccountDeleted: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  user,
  onClose,
  onUserUpdated,
  onAccountDeleted,
}) => {
  const [displayName, setDisplayName] = useState(user?.display_name || '');
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateSuccess, setUpdateSuccess] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsUpdating(true);
    setUpdateSuccess(false);
    try {
      const updated = await api.updateProfile({ display_name: displayName });
      onUserUpdated(updated);
      setUpdateSuccess(true);
      setTimeout(() => setUpdateSuccess(false), 2000);
    } catch (err) {
      console.error('Failed to update profile:', err);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDeleteAccount = async () => {
    const confirmation = prompt(
      'WARNING: This will permanently delete your account, all conversations, messages, memories, and vector embeddings in Qdrant. Type "DELETE" to confirm:'
    );
    if (confirmation !== 'DELETE') return;

    setIsDeleting(true);
    try {
      await api.deleteAccount();
      alert('Your account and all associated data have been permanently deleted.');
      onAccountDeleted();
    } catch (err: any) {
      alert(`Deletion failed: ${err.message}`);
      setIsDeleting(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
    >
      <div
        className="glass-panel"
        style={{
          width: '100%',
          maxWidth: '520px',
          padding: '24px',
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '1.1rem' }}>
            <User size={18} color="var(--primary)" />
            <span>Account Settings & Privacy</span>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-sub)', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        {/* Profile Details Form */}
        <form onSubmit={handleUpdateProfile} style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '24px' }}>
          <div>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
              Email Address
            </label>
            <input
              type="text"
              className="input-field"
              value={user?.email || 'N/A'}
              disabled
              style={{ opacity: 0.6, cursor: 'not-allowed' }}
            />
          </div>

          <div>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
              Display Name
            </label>
            <input
              type="text"
              className="input-field"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-sub)' }}>
              Role: <strong style={{ color: '#fff' }}>{user?.role.toUpperCase()}</strong>
            </div>
            <button type="submit" className="btn btn-primary btn-sm" disabled={isUpdating}>
              {updateSuccess ? <Check size={14} /> : null}
              <span>{isUpdating ? 'Saving...' : updateSuccess ? 'Saved!' : 'Update Profile'}</span>
            </button>
          </div>
        </form>

        {/* Privacy & Deletion Section */}
        <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
            <AlertTriangle size={16} />
            <span>Danger Zone & GDPR Data Purge</span>
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-sub)', lineHeight: 1.5, marginBottom: '14px' }}>
            Permanent deletion purges all your private message history from SQLite storage and deletes all semantic vector embeddings associated with your UID from Qdrant.
          </p>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            onClick={handleDeleteAccount}
            disabled={isDeleting}
            style={{ width: '100%' }}
          >
            <Trash2 size={14} />
            <span>{isDeleting ? 'Purging all account data...' : 'Permanently Delete My Account & All Memories'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
