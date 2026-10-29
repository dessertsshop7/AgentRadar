"""P02 资产中心；采集事实、内容版本和审核发布指针分开保存。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        CheckConstraint("availability IN ('active', 'unverified', 'withdrawn')"),
        CheckConstraint("stars >= 0 AND forks >= 0"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    full_name: Mapped[str] = mapped_column(String(300), index=True)
    canonical_url: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(100))
    stars: Mapped[int] = mapped_column(BigInteger, default=0)
    forks: Mapped[int] = mapped_column(BigInteger, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    availability: Mapped[str] = mapped_column(String(20), default="active")
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    readme_hash: Mapped[str | None] = mapped_column(String(64))
    readme_etag: Mapped[str | None] = mapped_column(Text)
    readme_checked_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RepositoryDocument(Base):
    __tablename__ = "repository_documents"
    __table_args__ = (UniqueConstraint("repository_id", "content_hash"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        CheckConstraint("asset_type IN ('tool','agent','skill','mcp','framework')"),
        CheckConstraint("review_state IN ('pending','approved','needs_review','withdrawn')"),
        ForeignKeyConstraint(
            ["id", "published_version_id"],
            ["asset_versions.asset_id", "asset_versions.id"],
            name="fk_asset_own_published_version",
            use_alter=True,
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(300))
    slug: Mapped[str] = mapped_column(String(180), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    asset_type: Mapped[str] = mapped_column(String(20), default="tool")
    review_state: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    published_version_id: Mapped[UUID | None] = mapped_column(index=True)
    current_source_hash: Mapped[str | None] = mapped_column(String(64))
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AssetVersion(Base):
    __tablename__ = "asset_versions"
    __table_args__ = (
        UniqueConstraint("asset_id", "id"),
        UniqueConstraint("asset_id", "source_hash", "content_hash"),
        CheckConstraint("status IN ('draft','approved','rejected')"),
        CheckConstraint("difficulty IN ('unknown','beginner','visual','developer')"),
        CheckConstraint("content_origin IN ('source_metadata','assistant_draft','human')"),
        CheckConstraint(
            "status <> 'approved' OR (summary_zh IS NOT NULL AND summary_zh ~ '[一-鿿]' "
            "AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_approved_chinese_and_review",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), index=True)
    repository_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("repository_documents.id"), index=True
    )
    source_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    name_zh: Mapped[str | None] = mapped_column(String(300))
    summary_zh: Mapped[str | None] = mapped_column(Text)
    description_zh: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(20), default="unknown")
    cost: Mapped[str] = mapped_column(String(120), default="unknown")
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    categories: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    scenarios: Mapped[list] = mapped_column(JSONB, default=list)
    requirements: Mapped[list] = mapped_column(JSONB, default=list)
    limitations: Mapped[list] = mapped_column(JSONB, default=list)
    content_origin: Mapped[str] = mapped_column(String(30), default="source_metadata")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)


class AssetRepository(Base):
    __tablename__ = "asset_repositories"
    __table_args__ = (
        Index(
            "uq_primary_repository", "asset_id", unique=True, postgresql_where=text("is_primary")
        ),
    )
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id"), primary_key=True, index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class AssetCategory(Base):
    __tablename__ = "asset_categories"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(120))


class AssetCategoryLink(Base):
    __tablename__ = "asset_category_links"
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    category_id: Mapped[str] = mapped_column(
        ForeignKey("asset_categories.id"), primary_key=True, index=True
    )
    evidence: Mapped[str] = mapped_column(Text)


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('running','succeeded','partial','failed','interrupted')"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    trigger: Mapped[str] = mapped_column(String(30), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    coverage: Mapped[dict] = mapped_column(JSONB, default=dict)


class SyncError(Base):
    __tablename__ = "sync_errors"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("sync_jobs.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    item_key: Mapped[str | None] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RepositorySnapshot(Base):
    __tablename__ = "repository_snapshots"
    __table_args__ = (
        UniqueConstraint("repository_id", "job_id"),
        Index("ix_snapshot_observation", "repository_id", "observed_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("sync_jobs.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stars: Mapped[int] = mapped_column(BigInteger)
    forks: Mapped[int] = mapped_column(BigInteger)


class TrendScore(Base):
    __tablename__ = "trend_scores"
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    formula_version: Mapped[str] = mapped_column(String(40))
    score: Mapped[float] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(JSONB)
    star_growth: Mapped[int | None] = mapped_column(Integer)
    sample_count: Mapped[int] = mapped_column(Integer)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
