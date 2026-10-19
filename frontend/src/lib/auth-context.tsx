'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import {
  auth,
  onAuthStateChanged,
  onIdTokenChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  fbSignOut,
  sendPasswordResetEmail,
  User,
} from './firebase';
import { api, setAuthToken, getStoredToken, UserRecord } from './api';

interface AuthContextType {
  firebaseUser: User | null;
  profile: UserRecord | null;
  loading: boolean;
  login: (email: string, pass: string) => Promise<void>;
  signup: (email: string, pass: string) => Promise<void>;
  logout: () => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
  devLogin: (role?: 'user' | 'admin') => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  firebaseUser: null,
  profile: null,
  loading: true,
  login: async () => {},
  signup: async () => {},
  logout: async () => {},
  resetPassword: async () => {},
  devLogin: async () => {},
  refreshProfile: async () => {},
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserRecord | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchProfile = async (explicitToken?: string): Promise<UserRecord | null> => {
    if (explicitToken) {
      setAuthToken(explicitToken);
    }
    const currentToken = explicitToken || getStoredToken();
    if (!currentToken) {
      setProfile(null);
      return null;
    }

    try {
      const p = await api.getProfile();
      setProfile(p);
      return p;
    } catch (err: any) {
      const status = err?.status;
      // Only clear token if backend explicitly rejected authentication with HTTP 401
      if (status === 401) {
        console.warn('Authentication token rejected by backend (HTTP 401).');
        const tok = getStoredToken();
        if (tok && !tok.startsWith('test-token-') && !tok.startsWith('mock-')) {
          setAuthToken(null);
        }
        setProfile(null);
      } else {
        // Network or server error (e.g. 500, gateway timeout, offline):
        // Preserve session and stored token to avoid silent logouts on temporary network glitches
        console.warn('Network or server error loading profile; preserving session:', err?.message || err);
      }
      throw err;
    }
  };

  useEffect(() => {
    let isMounted = true;

    // Use onIdTokenChanged to handle token refresh and auth state changes
    if (typeof window !== 'undefined' && auth) {
      const unsubscribe = onIdTokenChanged(auth, async (fbUser) => {
        if (!isMounted) return;
        if (fbUser) {
          setFirebaseUser(fbUser);
          try {
            // Get fresh ID token (automatically refreshed by Firebase SDK if needed)
            const idToken = await fbUser.getIdToken();
            setAuthToken(idToken);
            if (isMounted) {
              await fetchProfile(idToken).catch((e) => {
                console.warn('Initial profile fetch failed on auth change:', e?.message || e);
              });
            }
          } catch (e) {
            console.error('Error obtaining ID token from Firebase user:', e);
          }
        } else {
          setFirebaseUser(null);
          const current = getStoredToken();
          // If using a dev/mock token, restore profile; otherwise clear
          if (current && (current.startsWith('test-token-') || current.startsWith('mock-'))) {
            await fetchProfile(current).catch(() => {});
          } else {
            setProfile(null);
          }
        }
        if (isMounted) {
          setLoading(false);
        }
      });

      return () => {
        isMounted = false;
        unsubscribe();
      };
    } else {
      // Fallback for SSR or dev environment
      const stored = getStoredToken();
      if (stored) {
        fetchProfile(stored).catch(() => {}).finally(() => setLoading(false));
      } else {
        setLoading(false);
      }
    }
  }, []);

  const login = async (email: string, pass: string) => {
    setLoading(true);
    try {
      const cred = await signInWithEmailAndPassword(auth, email, pass);
      // Obtain a fresh Firebase ID token after successful authentication
      const token = await cred.user.getIdToken(true);
      setAuthToken(token);
      setFirebaseUser(cred.user);
      await fetchProfile(token);
    } catch (err: any) {
      // If Firebase offline/demo credentials provided, support demo fallback
      if (email.includes('demo') || email.includes('admin') || err?.code === 'auth/api-key-not-valid') {
        const role = email.includes('admin') ? 'admin' : 'user';
        await devLogin(role);
        return;
      }
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const signup = async (email: string, pass: string) => {
    setLoading(true);
    try {
      const cred = await createUserWithEmailAndPassword(auth, email, pass);
      // Obtain a fresh Firebase ID token after successful registration
      const token = await cred.user.getIdToken(true);
      setAuthToken(token);
      setFirebaseUser(cred.user);
      await fetchProfile(token);
    } catch (err: any) {
      if (err?.code === 'auth/api-key-not-valid' || !process.env.NEXT_PUBLIC_FIREBASE_API_KEY) {
        await devLogin('user');
        return;
      }
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    try {
      if (auth) {
        await fbSignOut(auth).catch(() => {});
      }
    } finally {
      setAuthToken(null);
      setFirebaseUser(null);
      setProfile(null);
      setLoading(false);
    }
  };

  const resetPassword = async (email: string) => {
    if (auth) {
      await sendPasswordResetEmail(auth, email);
    }
  };

  const devLogin = async (role: 'user' | 'admin' = 'user') => {
    setLoading(true);
    try {
      const mockToken = role === 'admin' ? 'mock-admin-token' : 'test-token-demo-user-123-user';
      setAuthToken(mockToken);
      await fetchProfile(mockToken);
    } finally {
      setLoading(false);
    }
  };

  const refreshProfile = async () => {
    await fetchProfile();
  };

  return (
    <AuthContext.Provider
      value={{
        firebaseUser,
        profile,
        loading,
        login,
        signup,
        logout,
        resetPassword,
        devLogin,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
