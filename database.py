import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Le mot de passe ne doit JAMAIS apparaître ici en clair.
# Il vient uniquement de la variable d'environnement DATABASE_URL (fichier .env en local,
# variable d'environnement configurée sur Render en production).
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL n'est pas définie. Crée un fichier .env avec DATABASE_URL=... "
        "(voir Supabase > Settings > Database > Connection string)."
    )

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