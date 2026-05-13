from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot_app.models import Subscription


def _short_title(title: str, limit: int = 24) -> str:
    title = " ".join((title or "Подписка").split())
    if len(title) <= limit:
        return title
    return title[: limit - 1].rstrip() + "…"


def subscriptions_keyboard(subscriptions: list[Subscription]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for subscription in subscriptions:
        sid = subscription.id
        title = _short_title(subscription.title)
        builder.button(text=f"📊 {title}", callback_data=f"s:{sid}")
        builder.button(text="📲 QR", callback_data=f"q:{sid}")
        builder.button(text="🔗", callback_data=f"l:{sid}")

    builder.button(text="🔄 Обновить", callback_data="r")
    if subscriptions:
        builder.button(text="🔗 Все ссылки", callback_data="la")
    builder.adjust(*([3] * len(subscriptions)), 1, 1)
    return builder.as_markup()


def single_subscription_keyboard(subscription_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📲 QR", callback_data=f"q:{subscription_id}")
    builder.button(text="🔗 Ссылка", callback_data=f"l:{subscription_id}")
    builder.button(text="⬅️ Все подписки", callback_data="r")
    builder.adjust(2, 1)
    return builder.as_markup()
