import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text
from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from config.settings import settings
from database.postgres_optimized import Base
from models.user import User
from models.user_business import user_business
from models.business import Business, Unit, PendingBusinessRequest
from models.savings import SavingsAccount, SavingsMarking
from models.expenses import ExpenseCard, Expense
from models.payments import Commission, PaymentAccount, AccountDetails, PaymentRequest
from models.settings import Settings

config.set_main_option("sqlalchemy.url", settings.POSTGRES_URI)
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    print(f"Connecting to database: {config.get_main_option('sqlalchemy.url')}")
    with connectable.connect() as connection:
        connection.execute(text("SET search_path TO public"))
        result = connection.execute(text("SHOW search_path")).fetchone()
        print(f"Database search_path: {result}")
        result = connection.execute(
            text("SELECT typname FROM pg_type WHERE typname IN ('expensecategory', 'income_type', 'markingstatus', 'notificationmethod', 'paymentmethod', 'paymentrequeststatus', 'permission', 'role', 'savingsstatus', 'savingstype')")
        ).fetchall()
        print(f"Enums exist: {[row[0] for row in result]}")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()