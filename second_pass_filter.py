from __future__ import annotations

MODES={
    "off": "",
    "light": "hqdn3d=1.0:1.0:2.0:2.0,unsharp=5:5:0.30:5:5:0",
    "strong": "hqdn3d=1.5:1.5:3.0:3.0,unsharp=5:5:0.40:5:5:0",
}

def filter_for(mode: str) -> str:
    return MODES.get(mode, MODES["off"])

def append_filter(existing: list[str], mode: str) -> list[str]:
    extra=filter_for(mode)
    return existing + ([extra] if extra else [])
