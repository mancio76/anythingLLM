"""Initial database schema

Revision ID: 0001
Revises: 
Create Date: 2024-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create job status enum
    job_status_enum = postgresql.ENUM(
        'pending', 'processing', 'completed', 'failed', 'cancelled',
        name='jobstatus'
    )
    job_status_enum.create(op.get_bind())
    
    # Create job type enum
    job_type_enum = postgresql.ENUM(
        'document_upload', 'question_processing', 'workspace_creation', 'workspace_deletion',
        name='jobtype'
    )
    job_type_enum.create(op.get_bind())
    
    # Create workspace status enum
    workspace_status_enum = postgresql.ENUM(
        'active', 'inactive', 'deleted', 'error',
        name='workspacestatus'
    )
    workspace_status_enum.create(op.get_bind())
    
    # Create LLM provider enum
    llm_provider_enum = postgresql.ENUM(
        'openai', 'ollama', 'anthropic',
        name='llmprovider'
    )
    llm_provider_enum.create(op.get_bind())
    
    # Create workspaces table
    op.create_table(
        'workspaces',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False, index=True),
        sa.Column('slug', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', workspace_status_enum, nullable=False, default='active', index=True),
        sa.Column('document_count', sa.Integer(), nullable=False, default=0),
        sa.Column('llm_provider', llm_provider_enum, nullable=False, default='openai'),
        sa.Column('llm_model', sa.String(100), nullable=False, default='gpt-3.5-turbo'),
        sa.Column('llm_temperature', sa.Float(), nullable=False, default=0.7),
        sa.Column('llm_max_tokens', sa.Integer(), nullable=True),
        sa.Column('llm_timeout', sa.Integer(), nullable=False, default=30),
        sa.Column('procurement_prompts', sa.Boolean(), nullable=False, default=True),
        sa.Column('auto_embed', sa.Boolean(), nullable=False, default=True),
        sa.Column('max_documents', sa.Integer(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False, index=True),
    )
    
    # Create jobs table
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('type', job_type_enum, nullable=False, index=True),
        sa.Column('status', job_status_enum, nullable=False, default='pending', index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('progress', sa.Float(), nullable=False, default=0.0),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False, index=True),
    )
    
    # Create questions table
    op.create_table(
        'questions',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('expected_fragments', sa.JSON(), nullable=False, default=[]),
        sa.Column('llm_provider', llm_provider_enum, nullable=True),
        sa.Column('llm_model', sa.String(100), nullable=True),
        sa.Column('llm_temperature', sa.Float(), nullable=True),
        sa.Column('llm_max_tokens', sa.Integer(), nullable=True),
        sa.Column('llm_timeout', sa.Integer(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False, index=True),
    )
    
    # Create question_results table
    op.create_table(
        'question_results',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('question_id', sa.String(36), sa.ForeignKey('questions.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('response', sa.Text(), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=False, default=0.0),
        sa.Column('processing_time', sa.Float(), nullable=False, default=0.0),
        sa.Column('fragments_found', sa.JSON(), nullable=False, default=[]),
        sa.Column('success', sa.Boolean(), nullable=False, default=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False, index=True),
    )
    
    # Create indexes
    op.create_index('idx_jobs_status_type', 'jobs', ['status', 'type'])
    op.create_index('idx_jobs_workspace_status', 'jobs', ['workspace_id', 'status'])
    op.create_index('idx_jobs_created_status', 'jobs', ['created_at', 'status'])
    
    op.create_index('idx_workspaces_name_status', 'workspaces', ['name', 'status'])
    op.create_index('idx_workspaces_status_created', 'workspaces', ['status', 'created_at'])
    
    op.create_index('idx_questions_workspace_created', 'questions', ['workspace_id', 'created_at'])
    
    op.create_index('idx_question_results_job_success', 'question_results', ['job_id', 'success'])
    op.create_index('idx_question_results_confidence', 'question_results', ['confidence_score'])
    
    # Create unique constraint
    op.create_unique_constraint('uq_job_question', 'question_results', ['job_id', 'question_id'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('question_results')
    op.drop_table('questions')
    op.drop_table('jobs')
    op.drop_table('workspaces')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS llmprovider')
    op.execute('DROP TYPE IF EXISTS workspacestatus')
    op.execute('DROP TYPE IF EXISTS jobtype')
    op.execute('DROP TYPE IF EXISTS jobstatus')