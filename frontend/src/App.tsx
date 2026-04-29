import React from 'react';
import { Activity, Database, LogOut, Server as ServerIcon, Users, WalletCards } from 'lucide-react';
import { clearToken, getToken, api } from './lib/api';
import type { Server, Subscription, User } from './lib/types';
import { ErrorBox } from './components/ui';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { ServersPage } from './pages/Servers';
import { UsersPage } from './pages/Users';
import { SubscriptionsPage } from './pages/Subscriptions';
import { AuditPage } from './pages/Audit';

type Tab = 'dashboard' | 'servers' | 'users' | 'subscriptions' | 'audit';

const tabs: Array<{ id: Tab; label: string; icon: React.ReactNode }> = [
  { id: 'dashboard', label: 'Dashboard', icon: <Activity size={18} /> },
  { id: 'servers', label: 'Servers', icon: <ServerIcon size={18} /> },
  { id: 'users', label: 'Users', icon: <Users size={18} /> },
  { id: 'subscriptions', label: 'Subscriptions', icon: <WalletCards size={18} /> },
  { id: 'audit', label: 'Audit', icon: <Database size={18} /> },
];

export default function App() {
  const [authenticated, setAuthenticated] = React.useState(Boolean(getToken()));
  const [tab, setTab] = React.useState<Tab>('dashboard');
  const [users, setUsers] = React.useState<User[]>([]);
  const [servers, setServers] = React.useState<Server[]>([]);
  const [subscriptions, setSubscriptions] = React.useState<Subscription[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  async function loadAll() {
    setLoading(true); setError(null);
    try {
      const [u, s, subs] = await Promise.all([api.listUsers(), api.listServers(), api.listSubscriptions()]);
      setUsers(u); setServers(s); setSubscriptions(subs);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      if (message.toLowerCase().includes('token') || message.includes('401')) { clearToken(); setAuthenticated(false); }
    } finally { setLoading(false); }
  }

  React.useEffect(() => { if (authenticated) loadAll(); }, [authenticated]);

  if (!authenticated) return <Login onLogin={() => setAuthenticated(true)} />;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="logo-mark small">3x</div><div><b>Central Manager</b><span>3x-ui orchestration</span></div></div>
      <nav>{tabs.map(t => <button key={t.id} className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)}>{t.icon}{t.label}</button>)}</nav>
      <button className="logout" onClick={() => { clearToken(); setAuthenticated(false); }}><LogOut size={17} /> Logout</button>
    </aside>
    <main className="content">
      <header className="topbar"><div><h1>{tabs.find(t => t.id === tab)?.label}</h1><p>{loading ? 'Refreshing data…' : 'Ready'}</p></div><button className="btn btn-secondary" onClick={loadAll}>Refresh all</button></header>
      <ErrorBox error={error} />
      {tab === 'dashboard' && <Dashboard users={users} servers={servers} subscriptions={subscriptions} />}
      {tab === 'servers' && <ServersPage servers={servers} onChanged={loadAll} />}
      {tab === 'users' && <UsersPage users={users} onChanged={loadAll} />}
      {tab === 'subscriptions' && <SubscriptionsPage users={users} servers={servers} subscriptions={subscriptions} onChanged={loadAll} />}
      {tab === 'audit' && <AuditPage />}
    </main>
  </div>;
}
