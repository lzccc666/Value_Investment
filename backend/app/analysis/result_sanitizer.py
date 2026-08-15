from __future__ import annotations

import re


def sanitize_result_payload(result: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in result.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_error_text(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_error_text(item) if isinstance(item, str) else item for item in value
            ]
        elif isinstance(value, dict):
            sanitized[key] = sanitize_result_payload(value)
        else:
            sanitized[key] = value
    return sanitized


def sanitize_error_text(value: str) -> str:
    text = value.strip()
    title_match = re.search(r"<title>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        title = " ".join(title_match.group(1).split())
        prefix_match = re.match(r"^(.*?HTTP\s+\d+[^\n；;]*[；;])", text, flags=re.IGNORECASE)
        prefix = " ".join(prefix_match.group(1).split()) if prefix_match else ""
        return f"{prefix}{title}" if prefix else title

    text = re.sub(r"<!DOCTYPE[^>]*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())
