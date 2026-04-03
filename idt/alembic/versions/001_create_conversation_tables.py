"""Create conversation tables.

Revision ID: 001
Revises:
Create Date: 2026-01-22

Creates the conversation_message and conversation_summary tables
for multi-turn conversation management.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create conversation tables."""
    # Create conversation_message table
    op.create_table(
        'conversation_message',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('session_id', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('turn_index', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_message_user_session',
        'conversation_message',
        ['user_id', 'session_id'],
        unique=False,
    )

    # Create conversation_summary table
    op.create_table(
        'conversation_summary',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('session_id', sa.String(length=255), nullable=False),
        sa.Column('summary_content', sa.Text(), nullable=False),
        sa.Column('start_turn', sa.Integer(), nullable=False),
        sa.Column('end_turn', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_summary_user_session',
        'conversation_summary',
        ['user_id', 'session_id'],
        unique=False,
    )


def downgrade() -> None:
    """Drop conversation tables."""
    op.drop_index('ix_summary_user_session', table_name='conversation_summary')
    op.drop_table('conversation_summary')
    op.drop_index('ix_message_user_session', table_name='conversation_message')
    op.drop_table('conversation_message')
