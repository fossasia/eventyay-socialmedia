from urllib.parse import urlparse


def normalize_telegram_chat_id(value: str) -> str:
    value = (value or "").strip()
    parse_value = value
    if value.startswith(("t.me/", "telegram.me/")):
        parse_value = f"https://{value}"

    parsed = urlparse(parse_value)
    if parsed.netloc in {"t.me", "telegram.me"}:
        path = parsed.path.strip("/")
        if path and not path.startswith(("+", "joinchat/")):
            return f"@{path.split('/')[0]}"

    if parsed.netloc == "web.telegram.org" and parsed.fragment:
        chat_id = parsed.fragment.strip()
        if chat_id.startswith("-") and not chat_id.startswith("-100"):
            return f"-100{chat_id.removeprefix('-')}"
        return chat_id

    return value
