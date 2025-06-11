"""Add ON DELETE CASCADE to user_settings, user_business, and user_permissions

Revision ID: 5bdbc0d87a02
Revises: 4aa9331d58e2
Create Date: 2025-06-11 18:56:00.838690
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic
revision = '5bdbc0d87a02'
down_revision = '4aa9331d58e2'
branch_labels = None
depends_on = None

# Reference the existing notificationmethod enum
notification_method_enum = ENUM(
    'whatsapp', 'email', 'both',
    name='notificationmethod',
    create_type=False
)

def upgrade():
    # Step 1: Clean up invalid data
    # Delete user_settings rows with user_id = NULL
    op.execute("DELETE FROM user_settings WHERE user_id IS NULL")
    # Delete orphaned user_business rows
    op.execute("DELETE FROM user_business WHERE user_id NOT IN (SELECT id FROM users)")
    # Delete orphaned user_permissions rows
    op.execute("DELETE FROM user_permissions WHERE user_id NOT IN (SELECT id FROM users)")

    # Step 2: Update foreign keys to ON DELETE CASCADE
    # user_settings.user_id
    op.drop_constraint('user_settings_user_id_fkey', 'user_settings', type_='foreignkey')
    op.create_foreign_key(
        'user_settings_user_id_fkey',
        'user_settings',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # user_business.user_id
    op.drop_constraint('user_business_user_id_fkey', 'user_business', type_='foreignkey')
    op.create_foreign_key(
        'user_business_user_id_fkey',
        'user_business',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # user_permissions.user_id
    op.drop_constraint('user_permissions_user_id_fkey', 'user_permissions', type_='foreignkey')
    op.create_foreign_key(
        'user_permissions_user_id_fkey',
        'user_permissions',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Step 3: Create missing user_settings records for existing users
    op.execute("""
        INSERT INTO user_settings (user_id, notification_method, created_at)
        SELECT u.id, 'both', NOW()
        FROM users u
        LEFT JOIN user_settings s ON u.id = s.user_id
        WHERE s.user_id IS NULL
        ON CONFLICT (user_id) DO NOTHING
    """)

def downgrade():
    # Step 1: Revert foreign keys to remove ON DELETE CASCADE
    # user_settings.user_id
    op.drop_constraint('user_settings_user_id_fkey', 'user_settings', type_='foreignkey')
    op.create_foreign_key(
        'user_settings_user_id_fkey',
        'user_settings',
        'users',
        ['user_id'],
        ['id']
    )

    # user_business.user_id
    op.drop_constraint('user_business_user_id_fkey', 'user_business', type_='foreignkey')
    op.create_foreign_key(
        'user_business_user_id_fkey',
        'user_business',
        'users',
        ['user_id'],
        ['id']
    )

    # user_permissions.user_id
    op.drop_constraint('user_permissions_user_id_fkey', 'user_permissions', type_='foreignkey')
    op.create_foreign_key(
        'user_permissions_user_id_fkey',
        'user_permissions',
        'users',
        ['user_id'],
        ['id']
    )

    # Step 2: Remove user_settings records created during upgrade
    op.execute("""
        DELETE FROM user_settings
        WHERE created_at >= CURRENT_DATE
        AND notification_method = 'both'
        AND NOT EXISTS (
            SELECT 1 FROM users WHERE users.id = user_settings.user_id
        )
    """)

    # Step 3: No action needed for deleted invalid rows, as they were orphaned