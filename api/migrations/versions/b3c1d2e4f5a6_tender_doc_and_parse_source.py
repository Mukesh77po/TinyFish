"""tender doc_source and eligibility_source (provenance)

Revision ID: b3c1d2e4f5a6
Revises: 99e5b6af0ae2
Create Date: 2026-10-24 22:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c1d2e4f5a6'
down_revision: Union[str, Sequence[str], None] = '99e5b6af0ae2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenders', sa.Column('doc_source', sa.String(length=16), nullable=True))
    op.add_column('tenders', sa.Column('eligibility_source', sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenders', 'eligibility_source')
    op.drop_column('tenders', 'doc_source')
