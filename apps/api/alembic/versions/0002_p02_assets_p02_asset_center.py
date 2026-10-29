"""P02 asset center

Revision ID: 0002_p02_assets
Revises: 0001_p00_baseline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_p02_assets"
down_revision: str | Sequence[str] | None = "0001_p00_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 发布指针形成循环引用：先建表，最后添加所属版本复合外键。
    op.create_table(
        "asset_categories",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=300), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("review_state", sa.String(length=20), nullable=False),
        sa.Column("published_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("asset_type IN ('tool','agent','skill','mcp','framework')"),
        sa.CheckConstraint("review_state IN ('pending','approved','needs_review','withdrawn')"),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("source_id", "external_id"),
    )
    op.create_index(
        op.f("ix_assets_published_version_id"), "assets", ["published_version_id"], unique=False
    )
    op.create_index(op.f("ix_assets_review_state"), "assets", ["review_state"], unique=False)
    op.create_index(op.f("ix_assets_source_id"), "assets", ["source_id"], unique=False)
    op.create_table(
        "repositories",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("full_name", sa.String(length=300), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("license", sa.String(length=100), nullable=True),
        sa.Column("stars", sa.BigInteger(), nullable=False),
        sa.Column("forks", sa.BigInteger(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("availability", sa.String(length=20), nullable=False),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("readme_hash", sa.String(length=64), nullable=True),
        sa.Column("readme_etag", sa.Text(), nullable=True),
        sa.Column("readme_checked_pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("availability IN ('active', 'unverified', 'withdrawn')"),
        sa.CheckConstraint("stars >= 0 AND forks >= 0"),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id"),
    )
    op.create_index(op.f("ix_repositories_full_name"), "repositories", ["full_name"], unique=False)
    op.create_index(op.f("ix_repositories_source_id"), "repositories", ["source_id"], unique=False)
    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=40), nullable=False),
        sa.Column("trigger", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("status IN ('running','succeeded','partial','failed','interrupted')"),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sync_jobs_source_id"), "sync_jobs", ["source_id"], unique=False)
    op.create_index(op.f("ix_sync_jobs_status"), "sync_jobs", ["status"], unique=False)
    op.create_table(
        "asset_category_links",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.String(length=40), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["asset_categories.id"],
        ),
        sa.PrimaryKeyConstraint("asset_id", "category_id"),
    )
    op.create_index(
        op.f("ix_asset_category_links_category_id"),
        "asset_category_links",
        ["category_id"],
        unique=False,
    )
    op.create_table(
        "asset_repositories",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("asset_id", "repository_id"),
    )
    op.create_index(
        op.f("ix_asset_repositories_repository_id"),
        "asset_repositories",
        ["repository_id"],
        unique=False,
    )
    op.create_index(
        "uq_primary_repository",
        "asset_repositories",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )
    op.create_table(
        "repository_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", "content_hash"),
    )
    op.create_index(
        op.f("ix_repository_documents_repository_id"),
        "repository_documents",
        ["repository_id"],
        unique=False,
    )
    op.create_table(
        "repository_snapshots",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stars", sa.BigInteger(), nullable=False),
        sa.Column("forks", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["sync_jobs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", "job_id"),
    )
    op.create_index(
        op.f("ix_repository_snapshots_job_id"), "repository_snapshots", ["job_id"], unique=False
    )
    op.create_index(
        op.f("ix_repository_snapshots_repository_id"),
        "repository_snapshots",
        ["repository_id"],
        unique=False,
    )
    op.create_index(
        "ix_snapshot_observation",
        "repository_snapshots",
        ["repository_id", "observed_at"],
        unique=False,
    )
    op.create_table(
        "sync_errors",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("item_key", sa.String(length=300), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["sync_jobs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sync_errors_job_id"), "sync_errors", ["job_id"], unique=False)
    op.create_table(
        "trend_scores",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("formula_version", sa.String(length=40), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("components", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("star_growth", sa.Integer(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
        ),
        sa.PrimaryKeyConstraint("asset_id"),
    )
    op.create_index(
        op.f("ix_trend_scores_window_end"), "trend_scores", ["window_end"], unique=False
    )
    op.create_table(
        "asset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("repository_document_id", sa.Uuid(), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("name_zh", sa.String(length=300), nullable=True),
        sa.Column("summary_zh", sa.Text(), nullable=True),
        sa.Column("description_zh", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("cost", sa.String(length=120), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scenarios", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("limitations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_origin", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.CheckConstraint("content_origin IN ('source_metadata','assistant_draft','human')"),
        sa.CheckConstraint("difficulty IN ('unknown','beginner','visual','developer')"),
        sa.CheckConstraint(
            "status <> 'approved' OR (summary_zh IS NOT NULL AND summary_zh ~ '[一-鿿]' "
            "AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_approved_chinese_and_review",
        ),
        sa.CheckConstraint("status IN ('draft','approved','rejected')"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["repository_document_id"],
            ["repository_documents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "id"),
        sa.UniqueConstraint("asset_id", "source_hash", "content_hash"),
    )
    op.create_index(
        op.f("ix_asset_versions_asset_id"), "asset_versions", ["asset_id"], unique=False
    )
    op.create_index(
        op.f("ix_asset_versions_repository_document_id"),
        "asset_versions",
        ["repository_document_id"],
        unique=False,
    )
    op.create_index(op.f("ix_asset_versions_status"), "asset_versions", ["status"], unique=False)
    op.create_foreign_key(
        "fk_asset_own_published_version",
        "assets",
        "asset_versions",
        ["id", "published_version_id"],
        ["asset_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_asset_own_published_version", "assets", type_="foreignkey")
    op.drop_index(op.f("ix_asset_versions_status"), table_name="asset_versions")
    op.drop_index(op.f("ix_asset_versions_repository_document_id"), table_name="asset_versions")
    op.drop_index(op.f("ix_asset_versions_asset_id"), table_name="asset_versions")
    op.drop_table("asset_versions")
    op.drop_index(op.f("ix_trend_scores_window_end"), table_name="trend_scores")
    op.drop_table("trend_scores")
    op.drop_index(op.f("ix_sync_errors_job_id"), table_name="sync_errors")
    op.drop_table("sync_errors")
    op.drop_index("ix_snapshot_observation", table_name="repository_snapshots")
    op.drop_index(op.f("ix_repository_snapshots_repository_id"), table_name="repository_snapshots")
    op.drop_index(op.f("ix_repository_snapshots_job_id"), table_name="repository_snapshots")
    op.drop_table("repository_snapshots")
    op.drop_index(op.f("ix_repository_documents_repository_id"), table_name="repository_documents")
    op.drop_table("repository_documents")
    op.drop_index(
        "uq_primary_repository",
        table_name="asset_repositories",
        postgresql_where=sa.text("is_primary"),
    )
    op.drop_index(op.f("ix_asset_repositories_repository_id"), table_name="asset_repositories")
    op.drop_table("asset_repositories")
    op.drop_index(op.f("ix_asset_category_links_category_id"), table_name="asset_category_links")
    op.drop_table("asset_category_links")
    op.drop_index(op.f("ix_sync_jobs_status"), table_name="sync_jobs")
    op.drop_index(op.f("ix_sync_jobs_source_id"), table_name="sync_jobs")
    op.drop_table("sync_jobs")
    op.drop_index(op.f("ix_repositories_source_id"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_full_name"), table_name="repositories")
    op.drop_table("repositories")
    op.drop_index(op.f("ix_assets_source_id"), table_name="assets")
    op.drop_index(op.f("ix_assets_review_state"), table_name="assets")
    op.drop_index(op.f("ix_assets_published_version_id"), table_name="assets")
    op.drop_table("assets")
    op.drop_table("sources")
    op.drop_table("asset_categories")
