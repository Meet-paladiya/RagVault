"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Users
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('password_hash', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # Chats
    op.create_table('chats',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # Messages
    op.create_table('messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('chat_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('citations', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("role IN ('user', 'assistant')", name='role_check'),
    sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # Documents
    op.create_table('documents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('chat_id', sa.UUID(), nullable=False),
    sa.Column('filename', sa.String(), nullable=False),
    sa.Column('file_type', sa.String(), nullable=False),
    sa.Column('upload_time', sa.DateTime(), nullable=True),
    sa.Column('total_pages', sa.Integer(), nullable=True),
    sa.Column('total_chunks', sa.Integer(), nullable=True),
    sa.Column('chroma_collection', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.CheckConstraint("status IN ('processing', 'processed', 'failed')", name='status_check'),
    sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # Quizzes
    op.create_table('quizzes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('chat_id', sa.UUID(), nullable=False),
    sa.Column('topic', sa.String(), nullable=False),
    sa.Column('score', sa.Numeric(), nullable=True),
    sa.Column('total_questions', sa.Integer(), nullable=False),
    sa.Column('weak_topics', sa.JSON(), nullable=True),
    sa.Column('questions', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # User Memory
    op.create_table('user_memory',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('memory_text', sa.Text(), nullable=False),
    sa.Column('source_chat_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['source_chat_id'], ['chats.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('user_memory')
    op.drop_table('quizzes')
    op.drop_table('documents')
    op.drop_table('messages')
    op.drop_table('chats')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
