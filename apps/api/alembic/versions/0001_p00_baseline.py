"""P00 空基线：尚无业务实体，仅通过 Alembic 记录迁移版本。"""

revision: str = "0001_p00_baseline"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
