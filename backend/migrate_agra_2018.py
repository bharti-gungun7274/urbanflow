import json

from backend.database import SessionLocal
from backend.models import ValidationRecord


SESSION_FILE = (
    "outputs/validation_sessions/Agra_2018_session.json"
)


def migrate():
    with open(
        SESSION_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    validated_points = data.get(
        "validated_points",
        {},
    )

    db = SessionLocal()

    inserted = 0
    skipped = 0

    try:
        for point_id, record in validated_points.items():

            point_id = int(point_id)

            existing = (
                db.query(ValidationRecord)
                .filter(
                    ValidationRecord.area == "Agra",
                    ValidationRecord.year == 2018,
                    ValidationRecord.point_id == point_id,
                )
                .first()
            )

            if existing:
                skipped += 1
                continue

            validation = ValidationRecord(
                area="Agra",
                year=2018,
                point_id=point_id,
                reference_class=int(
                    record["reference_class"]
                ),
                reference_source=str(
                    record["reference_source"]
                ),
                validated_by=1,
            )

            db.add(validation)
            inserted += 1

        db.commit()

        print("Migration completed.")
        print("Inserted:", inserted)
        print("Already existed:", skipped)

    except Exception as exc:
        db.rollback()
        print("Migration failed:", exc)

    finally:
        db.close()


if __name__ == "__main__":
    migrate()