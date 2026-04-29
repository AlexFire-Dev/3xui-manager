import React from 'react';
import { Button, Card, Field, Input, Select } from './ui';
import { fromLocalInputValue } from '../lib/format';
import type { User } from '../lib/types';

export function CreateServerForm({ onCreate }: { onCreate: (payload: { name: string; panel_url: string; panel_username: string; panel_password: string; subscription_base_url: string }) => Promise<void> }) {
  const [form, setForm] = React.useState({ name: '', panel_url: '', panel_username: '', panel_password: '', subscription_base_url: '' });
  const [busy, setBusy] = React.useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    try { await onCreate(form); setForm({ name: '', panel_url: '', panel_username: '', panel_password: '', subscription_base_url: '' }); } finally { setBusy(false); }
  }
  return <Card title="Add server"><form className="grid-form" onSubmit={submit}>
    <Field label="Name"><Input required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Germany #1" /></Field>
    <Field label="Panel URL"><Input required value={form.panel_url} onChange={e => setForm({ ...form, panel_url: e.target.value })} placeholder="https://xui.example.com:2053" /></Field>
    <Field label="Username"><Input required value={form.panel_username} onChange={e => setForm({ ...form, panel_username: e.target.value })} /></Field>
    <Field label="Password"><Input required type="password" value={form.panel_password} onChange={e => setForm({ ...form, panel_password: e.target.value })} /></Field>
    <Field label="Subscription base URL"><Input required value={form.subscription_base_url} onChange={e => setForm({ ...form, subscription_base_url: e.target.value })} placeholder="https://xui.example.com/sub" /></Field>
    <div className="form-actions"><Button busy={busy}>Create server</Button></div>
  </form></Card>;
}

export function CreateUserForm({ onCreate }: { onCreate: (payload: Partial<User>) => Promise<void> }) {
  const [form, setForm] = React.useState({ name: '', email: '', telegram_id: '', external_id: '' });
  const [busy, setBusy] = React.useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    try { await onCreate(form); setForm({ name: '', email: '', telegram_id: '', external_id: '' }); } finally { setBusy(false); }
  }
  return <Card title="Add user"><form className="grid-form" onSubmit={submit}>
    <Field label="Name"><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></Field>
    <Field label="Email"><Input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /></Field>
    <Field label="Telegram ID"><Input value={form.telegram_id} onChange={e => setForm({ ...form, telegram_id: e.target.value })} /></Field>
    <Field label="External ID"><Input value={form.external_id} onChange={e => setForm({ ...form, external_id: e.target.value })} /></Field>
    <div className="form-actions"><Button busy={busy}>Create user</Button></div>
  </form></Card>;
}

export function CreateSubscriptionForm({ users, onCreate }: { users: User[]; onCreate: (payload: { title: string; user_id?: string | null; expires_at?: string | null; traffic_limit?: number | null }) => Promise<void> }) {
  const [form, setForm] = React.useState({ title: '', user_id: '', expires_at: '', traffic_limit_gb: '' });
  const [busy, setBusy] = React.useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    try {
      await onCreate({
        title: form.title,
        user_id: form.user_id || null,
        expires_at: fromLocalInputValue(form.expires_at),
        traffic_limit: form.traffic_limit_gb ? Math.round(Number(form.traffic_limit_gb) * 1024 ** 3) : null,
      });
      setForm({ title: '', user_id: '', expires_at: '', traffic_limit_gb: '' });
    } finally { setBusy(false); }
  }
  return <Card title="Create subscription"><form className="grid-form" onSubmit={submit}>
    <Field label="Title"><Input required value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Alex / Mobile" /></Field>
    <Field label="User"><Select value={form.user_id} onChange={e => setForm({ ...form, user_id: e.target.value })}><option value="">No user</option>{users.map(u => <option key={u.id} value={u.id}>{u.name || u.email || u.telegram_id || u.id}</option>)}</Select></Field>
    <Field label="Expires at"><Input type="datetime-local" value={form.expires_at} onChange={e => setForm({ ...form, expires_at: e.target.value })} /></Field>
    <Field label="Traffic limit, GB"><Input type="number" min="0" step="1" value={form.traffic_limit_gb} onChange={e => setForm({ ...form, traffic_limit_gb: e.target.value })} /></Field>
    <div className="form-actions"><Button busy={busy}>Create subscription</Button></div>
  </form></Card>;
}
