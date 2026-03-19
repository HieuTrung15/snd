from __future__ import annotations

def bootstrap(units: int = 5) -> dict:
    """
    Kept for backward compatibility only.
    No install-time data bootstrap is executed.
    """
    return {"ok": True, "skipped": True, "units": units}
