"""SQLAlchemy models: tenders, profiles, matches (CLAUDE.md core data model)."""
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from api.config import EMBEDDING_DIM


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class Tender(Timestamps, Base):
    __tablename__ = "tenders"
    __table_args__ = (UniqueConstraint("portal", "bid_no", name="uq_tender_portal_bid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portal: Mapped[str] = mapped_column(String(16))
    bid_no: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(Text)
    item: Mapped[str | None] = mapped_column(Text)
    buyer: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[str | None] = mapped_column(Text)  # free text from portals; never cap it
    est_value: Mapped[float | None] = mapped_column(Float)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    doc_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    doc_text: Mapped[str | None] = mapped_column(Text)
    doc_source: Mapped[str | None] = mapped_column(String(16))  # fetch | direct | fixture
    eligibility: Mapped[dict | None] = mapped_column(JSONB)       # PLAN.md §3.4
    eligibility_source: Mapped[str | None] = mapped_column(String(16))  # llm | recorded
    corrigenda: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)


class Profile(Timestamps, Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(200))
    products: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)   # search terms for portal sweeps
    hsn_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    annual_turnover: Mapped[int | None] = mapped_column(BigInteger)         # INR
    years_in_business: Mapped[int | None] = mapped_column(Integer)
    certifications: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    states_served: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    matches: Mapped[list["Match"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class Match(Timestamps, Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("profile_id", "tender_id", name="uq_match_profile_tender"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    verdict: Mapped[str] = mapped_column(String(16))   # ELIGIBLE | CHECK_DOCS | NOT_ELIGIBLE
    reasons: Mapped[list] = mapped_column(JSONB, default=list)        # [{"text", "source_clause", "kind"}]
    missing_docs: Mapped[list] = mapped_column(JSONB, default=list)
    fit_score: Mapped[float | None] = mapped_column(Float)
    relevant: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")  # fit above threshold
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped[Profile] = relationship(back_populates="matches")
    tender: Mapped[Tender] = relationship()
