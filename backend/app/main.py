from fastapi import Depends, FastAPI

from app.auth import require_admin
from app.errors import install_error_handlers
from app.routers import audit, auth, public_sub, servers, subscriptions, tools, users


app = FastAPI(title="Central 3x-ui Manager", version="0.5.0")
install_error_handlers(app)

app.include_router(auth.router)
app.include_router(users.router, dependencies=[Depends(require_admin)])
app.include_router(servers.router, dependencies=[Depends(require_admin)])
app.include_router(subscriptions.router, dependencies=[Depends(require_admin)])
app.include_router(audit.router, dependencies=[Depends(require_admin)])
app.include_router(tools.router)
app.include_router(public_sub.router)


@app.get("/health")
def health():
    return {"status": "ok"}
