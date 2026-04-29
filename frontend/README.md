# Central 3x-ui Manager Frontend

React/Vite frontend for `central-3xui-manager` backend v0.6.

## Run locally

Backend:

```bash
cd central-3xui-manager-v0.6
docker compose up --build
```

Frontend:

```bash
cd central-3xui-manager-frontend-v0.5
npm install
npm run dev
```

Open http://localhost:5173.

Default API base is `/api`; Vite proxies it to `http://localhost:8000`.
For production, set:

```bash
VITE_API_BASE_URL=https://your-manager.example.com
```

## What is implemented

- Login via `/auth/login`
- Dashboard counters
- Servers: create, list, health, refresh configs, delete
- Users: create, list, edit status/basic fields, delete/force delete
- Subscriptions: create, list, inspect, update status/expiry/limit, delete
- Config picker: select cached remote configs and bulk attach to subscription
- Apply/reconcile actions
- Preview and public subscription URL copy
- Traffic, cache and audit log views


## Backend connection

By default the production nginx image proxies `/api/*` to `http://host.docker.internal:8000/`.
This is the easiest mode when the backend is running on your machine via `docker compose up` or uvicorn.

If frontend and backend are in the same Docker Compose project and the backend service is named `backend`, change `nginx.conf`:

```nginx
proxy_pass http://backend:8000/;
```

Then rebuild the frontend image.
