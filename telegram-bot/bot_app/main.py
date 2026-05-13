from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot_app.api import BackendApiClient, BackendApiError
from bot_app.config import settings
from bot_app.formatting import format_single_subscription, format_user_stats
from bot_app.keyboards import single_subscription_keyboard, subscriptions_keyboard
from bot_app.models import Subscription, Traffic, User
from bot_app.qr import make_qr_png

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

router = Router()
api = BackendApiClient()


@dataclass(frozen=True)
class UserContext:
    user: User
    subscriptions: list[Subscription]


def _telegram_username(message_or_callback: Message | CallbackQuery) -> str | None:
    tg_user = message_or_callback.from_user
    if not tg_user or not tg_user.username:
        return None
    return tg_user.username


async def _resolve_user_context(message_or_callback: Message | CallbackQuery) -> UserContext | str:
    username = _telegram_username(message_or_callback)
    if not username:
        return (
            "Я привязываю доступ по Telegram username. "
            "У тебя в Telegram не задан username, поэтому я не могу найти тебя в панели."
        )

    user = await api.find_user_by_telegram_username(username)
    normalized_username = api.normalize_telegram_username(username)
    if not user:
        return (
            f"Не нашёл пользователя с telegram_id <code>{normalized_username}</code>.\n\n"
            "Проверь, что в карточке пользователя в центральной панели telegram_id заполнен именно в таком формате."
        )

    if user.status != "active":
        return "Твой пользователь в панели сейчас отключён."

    subscriptions = await api.get_user_subscriptions(user.id)
    return UserContext(user=user, subscriptions=subscriptions)


async def _traffic_for_subscriptions(subscriptions: list[Subscription]) -> dict[str, Traffic]:
    async def fetch(subscription: Subscription) -> tuple[str, Traffic | None]:
        try:
            return subscription.id, await api.get_subscription_traffic(subscription.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read traffic for subscription %s: %s", subscription.id, exc)
            return subscription.id, None

    pairs = await asyncio.gather(*(fetch(subscription) for subscription in subscriptions))
    return {subscription_id: traffic for subscription_id, traffic in pairs if traffic is not None}


def _find_subscription(subscriptions: list[Subscription], subscription_id: str) -> Subscription | None:
    return next((item for item in subscriptions if item.id == subscription_id), None)


async def _send_stats(message: Message, *, edit: bool = False) -> None:
    context = await _resolve_user_context(message)
    if isinstance(context, str):
        if edit:
            await message.edit_text(context)
        else:
            await message.answer(context)
        return

    if not context.subscriptions:
        text = (
            f"👤 <b>{context.user.name or context.user.telegram_id or 'Пользователь'}</b>\n"
            "У тебя пока нет подписок."
        )
        if edit:
            await message.edit_text(text, reply_markup=subscriptions_keyboard([]))
        else:
            await message.answer(text, reply_markup=subscriptions_keyboard([]))
        return

    traffic_by_id = await _traffic_for_subscriptions(context.subscriptions)
    text = format_user_stats(context.user, context.subscriptions, traffic_by_id)
    keyboard = subscriptions_keyboard(context.subscriptions)

    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.message(Command("start", "stats"))
async def command_stats(message: Message) -> None:
    try:
        await _send_stats(message)
    except BackendApiError as exc:
        await message.answer(f"Backend API недоступен или вернул ошибку:\n<code>{str(exc)}</code>")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in stats command")
        await message.answer(f"Неожиданная ошибка:\n<code>{str(exc)}</code>")


@router.callback_query(F.data == "r")
async def callback_refresh(callback: CallbackQuery) -> None:
    await callback.answer("Обновляю…")
    if not isinstance(callback.message, Message):
        return
    try:
        await _send_stats(callback.message, edit=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to refresh stats")
        await callback.message.answer(f"Не удалось обновить статистику:\n<code>{str(exc)}</code>")


@router.callback_query(F.data.startswith("s:"))
async def callback_single_stats(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    subscription_id = (callback.data or "").split(":", 1)[1]
    try:
        context = await _resolve_user_context(callback)
        if isinstance(context, str):
            await callback.answer("Нет доступа", show_alert=True)
            await callback.message.answer(context)
            return

        subscription = _find_subscription(context.subscriptions, subscription_id)
        if not subscription:
            await callback.answer("Подписка не найдена", show_alert=True)
            return

        traffic = await api.get_subscription_traffic(subscription.id)
        await callback.message.edit_text(
            format_single_subscription(subscription, traffic),
            reply_markup=single_subscription_keyboard(subscription.id),
        )
        await callback.answer()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to show subscription stats")
        await callback.answer("Ошибка", show_alert=True)
        await callback.message.answer(f"Не удалось получить статистику подписки:\n<code>{str(exc)}</code>")


@router.callback_query(F.data.startswith("q:"))
async def callback_qr(callback: CallbackQuery, bot: Bot) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    subscription_id = (callback.data or "").split(":", 1)[1]
    try:
        context = await _resolve_user_context(callback)
        if isinstance(context, str):
            await callback.answer("Нет доступа", show_alert=True)
            await callback.message.answer(context)
            return

        subscription = _find_subscription(context.subscriptions, subscription_id)
        if not subscription:
            await callback.answer("Подписка не найдена", show_alert=True)
            return

        url = api.subscription_public_url(subscription)
        png = make_qr_png(url)
        file = BufferedInputFile(png, filename=f"subscription-{subscription.id}.png")
        await bot.send_photo(
            chat_id=callback.message.chat.id,
            photo=file,
            caption=f"📲 QR для <b>{subscription.title}</b>\n<code>{url}</code>",
        )
        await callback.answer("QR отправлен")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send QR")
        await callback.answer("Ошибка", show_alert=True)
        await callback.message.answer(f"Не удалось отправить QR:\n<code>{str(exc)}</code>")


@router.callback_query(F.data.startswith("l:"))
async def callback_link(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    subscription_id = (callback.data or "").split(":", 1)[1]
    try:
        context = await _resolve_user_context(callback)
        if isinstance(context, str):
            await callback.answer("Нет доступа", show_alert=True)
            await callback.message.answer(context)
            return

        subscription = _find_subscription(context.subscriptions, subscription_id)
        if not subscription:
            await callback.answer("Подписка не найдена", show_alert=True)
            return

        url = api.subscription_public_url(subscription)
        await callback.message.answer(f"🔗 <b>{subscription.title}</b>\n<code>{url}</code>")
        await callback.answer("Ссылка отправлена")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send link")
        await callback.answer("Ошибка", show_alert=True)
        await callback.message.answer(f"Не удалось отправить ссылку:\n<code>{str(exc)}</code>")


@router.callback_query(F.data == "la")
async def callback_all_links(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    try:
        context = await _resolve_user_context(callback)
        if isinstance(context, str):
            await callback.answer("Нет доступа", show_alert=True)
            await callback.message.answer(context)
            return

        if not context.subscriptions:
            await callback.answer("Подписок нет", show_alert=True)
            return

        lines = ["🔗 <b>Твои ссылки подписок:</b>"]
        for index, subscription in enumerate(context.subscriptions, start=1):
            lines.append(f"\n{index}. <b>{subscription.title}</b>\n<code>{api.subscription_public_url(subscription)}</code>")
        await callback.message.answer("\n".join(lines))
        await callback.answer("Ссылки отправлены")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send all links")
        await callback.answer("Ошибка", show_alert=True)
        await callback.message.answer(f"Не удалось отправить ссылки:\n<code>{str(exc)}</code>")


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Напиши /start или /stats, чтобы получить статистику и QR подписок.")


async def main() -> None:
    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    try:
        logger.info("Starting Telegram bot")
        await dp.start_polling(bot)
    finally:
        await api.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
