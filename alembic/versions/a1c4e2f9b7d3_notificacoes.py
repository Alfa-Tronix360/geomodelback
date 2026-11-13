"""notificações (sino)

Revision ID: a1c4e2f9b7d3
Revises: d0a76be47329
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e2f9b7d3"
down_revision: Union[str, None] = "d0a76be47329"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("titulo", sa.String(160), nullable=False),
        sa.Column("mensagem", sa.Text()),
        sa.Column("link", sa.String(255)),
        sa.Column("chave", sa.String(120)),
        sa.Column("lida_em", sa.DateTime(timezone=True)),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notifications_user_lida", "notifications", ["user_id", "lida_em"])
    op.create_index("ix_notifications_user_chave", "notifications", ["user_id", "chave"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_chave", table_name="notifications")
    op.drop_index("ix_notifications_user_lida", table_name="notifications")
    op.drop_table("notifications")
