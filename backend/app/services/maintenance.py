from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import (
    AuditEventType,
    MaintenanceRun,
    RemoteConfig,
    RemoteConfigStatus,
    Server,
    ServerStatus,
    now_utc,
)
from app.routers.servers import refresh_configs
from app.services.audit import audit
from app.services.traffic_stats import create_daily_traffic_snapshots
from app.services.xui_adapter import XuiAdapter, XuiServerConfig
from app.settings import settings


@dataclass(slots=True)
class DailyMaintenanceResult:
    run_date: str
    refreshed_before: int = 0
    refresh_before_failed: int = 0
    snapshot_created: int = 0
    snapshot_updated: int = 0
    snapshot_total: int = 0
    reset_ok: int = 0
    reset_failed: int = 0
    refreshed_after: int = 0
    refresh_after_failed: int = 0
    missing_snapshot_created: int = 0
    missing_snapshot_updated: int = 0
    missing_deleted: int = 0
    errors: list[str] | None = None

    def add_error(self, message: str) -> None:
        if self.errors is None:
            self.errors = []
        self.errors.append(message)


def make_adapter(server: Server) -> XuiAdapter:
    return XuiAdapter(
        XuiServerConfig(
            panel_url=server.panel_url,
            panel_username=server.panel_username,
            panel_password=server.panel_password,
            subscription_base_url=server.subscription_base_url,
        )
    )


def _active_servers(db: Session) -> list[Server]:
    return db.query(Server).filter(Server.status != ServerStatus.disabled).order_by(Server.created_at.asc()).all()


def _refresh_all_servers(db: Session, result: DailyMaintenanceResult, *, phase: str) -> None:
    for server in _active_servers(db):
        try:
            refresh_configs(server.id, db)
            if phase == "before":
                result.refreshed_before += 1
            else:
                result.refreshed_after += 1
        except Exception as exc:  # noqa: BLE001
            if phase == "before":
                result.refresh_before_failed += 1
            else:
                result.refresh_after_failed += 1
            result.add_error(f"refresh {phase} failed for {server.name}: {exc}")
            db.rollback()


def _reset_all_server_traffic(db: Session, result: DailyMaintenanceResult) -> None:
    if not settings.maintenance_reset_traffic_enabled:
        return

    for server in _active_servers(db):
        try:
            adapter = make_adapter(server)
            mode = settings.maintenance_reset_traffic_mode.lower().strip()
            if mode == "all":
                adapter.reset_all_panel_traffics()
            elif mode == "clients":
                adapter.reset_all_client_traffics()
            else:
                raise ValueError("MAINTENANCE_RESET_TRAFFIC_MODE must be 'clients' or 'all'")
            result.reset_ok += 1
            audit(
                db,
                AuditEventType.traffic_reset,
                f"Traffic reset on server {server.name}",
                entity_type="server",
                entity_id=server.id,
                payload={"mode": mode},
            )
            db.commit()
        except Exception as exc:  # noqa: BLE001
            result.reset_failed += 1
            result.add_error(f"traffic reset failed for {server.name}: {exc}")
            db.rollback()


def _cleanup_missing_remote_configs(db: Session, result: DailyMaintenanceResult, *, run_date: date) -> None:
    if not settings.maintenance_cleanup_missing_enabled:
        return

    grace_hours = max(0, settings.maintenance_missing_remote_config_grace_hours)
    cutoff = now_utc() - timedelta(hours=grace_hours)

    missing_query = db.query(RemoteConfig).filter(
        RemoteConfig.status == RemoteConfigStatus.missing,
        RemoteConfig.updated_at <= cutoff,
    )

    missing_count = missing_query.count()
    if missing_count:
        missing_snapshot = create_daily_traffic_snapshots(
            db,
            snapshot_date=run_date,
            snapshot_type="missing_cleanup",
            include_missing=True,
            only_enabled_synced_items=False,
        )
        result.missing_snapshot_created = missing_snapshot.created
        result.missing_snapshot_updated = missing_snapshot.updated
        db.flush()

    result.missing_deleted = missing_query.delete(synchronize_session=False)
    db.commit()


def _get_or_create_run(db: Session, *, run_date: date) -> MaintenanceRun:
    run = (
        db.query(MaintenanceRun)
        .filter(MaintenanceRun.run_type == "daily", MaintenanceRun.run_date == run_date)
        .first()
    )
    if run:
        return run

    run = MaintenanceRun(run_type="daily", run_date=run_date, status="started", started_at=now_utc())
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def run_daily_maintenance(db: Session, *, run_date: date | None = None, force: bool = False) -> DailyMaintenanceResult:
    run_date = run_date or now_utc().date()
    run = _get_or_create_run(db, run_date=run_date)
    if run.status == "finished" and not force:
        payload = json.loads(run.payload_json or "{}")
        return DailyMaintenanceResult(**payload) if payload else DailyMaintenanceResult(run_date=run_date.isoformat())

    result = DailyMaintenanceResult(run_date=run_date.isoformat())
    run.status = "started"
    run.error = None
    run.started_at = run.started_at or now_utc()
    audit(db, AuditEventType.maintenance_started, "Daily maintenance started", entity_type="maintenance", entity_id=run.id)
    db.commit()

    try:
        reset_already_happened = run.last_step in {"reset_traffic_done", "refresh_after_done", "cleanup_done"}

        if not reset_already_happened:
            _refresh_all_servers(db, result, phase="before")
            run.last_step = "refresh_before_done"
            db.commit()

            if settings.maintenance_daily_snapshot_enabled:
                snapshot = create_daily_traffic_snapshots(
                    db,
                    snapshot_date=run_date,
                    snapshot_type="daily_reset",
                    include_missing=False,
                    only_enabled_synced_items=True,
                )
                result.snapshot_created = snapshot.created
                result.snapshot_updated = snapshot.updated
                result.snapshot_total = snapshot.total
                audit(
                    db,
                    AuditEventType.daily_traffic_snapshot_created,
                    "Daily traffic snapshot created before reset",
                    entity_type="maintenance",
                    entity_id=run.id,
                    payload=asdict(snapshot),
                )
                run.last_step = "snapshot_done"
                db.commit()

            _reset_all_server_traffic(db, result)
            run.last_step = "reset_traffic_done"
            db.commit()
        else:
            result.add_error("Skipped snapshot/reset because this maintenance run had already reached reset_traffic_done")

        _refresh_all_servers(db, result, phase="after")
        run.last_step = "refresh_after_done"
        db.commit()

        _cleanup_missing_remote_configs(db, result, run_date=run_date)
        run.last_step = "cleanup_done"

        run.status = "finished"
        run.finished_at = now_utc()
        run.payload_json = json.dumps(asdict(result), ensure_ascii=False, default=str)
        audit(
            db,
            AuditEventType.maintenance_finished,
            "Daily maintenance finished",
            entity_type="maintenance",
            entity_id=run.id,
            payload=asdict(result),
        )
        db.commit()
        return result
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(MaintenanceRun, run.id)
        if run:
            run.status = "failed"
            run.finished_at = now_utc()
            run.error = str(exc)
            run.payload_json = json.dumps(asdict(result), ensure_ascii=False, default=str)
            db.commit()
        raise
