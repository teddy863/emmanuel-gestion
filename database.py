from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Ton lien propre sans caractères spéciaux problématiques
DATABASE_URL = "postgresql://postgres.tbnidnhcgrtqfqtmffxg:Emmanuel2026DbPass@aws-0-eu-west-2.pooler.supabase.com:5432/postgres"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 10}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()