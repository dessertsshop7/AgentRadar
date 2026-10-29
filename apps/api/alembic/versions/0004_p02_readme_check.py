"""区分尚未读取 README 与已确认缺失；不伪造历史检查时间。"""

import sqlalchemy as sa
from alembic import op

revision = "0004_p02_readme_check"
down_revision = "0003_p02_review"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "repositories", sa.Column("readme_checked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "repositories",
        sa.Column("readme_status", sa.String(20), nullable=False, server_default="unknown"),
    )
    op.execute("UPDATE repositories SET readme_status='available' WHERE readme_hash IS NOT NULL")


def downgrade():
    op.drop_column("repositories", "readme_status")
    op.drop_column("repositories", "readme_checked_at")
