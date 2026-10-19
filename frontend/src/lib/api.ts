/**
 * Typed REST & Streaming API client communicating with FastAPI backend.
 */
import { auth } from './firebase';

export class ApiError extends Error {
  status: number;
  statusText: string;
  data: any;

  constructor(status: number, statusText: string, message: string, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.data = data;
  }
}

export interface UserRecord {
  uid: string;
  email?: string;
  display_name?: string;
  role: 'user' | 'admin';
  status: 'active' | 'disabled';
  created_at: string;
  last_active_at: string;
  metadata?: Record<string, any>;
}

export interface Conversation {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  is_pinned: boolean;
  model: string;
  message_count: number;
  metadata?: Record<string, any>;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  user_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  token_count: number;
  retrieved_memory_ids: string[];
  metadata?: Record<string, any>;
}

export interface Memory {
  id: string;
  user_id: string;
  content: string;
  created_at: string;
  last_accessed_at: string;
  access_count: number;
  importance: number;
  category: string;
  memory_type: string;
  retention_status: 'active' | 'summarized' | 'archived' | 'forgotten' | 'permanent';
  is_pinned: boolean;
  is_critical: boolean;
  tags: string[];
  retention_score?: number;
  score_breakdown?: {
    importance: number;
    recency: number;
    frequency: number;
    relevance: number;
    redundancy: number;
    composite: number;
  };
  summary_of?: string[];
}

export interface ForgettingEvaluationResult {
  evaluation_id?: string;
  dry_run: boolean;
  evaluated_at: string;
  total_active_before: number;
  total_active_after: number;
  actions_proposed: Array<{
    memory_id: string;
    action: 'retain' | 'summarize' | 'archive' | 'forget' | 'keep' | 'compress' | 'prune' | string;
    score: number;
    reason: string;
    target_summary_content?: string;
  }>;
  retained_count: number;
  summarized_count: number;
  archived_count: number;
  forgotten_count: number;
  keep_count?: number;
  compress_count?: number;
  prune_count?: number;
  protected_count: number;
  estimated_token_savings: number;
}

export interface AdminOverview {
  status: string;
  timestamp: string;
  users: { total: number; active: number; disabled: number };
  memories: {
    total: number;
    active: number;
    summarized: number;
    archived: number;
    forgotten: number;
    permanent: number;
    estimated_active_tokens: number;
    storage_size_bytes: number;
  };
  services: {
    gemini_live: boolean;
    model_configured: string;
    qdrant_healthy: boolean;
    qdrant_collection: string;
    embedding_model: string;
    rl_mode: string;
  };
}

export interface RLExperiment {
  id: string;
  policy_version: string;
  timestamp: string;
  iterations: number;
  mean_reward: number;
  critical_retention_rate: number;
  retrieval_success_rate: number;
  storage_reduction_rate: number;
  safety_violations: number;
  parameters: Record<string, any>;
}

export interface AuditLogItem {
  id: number;
  timestamp: string;
  actor_uid: string;
  action: string;
  target_type: string;
  target_id?: string;
  details: Record<string, any>;
}

export interface LifecycleActivityItem {
  id: number;
  timestamp: string;
  memory_id: string;
  user_id: string;
  operation: 'KEEP' | 'COMPRESS' | 'ARCHIVE' | 'PRUNE' | 'RESTORE' | string;
  previous_status: string;
  new_status: string;
  result: string;
  token_savings: number;
  source_memory_ids?: string[] | null;
  consolidated_memory_id?: string | null;
  reason?: string | null;
}

export interface UserMemoryStats {
  total_memories: number;
  active_count: number;
  summarized_count: number;
  archived_count: number;
  forgotten_count: number;
  permanent_count: number;
  pinned_count: number;
  critical_count: number;
  short_term_count: number;
  long_term_count: number;
  average_importance: number;
  average_retention_score: number;
  estimated_active_tokens: number;
  storage_size_bytes: number;
}

export const getApiBaseUrl = (): string => {
  if (typeof process !== 'undefined') {
    let url = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL;
    if (url) {
      url = url.trim().replace(/\/$/, '');
      const bare = url.replace(/^https?:\/\//, '').replace(/\/.*$/, '');
      // Handle Render private service names (e.g. "intelligent-forgetting-backend" without TLD)
      if (bare === 'intelligent-forgetting-backend' || bare.endsWith('.internal')) {
        url = 'https://intelligent-forgetting-backend.onrender.com';
      } else if (!bare.includes('.') && bare !== 'localhost' && bare !== '127.0.0.1') {
        url = `https://${bare}.onrender.com`;
      } else if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = `https://${url}`;
      }
      // If configured with trailing /api/v1 or /api, strip it so baseUrl is the pure host origin
      url = url.replace(/\/api\/v1\/?$/, '').replace(/\/api\/?$/, '');
      return url;
    }
  }
  // Client-side fallback if env vars missing in browser runtime
  if (typeof window !== 'undefined' && window.location) {
    if (window.location.hostname.endsWith('.onrender.com')) {
      return 'https://intelligent-forgetting-backend.onrender.com';
    }
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      return 'http://127.0.0.1:8000';
    }
  }
  return 'http://127.0.0.1:8000';
};

// Token storage helper
let currentToken: string | null = null;

export const setAuthToken = (token: string | null) => {
  currentToken = token;
  if (typeof window !== 'undefined') {
    if (token) {
      localStorage.setItem('if_token', token);
    } else {
      localStorage.removeItem('if_token');
    }
  }
};

export const getStoredToken = (): string | null => {
  if (!currentToken && typeof window !== 'undefined') {
    currentToken = localStorage.getItem('if_token');
  }
  return currentToken;
};

/**
 * Ensures a valid, current token is acquired before protected requests.
 * Uses Firebase authenticated user's getIdToken() if available to avoid expired or stale tokens.
 */
export async function getValidToken(forceRefresh: boolean = false): Promise<string | null> {
  if (typeof window !== 'undefined' && auth) {
    if (typeof auth.authStateReady === 'function') {
      try {
        await auth.authStateReady();
      } catch {
        // Continue with available state
      }
    }
    if (auth.currentUser) {
      try {
        const freshToken = await auth.currentUser.getIdToken(forceRefresh);
        if (freshToken) {
          setAuthToken(freshToken);
          return freshToken;
        }
      } catch (err) {
        console.warn('Failed to obtain ID token from auth.currentUser:', err);
      }
    }
  }
  return getStoredToken();
}

async function apiRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (!headers.has('Cache-Control')) {
    headers.set('Cache-Control', 'no-cache');
  }
  if (!headers.has('Pragma')) {
    headers.set('Pragma', 'no-cache');
  }
  if (!headers.has('Authorization')) {
    const token = await getValidToken();
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }

  const baseUrl = getApiBaseUrl();
  let path = endpoint;
  if (!path.startsWith('http')) {
    if (!path.startsWith('/')) {
      path = `/${path}`;
    }
    // Prevent accidental duplication: e.g. /api/v1/api/v1/me -> /api/v1/me
    path = path.replace(/^\/api\/v1\/api\/v1\//, '/api/v1/');
  }

  const url = path.startsWith('http') ? path : `${baseUrl}${path}`;

  const response = await fetch(url, { cache: 'no-store', ...options, headers });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(
      response.status,
      response.statusText,
      errorData.detail || `Request failed with status ${response.status}`,
      errorData
    );
  }
  return response.json();
}

export const api = {
  // System
  getHealth: () => apiRequest<{ status: string; services: any }>('/api/v1/health'),
  getReadiness: () => apiRequest<{ status: string; ready: boolean }>('/api/v1/health/ready'),

  // Profile & Self
  getProfile: (explicitToken?: string) =>
    apiRequest<UserRecord>(
      '/api/v1/me',
      explicitToken ? { headers: { Authorization: `Bearer ${explicitToken}` } } : {}
    ),
  updateProfile: (data: { display_name?: string; metadata?: Record<string, any> }) =>
    apiRequest<UserRecord>('/api/v1/me/profile', { method: 'PATCH', body: JSON.stringify(data) }),
  deleteAccount: () => apiRequest<{ status: string; message: string; purged_records: any }>('/api/v1/me', { method: 'DELETE' }),

  // Conversations
  listConversations: () => apiRequest<Conversation[]>('/api/v1/conversations'),
  createConversation: (title?: string) =>
    apiRequest<Conversation>('/api/v1/conversations', { method: 'POST', body: JSON.stringify({ title: title || 'New Conversation' }) }),
  getConversation: (id: string) => apiRequest<Conversation>(`/api/v1/conversations/${id}`),
  updateConversation: (id: string, data: { title?: string; is_pinned?: boolean }) =>
    apiRequest<Conversation>(`/api/v1/conversations/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteConversation: (id: string) =>
    apiRequest<{ status: string }>(`/api/v1/conversations/${id}`, { method: 'DELETE' }),

  // Messages
  getMessages: (conversationId: string) =>
    apiRequest<ChatMessage[]>(`/api/v1/conversations/${conversationId}/messages`),
  sendMessage: (conversationId: string, content: string) =>
    apiRequest<ChatMessage>(`/api/v1/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),

  // Streaming Message via SSE
  streamMessage: async (
    conversationId: string,
    content: string,
    onChunk: (delta: string) => void,
    onDone: (messageId: string) => void,
    onError: (err: Error) => void
  ) => {
    const token = getStoredToken();
    const baseUrl = getApiBaseUrl();
    const url = `${baseUrl}/api/v1/conversations/${conversationId}/messages/stream`;

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ content }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Streaming failed with status ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();
            if (!dataStr) continue;
            try {
              const data = JSON.parse(dataStr);
              if (data.type === 'chunk' && data.delta) {
                onChunk(data.delta);
              } else if (data.type === 'done') {
                onDone(data.message_id || '');
              } else if (data.type === 'error') {
                onError(new Error(data.detail || 'Streaming encountered an error'));
              }
            } catch {
              // Ignore partial JSON
            }
          }
        }
      }
    } catch (err: any) {
      onError(err instanceof Error ? err : new Error(String(err)));
    }
  },

  // Memories
  listMemories: (status?: string, category?: string, limit: number = 200, offset: number = 0) => {
    let url = `/api/v1/memories?limit=${limit}&offset=${offset}`;
    if (status && status !== 'ALL') url += `&status=${status}`;
    if (category && category !== 'ALL') url += `&category=${category}`;
    return apiRequest<Memory[]>(url);
  },
  createMemory: (data: {
    content: string;
    importance?: number;
    category?: string;
    memory_type?: string;
    is_pinned?: boolean;
    is_critical?: boolean;
    tags?: string[];
  }) => apiRequest<Memory>('/api/v1/memories', { method: 'POST', body: JSON.stringify(data) }),
  getMemory: (id: string) => apiRequest<Memory>(`/api/v1/memories/${id}`),
  updateMemory: (id: string, data: Partial<Memory>) =>
    apiRequest<Memory>(`/api/v1/memories/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  updateImportance: (id: string, importance: number) =>
    apiRequest<Memory>(`/api/v1/memories/${id}/importance`, { method: 'PATCH', body: JSON.stringify({ importance }) }),
  pinMemory: (id: string) => apiRequest<Memory>(`/api/v1/memories/${id}/pin`, { method: 'POST' }),
  unpinMemory: (id: string) => apiRequest<Memory>(`/api/v1/memories/${id}/unpin`, { method: 'POST' }),
  markCritical: (id: string, critical: boolean = true) =>
    apiRequest<Memory>(`/api/v1/memories/${id}/critical?critical=${critical}`, { method: 'POST' }),
  archiveMemory: (id: string, reason?: string) =>
    apiRequest<Memory>(`/api/v1/memories/${id}/archive?reason=${encodeURIComponent(reason || 'User requested archival')}`, { method: 'POST' }),
  restoreMemory: (id: string) => apiRequest<Memory>(`/api/v1/memories/${id}/restore`, { method: 'POST' }),
  deleteMemory: (id: string, permanent: boolean = false) =>
    apiRequest<{ status: string; memory_id: string }>(`/api/v1/memories/${id}?permanent=${permanent}`, { method: 'DELETE' }),
  searchMemories: (query: string, topK: number = 10, useVector: boolean = true) =>
    apiRequest<Memory[]>('/api/v1/memories/search', {
      method: 'POST',
      body: JSON.stringify({ query, top_k: topK, use_vector: useVector }),
    }),
  getMemoryStats: () => apiRequest<UserMemoryStats>('/api/v1/memories/stats'),
  getLifecycleStats: () =>
    apiRequest<{
      total_operations: number;
      measured_token_savings: number;
      estimated_token_savings: number;
      unique_memories_affected: number;
      kept_count: number;
      archived_count: number;
      compressed_count: number;
      pruned_count: number;
      calculation_method: string;
    }>('/api/v1/memories/lifecycle-stats'),
  getActivityLog: (limit: number = 50, offset: number = 0) =>
    apiRequest<LifecycleActivityItem[]>(`/api/v1/memories/activity-log?limit=${limit}&offset=${offset}`),

  // Forgetting Engine
  evaluateForgetting: (dryRun: boolean = true, taskContext?: string) =>
    apiRequest<ForgettingEvaluationResult>('/api/v1/forgetting/evaluate', {
      method: 'POST',
      body: JSON.stringify({ dry_run: dryRun, task_context: taskContext }),
    }),
  applyForgetting: (actionItems?: any[], taskContext?: string, evaluationId?: string) =>
    apiRequest<{ retained: number; summarized: number; archived: number; forgotten: number; details: any[] }>(
      '/api/v1/forgetting/apply',
      { method: 'POST', body: JSON.stringify({ action_items: actionItems, task_context: taskContext, evaluation_id: evaluationId }) }
    ),

  // Admin Dashboard
  getAdminOverview: () => apiRequest<AdminOverview>('/api/v1/admin/overview'),
  listAdminUsers: (search?: string, limit: number = 100, offset: number = 0) => {
    let url = `/api/v1/admin/users?limit=${limit}&offset=${offset}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    return apiRequest<UserRecord[]>(url);
  },
  updateUserStatus: (uid: string, status: 'active' | 'disabled') =>
    apiRequest<UserRecord>(`/api/v1/admin/users/${uid}/status?status_val=${status}`, { method: 'PATCH' }),
  updateUserRole: (uid: string, role: 'user' | 'admin') =>
    apiRequest<UserRecord>(`/api/v1/admin/users/${uid}/role?role_val=${role}`, { method: 'PATCH' }),
  getAuditLogs: (limit: number = 100, offset: number = 0) =>
    apiRequest<AuditLogItem[]>(`/api/v1/admin/audit-logs?limit=${limit}&offset=${offset}`),
  listRLExperiments: () => apiRequest<RLExperiment[]>('/api/v1/admin/rl/experiments'),
  triggerRLExperiment: (iterations: number = 50) =>
    apiRequest<RLExperiment>(`/api/v1/admin/rl/experiments?iterations=${iterations}`, { method: 'POST' }),

  // Qdrant Cloud Diagnostics & SQLite Reconciliation
  getQdrantDiagnostics: () => apiRequest<any>('/api/v1/qdrant/diagnostics'),
  reconcileQdrant: (fix: boolean = false) =>
    apiRequest<any>(`/api/v1/qdrant/reconcile?fix=${fix}`, { method: 'POST' }),
};

