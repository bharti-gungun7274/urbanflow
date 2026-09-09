from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    is_active: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )


class ValidationRecord(Base):
    __tablename__ = "validation_records"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    area: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    point_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    reference_class: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    reference_source: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    validated_by: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    validated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "validated_by",
            "area",
            "year",
            "point_id",
            name="uq_validation_user_area_year_point",
        ),
    )


class ValidationHistory(Base):
    __tablename__ = "validation_history"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    area: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    point_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    reference_class: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    changed_by: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    reference_source: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    changed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )