import React from 'react';
import { api } from '../lib/api';
import { fmtDate, shortId } from '../lib/format';
import type { RemoteConfig, Server } from '../lib/types';
import { Badge, Button, Card, Empty, ErrorBox, Input } from '../components/ui';
import { CreateServerForm } from '../components/forms';

export function ServersPage({ servers, onChanged }: { servers: Server[]; onChanged: () => Promise<void> }) {
  const [selected, setSelected] = React.useState<Server | null>(null);
  const [configs, setConfigs] = React.useState<RemoteConfig[]>([]);
  const [q, setQ] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [editing, setEditing] = React.useState<Server | null>(null);

  async function loadConfigs(server: Server, query = q) {
    setSelected(server); setBusy('configs'); setError(null);
    try { setConfigs(await api.listConfigs(server.id, query)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(null); }
  }
  async function health(server: Server) { setBusy(server.id); setError(null); try { await api.serverHealth(server.id); await onChanged(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(null); } }
  async function refresh(server: Server) { setBusy(server.id); setError(null); try { const res = await api.refreshConfigs(server.id); setSelected(server); setConfigs(res.configs); await onChanged(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(null); } }

  async function removeServer(server: Server) {
    if (!window.confirm(`Удалить сервер "${server.name}" из локальной БД менеджера?`)) return;
    setBusy(`delete-${server.id}`);
    setError(null);
    try {
      await api.deleteServer(server.id, false);
      if (selected?.id === server.id) { setSelected(null); setConfigs([]); }
      await onChanged();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (window.confirm(`Не удалось удалить без force:\n${message}\n\nУдалить принудительно вместе с локальными конфигами/items/cache?`)) {
        try { await api.deleteServer(server.id, true); if (selected?.id === server.id) { setSelected(null); setConfigs([]); } await onChanged(); }
        catch (forceErr) { setError(forceErr instanceof Error ? forceErr.message : String(forceErr)); }
      } else {
        setError(message);
      }
    } finally { setBusy(null); }
  }

  return <div className="page-grid two-col">
    <div>
      <CreateServerForm onCreate={async payload => { await api.createServer(payload); await onChanged(); }} />
      {editing && (
        <CreateServerForm
          initial={editing}
          title={`Edit server: ${editing.name}`}
          submitLabel="Save"
          onCancel={() => setEditing(null)}
          onCreate={async payload => {
            const cleanPayload = {
              ...payload,
              panel_password: payload.panel_password || undefined,
            };
            await api.patchServer(editing.id, cleanPayload);
            setEditing(null);
            await onChanged();
          }}
        />
      )}
      <Card title="Servers"><ErrorBox error={error} />{servers.length === 0 ? <Empty>Add your first 3x-ui server.</Empty> : <div className="table-wrap"><table><thead><tr><th>Name</th><th>Status</th><th>Panel</th><th>Last refresh</th><th /></tr></thead><tbody>{servers.map(server => <tr key={server.id} className={selected?.id === server.id ? 'selected-row' : ''}>
        <td><b>{server.name}</b><small>{shortId(server.id)}</small></td><td><Badge value={server.status} /></td><td>{server.panel_url}</td><td>{fmtDate(server.last_config_refresh_at)}</td>
        <td className="row-actions"><Button variant="secondary" busy={busy === server.id} onClick={() => health(server)}>Health</Button><Button variant="secondary" busy={busy === server.id} onClick={() => refresh(server)}>Refresh configs</Button><Button variant="ghost" onClick={() => loadConfigs(server)}>Open</Button><Button variant="secondary" onClick={() => setEditing(server)}>Edit</Button><Button variant="danger" busy={busy === `delete-${server.id}`} onClick={() => removeServer(server)}>Delete</Button></td>
      </tr>)}</tbody></table></div>}</Card>
    </div>
    <Card title={selected ? `Configs: ${selected.name}` : 'Configs'} action={selected && <div className="inline-tools"><Input placeholder="Search" value={q} onChange={e => setQ(e.target.value)} /><Button variant="secondary" onClick={() => selected && loadConfigs(selected, q)}>Search</Button></div>}>
      {!selected ? <Empty>Select a server to inspect cached configs.</Empty> : busy === 'configs' ? <Empty>Loading...</Empty> : configs.length === 0 ? <Empty>No configs cached. Click Refresh configs.</Empty> : <div className="config-list">{configs.map(cfg => <div className="config-card" key={cfg.id}>
        <div><b>{cfg.client_email || 'No email'}</b><span>{cfg.inbound_remark || `Inbound ${cfg.inbound_id}`}</span></div>
        <div><Badge value={cfg.status} /></div>
        <code>{cfg.client_uuid}</code>
        <small>subId: {cfg.client_sub_id || '—'} · port: {cfg.inbound_port || '—'} · {cfg.inbound_protocol || '—'}</small>
      </div>)}</div>}
    </Card>
  </div>;
}
