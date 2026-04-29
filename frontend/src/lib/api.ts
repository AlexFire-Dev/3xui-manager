import type {
  ApplyResult,
  AuditLog,
  PreviewResult,
  RemoteConfig,
  Server,
  SourceCache,
  Subscription,
  SubscriptionDetail,
  SubscriptionItem,
  TrafficResult,
  User,
} from './types';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
const TOKEN_KEY = 'central3xui_token';

type ApiOptions = RequestInit & { auth?: boolean };

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function publicSubUrl(token: string) {
  const base = API_BASE === '/api' ? window.location.origin + '/api' : API_BASE;
  return `${base}/sub/${token}`;
}

async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has('Content-Type') && options.body) headers.set('Content-Type', 'application/json');
  const token = getToken();
  if (options.auth !== false && token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      message = data.message || data.detail || data.error || message;
    } catch {
      try { message = await response.text(); } catch { /* noop */ }
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return response.json() as Promise<T>;
  return response.text() as Promise<T>;
}

export const api = {
  login: async (username: string, password: string) => {
    const result = await request<{ access_token: string; token_type: string; expires_in: number }>('/auth/login', {
      method: 'POST',
      auth: false,
      body: JSON.stringify({ username, password }),
    });
    setToken(result.access_token);
    return result;
  },
  me: () => request<{ username: string; scope: string }>('/auth/me'),

  listUsers: (q = '') => request<User[]>(`/users${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  createUser: (payload: Partial<User>) => request<User>('/users', { method: 'POST', body: JSON.stringify(payload) }),
  patchUser: (id: string, payload: Partial<User>) => request<User>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteUser: (id: string, force = false) => request<void>(`/users/${id}${force ? '?force=true' : ''}`, { method: 'DELETE' }),
  userSubscriptions: (id: string) => request<Subscription[]>(`/users/${id}/subscriptions`),

  listServers: () => request<Server[]>('/servers'),
  deleteServer: (id: string, force = false) => request<void>(`/servers/${id}${force ? '?force=true' : ''}`, { method: 'DELETE' }),
  createServer: (payload: { name: string; panel_url: string; panel_username: string; panel_password: string; subscription_base_url: string }) =>
    request<Server>('/servers', { method: 'POST', body: JSON.stringify(payload) }),
  serverHealth: (id: string) => request<{ server_id: string; status: string; ok: boolean; checked_at: string; error?: string }>(`/servers/${id}/health`),
  refreshConfigs: (id: string) => request<{ server_id: string; discovered: number; upserted: number; marked_missing: number; configs: RemoteConfig[] }>(`/servers/${id}/configs/refresh`, { method: 'POST' }),
  listConfigs: (serverId: string, q = '') => request<RemoteConfig[]>(`/servers/${serverId}/configs${q ? `?q=${encodeURIComponent(q)}` : ''}`),

  listSubscriptions: (userId?: string) => request<Subscription[]>(`/subscriptions${userId ? `?user_id=${encodeURIComponent(userId)}` : ''}`),
  createSubscription: (payload: { title: string; user_id?: string | null; expires_at?: string | null; traffic_limit?: number | null }) =>
    request<Subscription>('/subscriptions', { method: 'POST', body: JSON.stringify(payload) }),
  readSubscription: (id: string) => request<SubscriptionDetail>(`/subscriptions/${id}`),
  patchSubscription: (id: string, payload: Partial<Subscription>) => request<Subscription>(`/subscriptions/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteSubscription: (id: string) => request<void>(`/subscriptions/${id}`, { method: 'DELETE' }),
  addItemFromConfig: (id: string, remote_config_id: string) => request<SubscriptionItem>(`/subscriptions/${id}/items/from-config`, { method: 'POST', body: JSON.stringify({ remote_config_id }) }),
  bulkItems: (id: string, remote_config_ids: string[], replace_existing = false) =>
    request<SubscriptionItem[]>(`/subscriptions/${id}/items/bulk`, { method: 'PUT', body: JSON.stringify({ remote_config_ids, replace_existing }) }),
  patchItem: (subscriptionId: string, itemId: string, payload: Partial<SubscriptionItem>) =>
    request<SubscriptionItem>(`/subscriptions/${subscriptionId}/items/${itemId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteItem: (subscriptionId: string, itemId: string) => request<void>(`/subscriptions/${subscriptionId}/items/${itemId}`, { method: 'DELETE' }),
  apply: (id: string) => request<ApplyResult>(`/subscriptions/${id}/apply`, { method: 'POST' }),
  reconcile: (id: string) => request<ApplyResult>(`/subscriptions/${id}/reconcile`, { method: 'POST' }),
  preview: (id: string) => request<PreviewResult>(`/subscriptions/${id}/preview`),
  previewText: (id: string, format: 'plain' | 'base64' = 'plain') => request<string>(`/subscriptions/${id}/preview.txt?format=${format}`),
  traffic: (id: string, refresh = true) => request<TrafficResult>(`/subscriptions/${id}/traffic?refresh=${refresh}`),
  cache: (id: string) => request<SourceCache[]>(`/subscriptions/${id}/cache`),
  refreshCache: (id: string) => request<PreviewResult>(`/subscriptions/${id}/cache/refresh`, { method: 'POST' }),

  audit: (limit = 100, entityType?: string, entityId?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (entityType) params.set('entity_type', entityType);
    if (entityId) params.set('entity_id', entityId);
    return request<AuditLog[]>(`/audit-log?${params.toString()}`);
  },
};
