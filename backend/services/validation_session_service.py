from pathlib import Path
import json
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parents[2]
SESSION_DIR = BASE_DIR / "outputs" / "validation_sessions"


def _session_file(area: str, year: int) -> Path:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SESSION_DIR / f"{area}_{year}_session.json"


def load_session(area: str, year: int) -> dict:
    path = _session_file(area, year)

    if not path.exists():
        return {
            "area": area,
            "year": int(year),
            "validated_points": {},
        }

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError

        data.setdefault("area", area)
        data.setdefault("year", int(year))
        data.setdefault("validated_points", {})

        return data

    except (json.JSONDecodeError, ValueError):
        return {
            "area": area,
            "year": int(year),
            "validated_points": {},
        }


def save_point(
    area: str,
    year: int,
    point_id: int,
    reference_class: int,
    reference_source: str = "Sentinel-2",
) -> dict:

    path = _session_file(area, year)
    session = load_session(area, year)

    session["validated_points"][str(point_id)] = {
        "reference_class": int(reference_class),
        "reference_source": reference_source,
        "validated_at": datetime.now().isoformat(timespec="seconds"),
    }

    with path.open("w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)

    return {
        "status": "saved",
        "point_id": int(point_id),
        "session_file": str(path),
    }


def clear_session(area: str, year: int) -> None:
    path = _session_file(area, year)

    if path.exists():
        path.unlink()