import json
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


class VlessConvertError(ValueError):
    pass


def _first(params: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
    values = params.get(key)
    if not values:
        return default
    return values[0]


def _has(params: dict[str, list[str]], key: str) -> bool:
    return key in params


def _to_int(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise VlessConvertError(f"Некорректный port: {value}") from exc


def _copy_extra_transport_settings(extra: dict[str, Any], transport: dict[str, Any]) -> None:
    if "xPaddingBytes" in extra:
        transport["x_padding_bytes"] = str(extra["xPaddingBytes"])
    if "noGRPCHeader" in extra:
        transport["no_grpc_header"] = extra["noGRPCHeader"]
    if "scMaxEachPostBytes" in extra:
        transport["sc_max_each_post_bytes"] = extra["scMaxEachPostBytes"]
    if "scMinPostsIntervalMs" in extra:
        transport["sc_min_posts_interval_ms"] = extra["scMinPostsIntervalMs"]
    if "scStreamUpServerSecs" in extra:
        transport["sc_stream_up_server_secs"] = str(extra["scStreamUpServerSecs"])

    xmux_src = extra.get("xmux")
    if isinstance(xmux_src, dict):
        xmux: dict[str, Any] = {}

        if "maxConcurrency" in xmux_src:
            xmux["max_concurrency"] = str(xmux_src["maxConcurrency"])
        if "maxConnections" in xmux_src:
            xmux["max_connections"] = xmux_src["maxConnections"]
        if "cMaxReuseTimes" in xmux_src:
            xmux["c_max_reuse_times"] = xmux_src["cMaxReuseTimes"]
        if "hMaxRequestTimes" in xmux_src:
            xmux["h_max_request_times"] = str(xmux_src["hMaxRequestTimes"])
        if "hMaxReusableSecs" in xmux_src:
            xmux["h_max_reusable_secs"] = str(xmux_src["hMaxReusableSecs"])
        if "hKeepAlivePeriod" in xmux_src:
            xmux["h_keep_alive_period"] = xmux_src["hKeepAlivePeriod"]

        if xmux:
            transport["xmux"] = xmux


def vless_url_to_sing_box_outbound(vless_url: str) -> dict[str, Any]:
    raw = vless_url.strip()

    if not raw.startswith("vless://"):
        raise VlessConvertError("Ссылка должна начинаться с vless://")

    parsed = urlparse(raw)

    if parsed.scheme != "vless":
        raise VlessConvertError("Поддерживается только схема vless://")

    if not parsed.username:
        raise VlessConvertError("В ссылке отсутствует UUID")

    if not parsed.hostname:
        raise VlessConvertError("В ссылке отсутствует server/host")

    params = parse_qs(parsed.query, keep_blank_values=True)

    uuid = unquote(parsed.username)
    server = parsed.hostname
    port = _to_int(str(parsed.port) if parsed.port else None, 443)
    tag = unquote(parsed.fragment) if parsed.fragment else "VLESS-XHTTP"

    transport_type = _first(params, "type", "xhttp") or "xhttp"
    path = _first(params, "path", "/") or "/"
    mode = _first(params, "mode", "auto") or "auto"
    x_padding_bytes = _first(params, "x_padding_bytes", "100-1000") or "100-1000"

    sni = _first(params, "sni", "") or ""
    host = _first(params, "host", sni) or sni

    security = _first(params, "security")
    is_reality = security == "reality"
    is_tls = security == "tls"

    pbk = _first(params, "pbk", "") or ""
    sid = _first(params, "sid", "") or ""
    fp = _first(params, "fp", "chrome") or "chrome"

    alpn_raw = _first(params, "alpn")
    if alpn_raw:
        alpn = [item for item in unquote(alpn_raw).split(",") if item]
    elif transport_type == "xhttp":
        alpn = ["h2", "http/1.1"]
    else:
        alpn = []

    tls: dict[str, Any] = {
        "enabled": True,
        "server_name": sni,
        "alpn": alpn,
    }

    if is_reality:
        tls["reality"] = {
            "enabled": True,
            "public_key": pbk,
            "short_id": sid,
        }
        tls["utls"] = {
            "enabled": True,
            "fingerprint": fp,
        }

    elif is_tls:
        if _has(params, "allowInsecure"):
            tls["insecure"] = _first(params, "allowInsecure") == "1"

        if _has(params, "fp"):
            tls["utls"] = {
                "enabled": True,
                "fingerprint": fp,
            }

    transport: dict[str, Any] = {
        "type": transport_type,
        "path": path,
        "mode": mode,
        "x_padding_bytes": x_padding_bytes,
    }

    if host:
        transport["host"] = host

    extra_raw = _first(params, "extra")
    if extra_raw:
        try:
            extra = json.loads(unquote(extra_raw))
            if isinstance(extra, dict):
                _copy_extra_transport_settings(extra, transport)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return {
        "type": "vless",
        "tag": tag,
        "server": server,
        "server_port": port,
        "uuid": uuid,
        "tls": tls,
        "transport": transport,
    }
