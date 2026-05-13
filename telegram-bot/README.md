# Telegram Bot Service for Central 3x-ui Manager

Отдельный Telegram bot service для проекта Central 3x-ui Manager.

Бот **не импортирует backend-код**, **не подключается к PostgreSQL напрямую** и работает только через существующее HTTP API:

- `POST /auth/login`
- `GET /users?q=@username`
- `GET /users/{id}/subscriptions`
- `GET /subscriptions/{id}/traffic?refresh=true`
- публичная ссылка `/sub/{token}` для QR

## Логика привязки пользователя

В текущей панели поле `users.telegram_id` хранится как Telegram username, например:

```text
@alex_shvarev
```

Telegram API отдаёт username без `@`, например `alex_shvarev`. Бот нормализует его в `@alex_shvarev`, ищет через:

```text
GET /users?q=@alex_shvarev
```

После этого бот делает точное сравнение поля `telegram_id`, чтобы не принять случайное совпадение из поиска.

Если пользователь поменяет username в Telegram, привязку в панели тоже нужно обновить.

## Несколько подписок у одного пользователя

Бот учитывает, что у пользователя может быть несколько подписок:

```text
GET /users/{user_id}/subscriptions
```

В `/start` и `/stats` он показывает сводку по всем подпискам и кнопки для каждой подписки:

- `📊` — подробная статистика конкретной подписки;
- `📲 QR` — QR публичной subscription-ссылки `/sub/{token}`;
- `🔗` — текстовая ссылка подписки;
- `🔗 Все ссылки` — все ссылки пользователя одним сообщением;
- `🔄 Обновить` — перечитать статистику через backend.

## ENV

Создай переменные в корневом `.env` проекта или отдельном env-файле:

```env
TELEGRAM_BOT_TOKEN=123456:telegram-token

# Если запускаешь через docker compose overlay рядом с api:
BOT_API_BASE_URL=http://api:8000

# URL, который пользователь реально должен открыть из Telegram.
# Важно: если backend опубликован с /api prefix, укажи его здесь.
BOT_PUBLIC_SUB_BASE_URL=https://vpn.example.com/api

BOT_ADMIN_USERNAME=admin
BOT_ADMIN_PASSWORD=admin
BOT_REQUEST_TIMEOUT_SECONDS=30
BOT_TRAFFIC_REFRESH=true
```

`BOT_PUBLIC_SUB_BASE_URL` должен указывать туда, где доступен endpoint `/sub/{token}`.

Примеры итоговой ссылки:

```text
https://vpn.example.com/api/sub/abcdef
https://api.example.com/sub/abcdef
```

## Запуск через docker compose overlay

Файл `docker-compose.telegram.yml` лежит в корне проекта и не меняет существующий backend.

```bash
docker compose -f docker-compose.yml -f docker-compose.telegram.yml up -d --build telegram-bot
```

Логи:

```bash
docker compose -f docker-compose.yml -f docker-compose.telegram.yml logs -f telegram-bot
```

## Локальный запуск

```bash
cd telegram-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m bot_app.main
```

При локальном запуске обычно нужно:

```env
BOT_API_BASE_URL=http://localhost:8000
BOT_PUBLIC_SUB_BASE_URL=http://localhost:8000
```

## Важно по безопасности

Бот использует admin API token, потому что в backend пока нет отдельного read-only API token для client-facing сервисов. В идеале позже добавить в backend отдельный service token с правами только на чтение:

- искать пользователя по telegram username;
- читать список его подписок;
- читать traffic;
- получать public subscription URL/token.

Сейчас backend-код не меняется, поэтому бот авторизуется через существующий `/auth/login`.
