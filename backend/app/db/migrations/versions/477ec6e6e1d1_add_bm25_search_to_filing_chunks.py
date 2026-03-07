"""add_bm25_search_to_filing_chunks

Revision ID: 477ec6e6e1d1
Revises: 1775362e301b
Create Date: 2026-03-07 19:32:56.055220

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '477ec6e6e1d1'
down_revision: Union[str, None] = '1775362e301b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE filing_chunks 
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
    """)

    op.execute("""
        CREATE INDEX ix_filing_chunks_content_tsv 
        ON filing_chunks 
        USING GIN(content_tsv)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_filing_chunks_content_tsv")
    op.execute("ALTER TABLE filing_chunks DROP COLUMN IF EXISTS content_tsv")
