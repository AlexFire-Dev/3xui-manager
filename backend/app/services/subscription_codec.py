import base64
import binascii
from urllib.parse import unquote


def maybe_decode_subscription(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""

    # If it already looks like a line-based proxy list, keep it.
    if "://" in text:
        return text

    # Many subscription endpoints return base64 without padding.
    padded = text + "=" * (-len(text) % 4)
    try:
        decoded = base64.b64decode(padded, validate=False).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return text

    return decoded if "://" in decoded else text


def normalize_links(raw: str, prefix: str | None = None) -> list[str]:
    decoded = maybe_decode_subscription(raw)
    links: list[str] = []
    for line in decoded.replace("\r", "\n").split("\n"):
        link = line.strip()
        if not link or "://" not in link:
            continue
        if prefix and "#" in link:
            base, name = link.rsplit("#", 1)
            link = f"{base}#{prefix}-{unquote(name)}"
        elif prefix:
            link = f"{link}#{prefix}"
        links.append(link)
    return links


def encode_response(links: list[str], fmt: str) -> str:
    body = "\n".join(links) + ("\n" if links else "")
    if fmt == "base64":
        return base64.b64encode(body.encode()).decode()
    return body
