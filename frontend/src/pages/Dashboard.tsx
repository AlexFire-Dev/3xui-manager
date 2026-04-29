import { Card } from '../components/ui';
import type { Server, Subscription, User } from '../lib/types';

export function Dashboard({ users, servers, subscriptions }: { users: User[]; servers: Server[]; subscriptions: Subscription[] }) {
  const activeServers = servers.filter(s => s.status === 'active').length;
  const activeSubs = subscriptions.filter(s => s.status === 'active').length;
  return <div className="page-grid">
    <Card title="Overview"><div className="metrics">
      <div className="metric"><strong>{users.length}</strong><span>Users</span></div>
      <div className="metric"><strong>{servers.length}</strong><span>Servers</span></div>
      <div className="metric"><strong>{activeServers}</strong><span>Active servers</span></div>
      <div className="metric"><strong>{activeSubs}</strong><span>Active subscriptions</span></div>
    </div></Card>
    <Card title="Flow"><div className="flow">
      <div>1. Add 3x-ui servers</div><div>2. Refresh cached configs</div><div>3. Create user + central subscription</div><div>4. Pick configs and Apply</div><div>5. Give client one public `/sub/token` URL</div>
    </div></Card>
  </div>;
}
