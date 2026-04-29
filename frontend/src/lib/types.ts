export type Status = 'active' | 'disabled' | 'down' | 'expired' | 'pending' | 'synced' | 'error' | 'missing';

export type User = {
  id: string;
  external_id: string | null;
  name: string | null;
  email: string | null;
  telegram_id: string | null;
  status: 'active' | 'disabled';
  created_at: string;
};

export type Server = {
  id: string;
  name: string;
  panel_url: string;
  subscription_base_url: string;
  status: 'active' | 'disabled' | 'down';
  created_at: string;
  last_config_refresh_at?: string | null;
  last_config_refresh_error?: string | null;
  last_health_at?: string | null;
  last_health_error?: string | null;
};

export type RemoteConfig = {
  id: string;
  server_id: string;
  inbound_id: number;
  inbound_remark: string | null;
  inbound_protocol: string | null;
  inbound_port: number | null;
  client_uuid: string;
  client_email: string | null;
  client_sub_id: string | null;
  client_enable: boolean | null;
  client_expiry_time: number | null;
  client_total_gb: number | null;
  client_up?: number | null;
  client_down?: number | null;
  status: 'active' | 'disabled' | 'missing';
  discovered_at: string;
  updated_at: string;
};

export type Subscription = {
  id: string;
  user_id: string | null;
  title: string;
  token: string;
  shared_sub_id: string;
  status: 'active' | 'disabled' | 'expired';
  expires_at: string | null;
  traffic_limit: number | null;
  created_at: string;
};

export type SubscriptionItem = {
  id: string;
  subscription_id: string;
  server_id: string;
  inbound_id: number;
  client_email: string | null;
  client_uuid: string | null;
  enabled: boolean;
  status: 'pending' | 'synced' | 'error' | 'disabled';
  last_error: string | null;
  last_sync_at: string | null;
  sort_order: number;
};

export type SubscriptionDetail = Subscription & { items: SubscriptionItem[] };

export type PreviewResult = {
  subscription_id: string;
  token: string;
  link_count: number;
  links: string[];
  errors: string[];
  used_cache: boolean;
};

export type ApplyResult = {
  subscription_id: string;
  shared_sub_id: string;
  synced: number;
  failed: number;
  skipped: number;
  errors: string[];
  results: Array<{
    item_id: string;
    server_id: string;
    inbound_id: number;
    client_email: string | null;
    client_uuid: string | null;
    status: string;
    ok: boolean;
    action: string;
    error?: string | null;
  }>;
};

export type TrafficResult = {
  subscription_id: string;
  up: number;
  down: number;
  total: number;
  limit: number | null;
  breakdown: Array<{ server_id: string; server_name: string; up: number; down: number; total: number; items: number }>;
};

export type SourceCache = {
  id: string;
  subscription_id: string;
  server_id: string;
  normalized_links: string;
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_error: string | null;
};

export type AuditLog = {
  id: string;
  event_type: string;
  entity_type: string | null;
  entity_id: string | null;
  message: string;
  payload_json: string | null;
  created_at: string;
};
