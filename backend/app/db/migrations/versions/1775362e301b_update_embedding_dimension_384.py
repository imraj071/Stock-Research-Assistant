"""update_embedding_dimension_384

Revision ID: 1775362e301b
Revises: 80d6b1900072
Create Date: 2026-03-07 18:54:23.624519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1775362e301b'
down_revision: Union[str, None] = '80d6b1900072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE filing_chunks ALTER COLUMN embedding TYPE vector(384)")


def downgrade() -> None:
    op.execute("ALTER TABLE filing_chunks ALTER COLUMN embedding TYPE vector(1536)")
