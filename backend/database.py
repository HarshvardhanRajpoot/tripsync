import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Put it in backend/.env (or in your host's environment variables).")

# pool_pre_ping: replaces connections that the hosted database closed while the app was idle
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Used by API endpoints to get a database session, and auto-close it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
