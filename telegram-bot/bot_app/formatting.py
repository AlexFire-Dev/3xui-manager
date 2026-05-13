from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from bot_app.models import Subscription, Traffic, User


STATUS_LABELS = {
    "active": "активна",
    "disabled": "отключена",
    "expired": "истекла",
}


def fmt_bytes(value: int | None) -> str:
    value = int(value or 0)
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ", "ПБ"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "Б":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}".replace(".00", "")
        size /= 1024
    return f"{value} Б"


def fmt_percent(used: int, limit: int | None) -> str:
    if not limit:
        return "без лимита"
    return f"{used / limit * 100:.1f}%"


def fmt_date(value: str | None) -> str:
    if not value:
        return "не задано"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%d.%m.%Y %H:%M")


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def format_subscription_line(subscription: Subscription, traffic: Traffic | None) -> str:
    used = traffic.total if traffic else 0
    limit = traffic.limit if traffic else subscription.traffic_limit
    return (
        f"<b>{escape(subscription.title)}</b>\n"
        f"Статус: {escape(status_label(subscription.status))}\n"
        f"Трафик: {fmt_bytes(used)} / {fmt_bytes(limit) if limit else 'без лимита'} ({fmt_percent(used, limit)})\n"
        f"Истекает: {escape(fmt_date(subscription.expires_at))}"
    )


def format_user_stats(user: User, subscriptions: list[Subscription], traffic_by_id: dict[str, Traffic]) -> str:
    title_name = user.name or user.telegram_id or "пользователь"
    total_used = sum((traffic_by_id.get(sub.id).total if traffic_by_id.get(sub.id) else 0) for sub in subscriptions)
    total_limit_values = [sub.traffic_limit for sub in subscriptions if sub.traffic_limit]
    total_limit = sum(total_limit_values) if total_limit_values else None

    lines = [
        f"👤 <b>{escape(title_name)}</b>",
        f"Telegram: <code>{escape(user.telegram_id or 'не задан')}</code>",
        f"Подписок: <b>{len(subscriptions)}</b>",
        f"Всего использовано: <b>{fmt_bytes(total_used)}</b>"
        + (f" / {fmt_bytes(total_limit)} ({fmt_percent(total_used, total_limit)})" if total_limit else ""),
    ]

    if subscriptions:
        lines.append("")
        lines.append("<b>Подписки:</b>")
        for index, subscription in enumerate(subscriptions, start=1):
            traffic = traffic_by_id.get(subscription.id)
            lines.append(f"\n{index}. " + format_subscription_line(subscription, traffic))

    return "\n".join(lines)


def format_single_subscription(subscription: Subscription, traffic: Traffic) -> str:
    lines = [format_subscription_line(subscription, traffic)]
    if traffic.breakdown:
        lines.append("")
        lines.append("<b>По серверам:</b>")
        for item in traffic.breakdown:
            lines.append(
                f"• {escape(item.server_name)}: {fmt_bytes(item.total)} "
                f"↓ {fmt_bytes(item.down)} / ↑ {fmt_bytes(item.up)}"
                f" · клиентов: {item.items}"
            )
    return "\n".join(lines)
