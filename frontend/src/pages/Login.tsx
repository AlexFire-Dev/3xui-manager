import React from 'react';
import { api } from '../lib/api';
import { Button, ErrorBox, Field, Input } from '../components/ui';

export function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = React.useState('admin');
  const [password, setPassword] = React.useState('admin');
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(null); setBusy(true);
    try { await api.login(username, password); onLogin(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); }
  }
  return <main className="login-screen"><form className="login-card" onSubmit={submit}>
    <div className="logo-mark">3x</div>
    <h1>Central 3x-ui Manager</h1>
    <p>Admin panel for aggregated multi-server subscriptions.</p>
    <ErrorBox error={error} />
    <Field label="Username"><Input value={username} onChange={e => setUsername(e.target.value)} /></Field>
    <Field label="Password"><Input type="password" value={password} onChange={e => setPassword(e.target.value)} /></Field>
    <Button busy={busy}>Login</Button>
  </form></main>;
}
