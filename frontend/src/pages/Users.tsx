import React from 'react';
import { api } from '../lib/api';
import { fmtDate, shortId } from '../lib/format';
import type { User } from '../lib/types';
import { Badge, Button, Card, Empty, ErrorBox, Input, Select } from '../components/ui';
import { CreateUserForm } from '../components/forms';

export function UsersPage({ users, onChanged }: { users: User[]; onChanged: () => Promise<void> }) {
  const [q, setQ] = React.useState('');
  const [filtered, setFiltered] = React.useState<User[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);

  async function reload() {
    await onChanged();
    if (filtered !== null) setFiltered(await api.listUsers(q));
  }

  async function search() {
    setError(null);
    try { setFiltered(await api.listUsers(q)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  async function removeUser(user: User) {
    const label = user.name || user.email || user.telegram_id || shortId(user.id);
    if (!window.confirm(`Удалить пользователя "${label}"?`)) return;
    setBusy(`delete-${user.id}`);
    setError(null);
    try {
      await api.deleteUser(user.id, false);
      await reload();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (window.confirm(`Не удалось удалить без force:\n${message}\n\nУдалить принудительно вместе с локальными зависимостями?`)) {
        try { await api.deleteUser(user.id, true); await reload(); }
        catch (forceErr) { setError(forceErr instanceof Error ? forceErr.message : String(forceErr)); }
      } else {
        setError(message);
      }
    } finally {
      setBusy(null);
    }
  }

  const list = filtered ?? users;
  return <div className="page-grid">
    <CreateUserForm onCreate={async payload => { await api.createUser(payload); await onChanged(); setFiltered(null); }} />
    <Card title="Users" action={<div className="inline-tools"><Input placeholder="Search users" value={q} onChange={e => setQ(e.target.value)} /><Button variant="secondary" onClick={search}>Search</Button></div>}>
      <ErrorBox error={error} />
      {list.length === 0 ? <Empty>No users yet.</Empty> : <div className="table-wrap"><table><thead><tr><th>User</th><th>Email</th><th>Telegram</th><th>Status</th><th>Created</th><th /></tr></thead><tbody>{list.map(user => <tr key={user.id}>
        <td><b>{user.name || 'Unnamed'}</b><small>{user.external_id || shortId(user.id)}</small></td><td>{user.email || '—'}</td><td>{user.telegram_id || '—'}</td><td><Badge value={user.status} /></td><td>{fmtDate(user.created_at)}</td>
        <td className="row-actions"><Select value={user.status} onChange={async e => { await api.patchUser(user.id, { status: e.target.value as User['status'] }); await reload(); }}><option value="active">active</option><option value="disabled">disabled</option></Select><Button variant="danger" busy={busy === `delete-${user.id}`} onClick={() => removeUser(user)}>Delete</Button></td>
      </tr>)}</tbody></table></div>}
    </Card>
  </div>;
}
