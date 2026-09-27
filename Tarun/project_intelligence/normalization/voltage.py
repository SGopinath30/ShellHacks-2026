"""Voltage normalization without model inference."""

from __future__ import annotations

import re


def normalize_voltage_kv(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        voltage = float(value)
    else:
        text = str(value).strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            voltage = float(text)
            return voltage if 0 < voltage <= 2_000 else None
        match = re.search(
            r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:k\s*v|kilovolts?)\b",
            text,
            re.I,
        )
        if match is None:
            return None
        voltage = float(match.group(1))
    return voltage if 0 < voltage <= 2_000 else None


def extract_voltages_kv(value: object) -> list[float]:
    if value is None:
        return []
    matches = re.findall(
        r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:k\s*v|kilovolts?)\b",
        str(value),
        re.I,
    )
    return list(dict.fromkeys(float(match) for match in matches))
