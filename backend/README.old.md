# Central 3x-ui Manager MVP v0.3

MVP центральной панели-агрегатора подписок поверх нескольких 3x-ui серверов.

## Что добавлено в v0.3

- Реальный адаптер `py3xui` для:
  - логина в 3x-ui;
  - получения inbound/client конфигов;
  - установки общего `subId` выбранным клиентам.
- Кэш конфигов серверов в БД: `remote_configs`.
- Кэш ответов штатной 3x-ui подписки в БД: `subscription_source_caches`.
- Endpoint для выбора конфига из кэша и добавления его в центральную подписку.
- `/sub/{token}` теперь опрашивает каждый выбранный 3x-ui сервер один раз и при ошибке может вернуть последний успешный кэш.

> Если переходишь с v0.2 и SQLite, проще удалить старый `app.db`: схемы изменились, Alembic пока не подключён.

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Docs: http://127.0.0.1:8000/docs

## Базовый flow

### 1. Добавить сервер

```bash
curl -X POST http://localhost:8000/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "server-1",
    "panel_url": "https://xui.example.com:2053/custom-path",
    "panel_username": "admin",
    "panel_password": "password",
    "subscription_base_url": "https://xui.example.com:2053/sub"
  }'
```

Если в 3x-ui включён custom URI path, добавь его в `panel_url`, как требует `py3xui`.

### 2. Получить и закэшировать конфиги с 3x-ui

```bash
curl -X POST http://localhost:8000/servers/SERVER_ID/configs/refresh
```

### 3. Посмотреть кэш конфигов

```bash
curl http://localhost:8000/servers/SERVER_ID/configs
```

Можно искать:

```bash
curl 'http://localhost:8000/servers/SERVER_ID/configs?q=alex'
```

### 4. Создать центральную подписку

```bash
curl -X POST http://localhost:8000/subscriptions \
  -H "Content-Type: application/json" \
  -d '{"title":"Alex"}'
```

Ответ содержит:

- `token` — ссылка для клиента: `/sub/{token}`
- `shared_sub_id` — общий subId, который будет проставлен в 3x-ui

### 5. Добавить выбранный config в подписку

```bash
curl -X POST http://localhost:8000/subscriptions/SUBSCRIPTION_ID/items/from-config \
  -H "Content-Type: application/json" \
  -d '{"remote_config_id":"REMOTE_CONFIG_ID", "sort_order":100}'
```

Можно добавлять несколько конфигов с разных серверов и разных inbound'ов.

### 6. Проставить общий subId на 3x-ui

```bash
curl -X POST http://localhost:8000/subscriptions/SUBSCRIPTION_ID/apply
```

Этот вызов через `py3xui` обновит выбранные clients и задаст им `subscription.shared_sub_id`.

### 7. Клиентская подписка

```bash
curl http://localhost:8000/sub/TOKEN
```

Внутри backend:

1. проверяет статус и срок центральной подписки;
2. берёт серверы, где есть synced items;
3. вызывает штатный 3x-ui subscription endpoint `/sub/{shared_sub_id}`;
4. нормализует plain/base64;
5. обновляет кэш `subscription_source_caches`;
6. возвращает склеенный ответ.

Если один 3x-ui недоступен, используется последний успешный кэш, если `use_cache_on_error=true`.

## Основные endpoints

- `POST /servers`
- `GET /servers`
- `POST /servers/{server_id}/configs/refresh`
- `GET /servers/{server_id}/configs`
- `POST /subscriptions`
- `GET /subscriptions/{id}`
- `PUT/PATCH /subscriptions/{id}`
- `POST /subscriptions/{id}/items`
- `POST /subscriptions/{id}/items/from-config`
- `PUT/PATCH /subscriptions/{id}/items/{item_id}`
- `DELETE /subscriptions/{id}/items/{item_id}`
- `POST /subscriptions/{id}/apply`
- `GET /sub/{token}`

## Важные ограничения

- Пока нет Alembic migrations.
- Credentials 3x-ui хранятся открытым текстом в БД — для production нужно шифровать.
- 2FA для 3x-ui не реализован в UI/API этого MVP.
- Поведение `subId` зависит от версии 3x-ui; если client update сработал, но UI странно отображает состояние, проверь версию 3x-ui.
