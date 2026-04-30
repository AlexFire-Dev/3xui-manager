#!/bin/sh
set -eu

SUB_URL="http://10.27.50.10:5173/api/sub/your-sub-address"
CONVERTER_URL="http://10.27.50.10:8000/tools/vless-to-outbound"

CONFIG="/etc/sing-box/config.json"
SERVICE="sing-box"

HWID_FILE="/etc/sing-box/hwid"

# Если нужно принудительно оставить tag = proxy, укажи:
# FORCE_TAG="proxy"
FORCE_TAG=""

get_or_create_hwid() {
  if [ -s "$HWID_FILE" ]; then
    cat "$HWID_FILE"
    return
  fi

  mkdir -p "$(dirname "$HWID_FILE")"

  if [ -r /proc/sys/kernel/random/uuid ]; then
    HWID="$(cat /proc/sys/kernel/random/uuid)"
  else
    HWID="$(hexdump -n 16 -e '4/4 "%08x" 1 "\n"' /dev/urandom)"
  fi

  echo "$HWID" > "$HWID_FILE"
  chmod 600 "$HWID_FILE"

  echo "$HWID"
}

command -v curl >/dev/null 2>&1 || {
  echo "ERROR: curl not found"
  echo "Install: opkg update && opkg install curl"
  exit 1
}

command -v jq >/dev/null 2>&1 || {
  echo "ERROR: jq not found"
  echo "Install: opkg update && opkg install jq"
  exit 1
}

[ -f "$CONFIG" ] || {
  echo "ERROR: config not found: $CONFIG"
  exit 1
}

HWID="$(get_or_create_hwid)"

TMP_DIR="$(mktemp -d /tmp/singbox-update.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

SUB_FILE="$TMP_DIR/sub.txt"
REQ_FILE="$TMP_DIR/request.json"
RESP_FILE="$TMP_DIR/response.json"
OUTBOUND_FILE="$TMP_DIR/outbound.json"
NEW_CONFIG="$TMP_DIR/config.json"

BACKUP="${CONFIG}.bak.$(date +%Y%m%d-%H%M%S)"

echo "Using HWID: $HWID"

echo "Fetching subscription..."

HTTP_CODE="$(curl -k -sS -L \
  -H "X-HWID: $HWID" \
  -w "%{http_code}" \
  -o "$SUB_FILE" \
  "$SUB_URL")"

if [ "$HTTP_CODE" != "200" ]; then
  echo "ERROR: subscription request failed"
  echo "HTTP status: $HTTP_CODE"
  echo "Response body:"
  cat "$SUB_FILE"
  echo
  exit 1
fi

VLESS_URL="$(tr -d '\r' < "$SUB_FILE" | sed -n '/^vless:\/\//{p;q;}')"

if [ -z "$VLESS_URL" ]; then
  echo "ERROR: no vless:// URL found in subscription response"
  echo "Subscription response:"
  cat "$SUB_FILE"
  echo
  exit 1
fi

VLESS_FLOW="$(printf '%s\n' "$VLESS_URL" | sed -n 's/.*[?&]flow=\([^&#]*\).*/\1/p')"

echo "Found VLESS URL:"
echo "$VLESS_URL"

echo "Converting VLESS URL to sing-box outbound..."
jq -n --arg url "$VLESS_URL" '{url: $url}' > "$REQ_FILE"

HTTP_CODE="$(curl -k -sS -L \
  -X POST "$CONVERTER_URL" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -w "%{http_code}" \
  -d @"$REQ_FILE" \
  -o "$RESP_FILE")"

if [ "$HTTP_CODE" != "200" ]; then
  echo "ERROR: converter request failed"
  echo "HTTP status: $HTTP_CODE"
  echo "Response body:"
  cat "$RESP_FILE"
  echo
  exit 1
fi

echo "Validating converter response..."
if ! jq -e '.outbound and .outbound.type' "$RESP_FILE" >/dev/null; then
  echo "ERROR: converter returned invalid response"
  echo "Response body:"
  cat "$RESP_FILE"
  echo
  exit 1
fi

jq -e --arg flow "$VLESS_FLOW" '
  .outbound

  # sing-box не принимает transport.type = "tcp".
  # Для обычного TCP нужно удалить transport и поставить network = "tcp".
  | if .transport.type == "tcp" then
      .network = "tcp" | del(.transport)
    else
      .
    end

  # Если flow был в VLESS-ссылке, но конвертер его не добавил — добавляем.
  | if ($flow != "" and (.flow == null or .flow == "")) then
      .flow = $flow
    else
      .
    end
' "$RESP_FILE" > "$OUTBOUND_FILE"

if [ -n "$FORCE_TAG" ]; then
  jq --arg tag "$FORCE_TAG" '.tag = $tag' "$OUTBOUND_FILE" > "$TMP_DIR/outbound_tagged.json"
  mv "$TMP_DIR/outbound_tagged.json" "$OUTBOUND_FILE"
fi

echo "New outbound:"
jq . "$OUTBOUND_FILE"

echo "Creating backup:"
echo "$BACKUP"
cp "$CONFIG" "$BACKUP"

echo "Updating outbounds section..."
jq --slurpfile outbound "$OUTBOUND_FILE" '.outbounds = [$outbound[0]]' "$CONFIG" > "$NEW_CONFIG"

echo "Validating new JSON config..."
jq -e . "$NEW_CONFIG" >/dev/null

if command -v sing-box >/dev/null 2>&1; then
  echo "Checking sing-box config..."
  sing-box check -c "$NEW_CONFIG"
fi

cp "$NEW_CONFIG" "$CONFIG"

echo "Restarting $SERVICE..."
if /etc/init.d/"$SERVICE" restart; then
  echo "Restarting OpenWrt network..."
  /etc/init.d/network restart
else
  echo "ERROR: $SERVICE restart failed"
  echo "Rolling back config..."
  cp "$BACKUP" "$CONFIG"
  /etc/init.d/"$SERVICE" restart || true
  exit 1
fi

echo "Done."
echo "Backup saved at: $BACKUP"
