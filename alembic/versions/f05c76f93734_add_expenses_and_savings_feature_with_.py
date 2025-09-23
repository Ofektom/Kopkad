"""Add expenses feature with income_details

Revision ID: f05c76f93734
Revises: 3c50fb742cea
Create Date: 2025-09-21 14:00:12.775562

"""
from alembic import op
from sqlalchemy.sql import text
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alembic.runtime.migration")

# revision identifiers, used by Alembic.
revision = 'f05c76f93734'
down_revision = '3c50fb742cea'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    logger.info("Starting migration f05c76f93734")

    # Drop enums in all schemas
    logger.info("Dropping enums if they exist")
    conn.execute(text("""
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN (SELECT nspname FROM pg_namespace)
            LOOP
                EXECUTE 'SET search_path TO ' || quote_ident(r.nspname);
                EXECUTE 'DROP TYPE IF EXISTS income_type CASCADE';
                EXECUTE 'DROP TYPE IF EXISTS expensecategory CASCADE';
            END LOOP;
            SET search_path TO public;
        END $$;
    """))
    logger.info("Enums dropped successfully")

    # Verify no enums exist
    result = conn.execute(text("SELECT typname FROM pg_type WHERE typname IN ('income_type', 'expensecategory')")).fetchall()
    logger.info(f"Enum check result: {result}")

    # Create enums
    logger.info("Creating income_type enum")
    conn.execute(text("CREATE TYPE income_type AS ENUM ('SALARY', 'SAVINGS', 'BORROWED', 'BUSINESS', 'OTHER')"))
    logger.info("Creating expensecategory enum")
    conn.execute(text("CREATE TYPE expensecategory AS ENUM ('FOOD', 'TRANSPORT', 'ENTERTAINMENT', 'UTILITIES', 'RENT', 'MISC')"))
    logger.info("Enums created successfully")

    # Create expense_cards table
    logger.info("Creating expense_cards table")
    conn.execute(text("""
        CREATE TABLE expense_cards (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            name VARCHAR(100) NOT NULL,
            income_type income_type NOT NULL,
            income_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
            balance NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
            savings_id INTEGER,
            income_details VARCHAR(255),
            created_by INTEGER,
            created_at TIMESTAMP WITH TIME ZONE,
            updated_by INTEGER,
            updated_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT fk_expense_cards_customer_id FOREIGN KEY (customer_id) REFERENCES users(id),
            CONSTRAINT fk_expense_cards_savings_id FOREIGN KEY (savings_id) REFERENCES savings_accounts(id) ON DELETE SET NULL,
            CONSTRAINT fk_expense_cards_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT fk_expense_cards_updated_by FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
        )
    """))
    logger.info("expense_cards table created")

    # Create expenses table
    logger.info("Creating expenses table")
    conn.execute(text("""
        CREATE TABLE expenses (
            id INTEGER PRIMARY KEY,
            expense_card_id INTEGER NOT NULL,
            category expensecategory,
            description VARCHAR(255),
            amount NUMERIC(10, 2) NOT NULL,
            date DATE NOT NULL,
            created_by INTEGER,
            created_at TIMESTAMP WITH TIME ZONE,
            updated_by INTEGER,
            updated_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT fk_expenses_expense_card_id FOREIGN KEY (expense_card_id) REFERENCES expense_cards(id),
            CONSTRAINT fk_expenses_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT fk_expenses_updated_by FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
        )
    """))
    logger.info("expenses table created")

def downgrade():
    conn = op.get_bind()
    logger.info("Starting downgrade for f05c76f93734")

    # Drop tables
    logger.info("Dropping expenses table")
    conn.execute(text("DROP TABLE IF EXISTS expenses"))
    logger.info("Dropping expense_cards table")
    conn.execute(text("DROP TABLE IF EXISTS expense_cards"))

    # Drop enums
    logger.info("Dropping enums")
    conn.execute(text("DROP TYPE IF EXISTS income_type CASCADE"))
    conn.execute(text("DROP TYPE IF EXISTS expensecategory CASCADE"))
    logger.info("Enums dropped in downgrade")