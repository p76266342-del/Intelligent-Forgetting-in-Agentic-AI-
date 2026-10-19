import React, { useState, useEffect } from 'react';
import { api, UserRecord, getStoredToken, setAuthToken } from './api';
import { auth, onAuthStateChanged, fbSignOut } from './firebase';
import { ChatView } from './components/ChatView';
import { MemoryView } from './components/MemoryView';
import { AdminDashboard } from './components/AdminDashboard';
import { SettingsModal } from './components/SettingsModal';
import { AuthModal } from './components/AuthModal';

export const App: React.FC = () => {
  const [currentUser, setCurrentUser] = useState<UserRecord | null>(null);
  const [currentView, setCurrentView] = useState<'chat' | 'memories' | 'admin'>('chat');
  const [showSettings, setShowSettings] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isLoadingAuth, setIsLoadingAuth] = useState<boolean>(true);

  useEffect(() => {
    // 1. Check local stored token
    const token = getStoredToken();
    if (token) {
      loadProfile();
    } else {
      setIsLoadingAuth(false);
    }

    // 2. Firebase auth state listener
    const unsubscribe = onAuthStateChanged(auth, async (fbUser) => {
      if (fbUser) {
        const idToken = await fbUser.getIdToken();
        setAuthToken(idToken);
        loadProfile();
      }
    });

    return () => unsubscribe();
  }, []);

  const loadProfile = async () => {
    setIsLoadingAuth(true);
    try {
      const user = await api.getProfile();
      setCurrentUser(user);
      setIsAuthenticated(true);
    } catch (err) {
      console.error('Failed to load profile:', err);
      // If token invalid, clear it
      setAuthToken(null);
      setIsAuthenticated(false);
      setCurrentUser(null);
    } finally {
      setIsLoadingAuth(false);
    }
  };

  const handleLogout = async () => {
    try {
      await fbSignOut(auth);
    } catch (e) {
      // ignore
    }
    setAuthToken(null);
    setIsAuthenticated(false);
    setCurrentUser(null);
    setCurrentView('chat');
  };

  if (isLoadingAuth) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}>
        <div style={{ textAlign: 'center' }}>
          <div className="animate-pulse-glow" style={{ width: '40px', height: '40px', borderRadius: '50%', background: 'linear-gradient(135deg, #6366f1, #06b6d4)', margin: '0 auto 16px' }} />
          <div style={{ fontSize: '0.9rem', fontWeight: 500 }}>Initializing Intelligent Memory Platform...</div>
        </div>
      </div>
    );
  }

  return (
    <>
      {!isAuthenticated && (
        <AuthModal
          onSuccess={() => {
            loadProfile();
          }}
        />
      )}

      {isAuthenticated && (
        <>
          {currentView === 'chat' && (
            <ChatView
              user={currentUser}
              onOpenSettings={() => setShowSettings(true)}
              onOpenAdmin={() => setCurrentView('admin')}
              onOpenMemories={() => setCurrentView('memories')}
              onLogout={handleLogout}
            />
          )}

          {currentView === 'memories' && (
            <MemoryView onBackToChat={() => setCurrentView('chat')} />
          )}

          {currentView === 'admin' && (
            <AdminDashboard onBackToChat={() => setCurrentView('chat')} />
          )}

          {showSettings && (
            <SettingsModal
              user={currentUser}
              onClose={() => setShowSettings(false)}
              onUserUpdated={(u) => setCurrentUser(u)}
              onAccountDeleted={handleLogout}
            />
          )}
        </>
      )}
    </>
  );
};

export default App;
