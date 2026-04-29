import React from 'react';
import { api } from '../lib/api';
import { fmtDate, shortId } from '../lib/format';
import type { AuditLog } from '../lib/types';
import { Button, Card, Empty, ErrorBox, Input } from '../components/ui';

export function AuditPage() {
  const [logs, setLogs] = React.useState<AuditLog[]>([]);
  const [entityType, setEntityType] = React.useState('');
  const [entityId, setEntityId] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  async function load() { setBusy(true); setError(null); try { setLogs(await api.audit(200, entityType || undefined, entityId || undefined)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } }
  React.useEffect(() => { load(); }, []);
  return <Card title="Audit log" action={<div className="inline-tools"><Input placeholder="entity_type" value={entityType} onChange={e => setEntityType(e.target.value)} /><Input placeholder="entity_id" value={entityId} onChange={e => setEntityId(e.target.value)} /><Button variant="secondary" busy={busy} onClick={load}>Load</Button></div>}>
    <ErrorBox error={error} />{logs.length === 0 ? <Empty>No events.</Empty> : <div className="table-wrap"><table><thead><tr><th>When</th><th>Event</th><th>Entity</th><th>Message</th></tr></thead><tbody>{logs.map(log => <tr key={log.id}>
      <td>{fmtDate(log.created_at)}</td><td><b>{log.event_type}</b></td><td>{log.entity_type || '—'} {log.entity_id ? shortId(log.entity_id) : ''}</td><td>{log.message}{log.payload_json && <details><summary>payload</summary><pre>{log.payload_json}</pre></details>}</td>
    </tr>)}</tbody></table></div>}
  </Card>;
}
