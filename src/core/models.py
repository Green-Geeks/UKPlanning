from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Council(Base):
    __tablename__ = "councils"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    authority_code: Mapped[str] = mapped_column(String(100), unique=True)
    platform: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[str] = mapped_column(Text)
    schedule_cron: Mapped[str] = mapped_column(String(50), default="0 3 * * *")
    requires_js: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_successful_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    applications: Mapped[List["Application"]] = relationship(back_populates="council")
    scrape_runs: Mapped[List["ScrapeRun"]] = relationship(back_populates="council")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("council_id", "reference", name="uq_council_reference"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    council_id: Mapped[int] = mapped_column(ForeignKey("councils.id"))
    reference: Mapped[str] = mapped_column(String(100))
    url: Mapped[Optional[str]] = mapped_column(Text)
    address: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    application_type: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[Optional[str]] = mapped_column(String(100))
    decision: Mapped[Optional[str]] = mapped_column(String(255))
    date_received: Mapped[Optional[date]] = mapped_column(Date)
    date_validated: Mapped[Optional[date]] = mapped_column(Date)
    ward: Mapped[Optional[str]] = mapped_column(String(255))
    parish: Mapped[Optional[str]] = mapped_column(String(255))
    applicant_name: Mapped[Optional[str]] = mapped_column(String(255))
    case_officer: Mapped[Optional[str]] = mapped_column(String(255))
    first_scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON)

    council: Mapped["Council"] = relationship(back_populates="applications")


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    council_id: Mapped[int] = mapped_column(ForeignKey("councils.id"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50))
    applications_found: Mapped[int] = mapped_column(Integer, default=0)
    applications_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    date_range_from: Mapped[Optional[date]] = mapped_column(Date)
    date_range_to: Mapped[Optional[date]] = mapped_column(Date)

    council: Mapped["Council"] = relationship(back_populates="scrape_runs")
