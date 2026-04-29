# Central 3x-ui Manager MVP v0.5

Центральная панель-оркестратор поверх нескольких 3x-ui серверов.

## Что добавлено в v0.5

- Admin auth:
  - `POST /auth/login`
  - `GET /auth/me`
  - все admin endpoints закрыты Bearer token'ом
  - публичными остаются `GET /health` и `GET /sub/{token}`
- Единый формат ошибок:

```json
{
  "error": "not_found",
  "message": "Subscription not found",
  "details": {}
}
```

- Более подробный `apply`:
  - результат по каждому item;
  - `synced / failed / skipped`;
  - в 3x-ui теперь проставляются не только `subId`, но и `expiryTime`, `totalGB`, `enable`.

> Alembic пока не подключён. Для MVP схема создаётся через `Base.metadata.create_all`. При изменении моделей проще пересоздать БД/volume.

## Запуск

```bash
docker compose up --build
```

Swagger UI:

```text
http://localhost:8000/docs
```

## Переменные окружения

```env
DATABASE_URL=postgresql+psycopg://manager:manager@postgres:5432/manager
PUBLIC_BASE_URL=http://localhost:8000
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
JWT_SECRET=change-me-in-production
ADMIN_TOKEN_TTL_SECONDS=43200
```

## Auth flow

### 1. Получить токен

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)
```

### 2. Использовать admin API

```bash
curl http://localhost:8000/users \
  -H "Authorization: Bearer $TOKEN"
```

## Основной flow

### 1. Создать пользователя

```bash
curl -X POST http://localhost:8000/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Alex","telegram_id":"123"}'
```

### 2. Добавить 3x-ui сервер

```bash
curl -X POST http://localhost:8000/servers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "server-1",
    "panel_url": "https://xui.example.com:2053/custom-path",
    "panel_username": "admin",
    "panel_password": "password",
    "subscription_base_url": "https://xui.example.com:2053/sub"
  }'
```

### 3. Закэшировать конфиги с сервера

```bash
curl -X POST http://localhost:8000/servers/SERVER_ID/configs/refresh \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Посмотреть выбранные конфиги

```bash
curl 'http://localhost:8000/servers/SERVER_ID/configs?q=alex' \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Создать центральную подписку

```bash
curl -X POST http://localhost:8000/subscriptions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Alex subscription","user_id":"USER_ID","traffic_limit":107374182400}'
```

Ответ содержит:

- `token` — публичная ссылка клиента `/sub/{token}`;
- `shared_sub_id` — общий `subId`, который будет проставлен на 3x-ui.

### 6. Добавить config в подписку

```bash
curl -X POST http://localhost:8000/subscriptions/SUBSCRIPTION_ID/items/from-config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"remote_config_id":"REMOTE_CONFIG_ID","sort_order":100}'
```

### 7. Применить подписку к 3x-ui

```bash
curl -X POST http://localhost:8000/subscriptions/SUBSCRIPTION_ID/apply \
  -H "Authorization: Bearer $TOKEN"
```

`apply` делает для каждого выбранного client/config:

- `subId = subscription.shared_sub_id`;
- `expiryTime = subscription.expires_at`, если задан;
- `totalGB = subscription.traffic_limit`, если задан;
- `enable = true/false` по статусу подписки.

### 8. Preview

```bash
curl http://localhost:8000/subscriptions/SUBSCRIPTION_ID/preview \
  -H "Authorization: Bearer $TOKEN"
```

### 9. Публичная подписка для клиента

```bash
curl http://localhost:8000/sub/TOKEN
```

Публичная ссылка не требует admin token.

## Основные endpoints

### Public

- `GET /health`
- `GET /sub/{token}?format=plain|base64&use_cache_on_error=true`

### Auth

- `POST /auth/login`
- `GET /auth/me`

### Admin

- `POST /users`
- `GET /users`
- `GET /users/{id}`
- `PATCH /users/{id}`
- `POST /servers`
- `GET /servers`
- `GET /servers/{id}/health`
- `POST /servers/{id}/configs/refresh`
- `GET /servers/{id}/configs`
- `POST /subscriptions`
- `GET /subscriptions`
- `GET /subscriptions/{id}`
- `PUT/PATCH /subscriptions/{id}`
- `POST /subscriptions/{id}/items/from-config`
- `PUT /subscriptions/{id}/items/bulk`
- `POST /subscriptions/{id}/apply`
- `POST /subscriptions/{id}/reconcile`
- `GET /subscriptions/{id}/preview`
- `GET /subscriptions/{id}/traffic`
- `GET /subscriptions/{id}/cache`
- `POST /subscriptions/{id}/cache/refresh`
- `DELETE /subscriptions/{id}/cache`
- `GET /audit-log`
- `GET /subscriptions/{id}/events`

## Delete endpoints added in v0.6

All admin delete endpoints require the same Bearer token as the rest of the admin API.

```bash
# Delete subscription and its local items/cache
curl -X DELETE http://localhost:8000/subscriptions/<subscription_id> \
  -H "Authorization: Bearer <token>"

# Delete user only if it has no subscriptions
curl -X DELETE http://localhost:8000/users/<user_id> \
  -H "Authorization: Bearer <token>"

# Delete user and local subscriptions
curl -X DELETE 'http://localhost:8000/users/<user_id>?force=true' \
  -H "Authorization: Bearer <token>"

# Delete server only if it is not referenced by subscriptions/cache
curl -X DELETE http://localhost:8000/servers/<server_id> \
  -H "Authorization: Bearer <token>"

# Delete server and local references/config cache
curl -X DELETE 'http://localhost:8000/servers/<server_id>?force=true' \
  -H "Authorization: Bearer <token>"
```

Note: these delete local manager records only. They do not remove clients from remote 3x-ui instances.
