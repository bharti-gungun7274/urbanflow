from pathlib import Path
import json
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "outputs"
HISTORY_FILE = OUTPUT_DIR / "history.json"


def ensure_output_directory():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text(
            "[]",
            encoding="utf-8"
        )


def load_history():
    ensure_output_directory()

    try:
        return json.loads(
            HISTORY_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return []


def save_history_record(
    area,
    year,
    total_points,
    validated_points,
    overall_accuracy,
    kappa,
):
    ensure_output_directory()

    history = load_history()

    record = {
        "area": area,
        "year": str(year),
        "total_points": int(total_points),
        "validated_points": int(validated_points),
        "overall_accuracy": float(
            overall_accuracy
        ),
        "kappa": float(kappa),
        "timestamp": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }

    history.insert(0, record)

    HISTORY_FILE.write_text(
        json.dumps(
            history,
            indent=2
        ),
        encoding="utf-8"
    )

    return record