import React from 'react';
import { api, publicSubUrl } from '../lib/api';
import { fmtBytes, fmtDate, fromLocalInputValue, shortId, toLocalInputValue } from '../lib/format';
import type { ApplyResult, PreviewResult, RemoteConfig, Server, SourceCache, Subscription, SubscriptionDetail, TrafficResult, User } from '../lib/types';
import { Badge, Button, Card, CopyButton, Empty, ErrorBox, Field, Input, Select, Textarea } from '../components/ui';
import { CreateSubscriptionForm } from '../components/forms';

export function SubscriptionsPage({ users, servers, subscriptions, onChanged }: { users: User[]; servers: Server[]; subscriptions: Subscription[]; onChanged: () => Promise<void> }) {
  const [selectedId, setSelectedId] = React.useState<string | null>(subscriptions[0]?.id ?? null);
  const [detail, setDetail] = React.useState<SubscriptionDetail | null>(null);
  const [preview, setPreview] = React.useState<PreviewResult | null>(null);
  const [applyResult, setApplyResult] = React.useState<ApplyResult | null>(null);
  const [traffic, setTraffic] = React.useState<TrafficResult | null>(null);
  const [cache, setCache] = React.useState<SourceCache[]>([]);
  const [serverId, setServerId] = React.useState('');
  const [configs, setConfigs] = React.useState<RemoteConfig[]>([]);
  const [selectedConfigs, setSelectedConfigs] = React.useState<Set<string>>(new Set());
  const [configQ, setConfigQ] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);

  React.useEffect(() => { if (selectedId) loadDetail(selectedId); }, [selectedId]);

  async function wrap<T>(name: string, fn: () => Promise<T>) { setBusy(name); setError(null); try { return await fn(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(null); } }
  async function loadDetail(id = selectedId!) { await wrap('detail', async () => { const d = await api.readSubscription(id); setDetail(d); setPreview(null); setApplyResult(null); return d; }); }
  async function loadConfigs() { if (!serverId) return; await wrap('configs', async () => { setConfigs(await api.listConfigs(serverId, configQ)); setSelectedConfigs(new Set()); }); }
  async function addSelected(replace_existing = false) { if (!detail || selectedConfigs.size === 0) return; await wrap('bulk', async () => { await api.bulkItems(detail.id, [...selectedConfigs], replace_existing); await loadDetail(detail.id); }); }
  async function runApply() { if (!detail) return; await wrap('apply', async () => { const res = await api.apply(detail.id); setApplyResult(res); await loadDetail(detail.id); await onChanged(); }); }
  async function runPreview() { if (!detail) return; await wrap('preview', async () => setPreview(await api.preview(detail.id))); }
  async function loadTraffic() { if (!detail) return; await wrap('traffic', async () => setTraffic(await api.traffic(detail.id, true))); }
  async function loadCache() { if (!detail) return; await wrap('cache', async () => setCache(await api.cache(detail.id))); }
  async function refreshCache() { if (!detail) return; await wrap('cache-refresh', async () => setPreview(await api.refreshCache(detail.id))); }
  async function removeSubscription() {
    if (!detail) return;
    if (!window.confirm(`Удалить подписку \"${detail.title}\" из локальной БД менеджера?`)) return;
    await wrap('delete-subscription', async () => {
      await api.deleteSubscription(detail.id);
      setDetail(null);
      setPreview(null);
      setApplyResult(null);
      setTraffic(null);
      setCache([]);
      const next = subscriptions.find(s => s.id !== detail.id);
      setSelectedId(next?.id ?? null);
      await onChanged();
    });
  }

  return <div className="page-grid two-col wide-left">
    <div>
      <CreateSubscriptionForm users={users} onCreate={async payload => { const sub = await api.createSubscription(payload); await onChanged(); setSelectedId(sub.id); }} />
      <Card title="Subscriptions">
        {subscriptions.length === 0 ? <Empty>Create a subscription.</Empty> : <div className="subscription-list">{subscriptions.map(sub => <button key={sub.id} className={`subscription-row ${sub.id === selectedId ? 'active' : ''}`} onClick={() => setSelectedId(sub.id)}>
          <div><b>{sub.title}</b><small>{shortId(sub.id)} · {sub.user_id ? `user ${shortId(sub.user_id)}` : 'no user'}</small></div><Badge value={sub.status} />
        </button>)}</div>}
      </Card>
    </div>
    <div className="stack">
      <ErrorBox error={error} />
      {!detail ? <Card><Empty>Select subscription.</Empty></Card> : <>
        <Card title={detail.title} action={<div className="inline-tools"><Button variant="secondary" busy={busy === 'preview'} onClick={runPreview}>Preview</Button><Button busy={busy === 'apply'} onClick={runApply}>Apply</Button><Button variant="danger" busy={busy === 'delete-subscription'} onClick={removeSubscription}>Delete</Button></div>}>
          <div className="details-grid">
            <div><span>Status</span><Badge value={detail.status} /></div><div><span>Items</span><b>{detail.items.length}</b></div><div><span>Expires</span><b>{fmtDate(detail.expires_at)}</b></div><div><span>Limit</span><b>{detail.traffic_limit ? fmtBytes(detail.traffic_limit) : '—'}</b></div>
            <div className="wide"><span>Public URL</span><div className="copy-line"><code>{publicSubUrl(detail.token)}</code><CopyButton value={publicSubUrl(detail.token)} /></div></div>
            <div><span>shared_sub_id</span><code>{detail.shared_sub_id}</code></div><div><span>token</span><code>{detail.token}</code></div>
          </div>
          <EditSubscription detail={detail} users={users} onSaved={async () => { await loadDetail(detail.id); await onChanged(); }} />
        </Card>

        <Card title="Items / selected configs"><div className="table-wrap"><table><thead><tr><th>Server</th><th>Inbound</th><th>Client</th><th>Status</th><th>Enabled</th><th /></tr></thead><tbody>{detail.items.map(item => <tr key={item.id}>
          <td>{servers.find(s => s.id === item.server_id)?.name || shortId(item.server_id)}</td><td>{item.inbound_id}</td><td><b>{item.client_email || '—'}</b><small>{shortId(item.client_uuid)}</small></td><td><Badge value={item.status} />{item.last_error && <small className="danger-text">{item.last_error}</small>}</td><td>{item.enabled ? 'yes' : 'no'}</td>
          <td className="row-actions"><Button variant="secondary" onClick={async () => { await api.patchItem(detail.id, item.id, { enabled: !item.enabled }); await loadDetail(detail.id); }}>{item.enabled ? 'Disable' : 'Enable'}</Button><Button variant="danger" onClick={async () => { await api.deleteItem(detail.id, item.id); await loadDetail(detail.id); }}>Remove</Button></td>
        </tr>)}</tbody></table></div>{detail.items.length === 0 && <Empty>No configs attached yet.</Empty>}</Card>

        <Card title="Add configs from server" action={<div className="inline-tools"><Select value={serverId} onChange={e => setServerId(e.target.value)}><option value="">Select server</option>{servers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</Select><Input placeholder="Search config" value={configQ} onChange={e => setConfigQ(e.target.value)} /><Button variant="secondary" busy={busy === 'configs'} onClick={loadConfigs}>Load</Button></div>}>
          {configs.length === 0 ? <Empty>Load cached server configs first. Refresh them on Servers page if needed.</Empty> : <><div className="config-list compact">{configs.map(cfg => <label className="config-card selectable" key={cfg.id}>
            <input type="checkbox" checked={selectedConfigs.has(cfg.id)} onChange={e => setSelectedConfigs(prev => { const next = new Set(prev); e.target.checked ? next.add(cfg.id) : next.delete(cfg.id); return next; })} />
            <div><b>{cfg.client_email || 'No email'}</b><span>{cfg.inbound_remark || `Inbound ${cfg.inbound_id}`}</span><small>{shortId(cfg.client_uuid)} · subId {cfg.client_sub_id || '—'}</small></div><Badge value={cfg.status} />
          </label>)}</div><div className="form-actions"><Button variant="secondary" busy={busy === 'bulk'} disabled={selectedConfigs.size === 0} onClick={() => addSelected(false)}>Add selected</Button><Button variant="danger" busy={busy === 'bulk'} disabled={selectedConfigs.size === 0} onClick={() => addSelected(true)}>Replace with selected</Button></div></>}
        </Card>

        <Card title="Preview / cache / traffic" action={<div className="inline-tools"><Button variant="secondary" busy={busy === 'traffic'} onClick={loadTraffic}>Traffic</Button><Button variant="secondary" busy={busy === 'cache'} onClick={loadCache}>Cache</Button><Button variant="secondary" busy={busy === 'cache-refresh'} onClick={refreshCache}>Refresh cache</Button></div>}>
          {applyResult && <ResultBlock title="Apply result" value={JSON.stringify(applyResult, null, 2)} />}
          {preview && <ResultBlock title={`Preview: ${preview.link_count} links${preview.used_cache ? ' (cache used)' : ''}`} value={preview.links.join('\n') || preview.errors.join('\n')} />}
          {traffic && <ResultBlock title={`Traffic: ${fmtBytes(traffic.total)} / ${traffic.limit ? fmtBytes(traffic.limit) : '∞'}`} value={traffic.breakdown.map(b => `${b.server_name}: ${fmtBytes(b.total)} (${b.items} items)`).join('\n')} />}
          {cache.length > 0 && <ResultBlock title="Cache" value={cache.map(c => `${servers.find(s => s.id === c.server_id)?.name || c.server_id}: success=${fmtDate(c.last_success_at)} error=${c.last_error || '—'}`).join('\n')} />}
        </Card>
      </>}
    </div>
  </div>;
}

function EditSubscription({ detail, users, onSaved }: { detail: SubscriptionDetail; users: User[]; onSaved: () => Promise<void> }) {
  const [form, setForm] = React.useState({ title: detail.title, status: detail.status, user_id: detail.user_id || '', expires_at: toLocalInputValue(detail.expires_at), traffic_limit_gb: detail.traffic_limit ? String(Math.round(detail.traffic_limit / 1024 ** 3)) : '' });
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => setForm({ title: detail.title, status: detail.status, user_id: detail.user_id || '', expires_at: toLocalInputValue(detail.expires_at), traffic_limit_gb: detail.traffic_limit ? String(Math.round(detail.traffic_limit / 1024 ** 3)) : '' }), [detail.id]);
  return <form className="grid-form subtle-form" onSubmit={async e => { e.preventDefault(); setBusy(true); try { await api.patchSubscription(detail.id, { title: form.title, status: form.status, user_id: form.user_id || null, expires_at: fromLocalInputValue(form.expires_at), traffic_limit: form.traffic_limit_gb ? Math.round(Number(form.traffic_limit_gb) * 1024 ** 3) : null }); await onSaved(); } finally { setBusy(false); } }}>
    <Field label="Title"><Input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} /></Field><Field label="Status"><Select value={form.status} onChange={e => setForm({ ...form, status: e.target.value as Subscription['status'] })}><option value="active">active</option><option value="disabled">disabled</option><option value="expired">expired</option></Select></Field>
    <Field label="User"><Select value={form.user_id} onChange={e => setForm({ ...form, user_id: e.target.value })}><option value="">No user</option>{users.map(u => <option key={u.id} value={u.id}>{u.name || u.email || u.telegram_id || u.id}</option>)}</Select></Field><Field label="Expires"><Input type="datetime-local" value={form.expires_at} onChange={e => setForm({ ...form, expires_at: e.target.value })} /></Field><Field label="Limit, GB"><Input type="number" value={form.traffic_limit_gb} onChange={e => setForm({ ...form, traffic_limit_gb: e.target.value })} /></Field>
    <div className="form-actions"><Button variant="secondary" busy={busy}>Save</Button></div>
  </form>;
}

function ResultBlock({ title, value }: { title: string; value: string }) { return <div className="result-block"><div><b>{title}</b><CopyButton value={value} /></div><Textarea readOnly value={value} rows={8} /></div>; }
