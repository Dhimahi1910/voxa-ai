from __future__ import annotations

import phonenumbers


def normalize_phone(raw: str | None, default_country: str = "IN") -> str | None:
    """Return E.164 or None if the number is not valid."""
    if not raw:
        return None
    text = str(raw).strip()
    try:
        num = phonenumbers.parse(text, None if text.startswith("+") else default_country)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(num):
        return None
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
