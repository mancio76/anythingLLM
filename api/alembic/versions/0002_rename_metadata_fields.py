"""Rename metadata fields to avoid SQLAlchemy conflicts

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename metadata columns to avoid SQLAlchemy reserved word conflicts."""
    
    # Rename metadata column in jobs table
    op.alter_column('jobs', 'metadata', new_column_name='job_metadata')
    
    # Rename metadata column in workspaces table
    op.alter_column('workspaces', 'metadata', new_column_name='workspace_metadata')
    
    # Rename metadata column in questions table
    op.alter_column('questions', 'metadata', new_column_name='question_metadata')
    
    # Rename metadata column in question_results table
    op.alter_column('question_results', 'metadata', new_column_name='result_metadata')


def downgrade() -> None:
    """Revert metadata column name changes."""
    
    # Revert metadata column in jobs table
    op.alter_column('jobs', 'job_metadata', new_column_name='metadata')
    
    # Revert metadata column in workspaces table
    op.alter_column('workspaces', 'workspace_metadata', new_column_name='metadata')
    
    # Revert metadata column in questions table
    op.alter_column('questions', 'question_metadata', new_column_name='metadata')
    
    # Revert metadata column in question_results table
    op.alter_column('question_results', 'result_metadata', new_column_name='metadata')