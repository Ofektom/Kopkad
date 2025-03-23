from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from config.settings import settings

# PostgreSQL connection settings
DATABASE_URL = settings.POSTGRES_URI
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create tables (run once or via migrations)
def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database initialized with tables")