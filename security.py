import random
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

# Configuration du hashage Argon2 (Exigence 4.1)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Clé secrète de signature JWT (Doit provenir des variables d'environnement en prod)
SECRET_KEY = "SECRET_SUPER_SECRETI_A_REMPLACER_PAR_ENV_VAR"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30  # Session longue durée (Exigence 2 & 4.1)


def hash_pin(pin: str) -> str:
    """Hache un PIN à 4 chiffres avec Argon2 (jamais stocké en clair)."""
    return pwd_context.hash(pin)


def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """Vérifie la correspondance entre le PIN saisi et le hash."""
    return pwd_context.verify(plain_pin, hashed_pin)


def generate_auto_pin() -> str:
    """Génère automatiquement un PIN aléatoire à 4 chiffres (Exigence 2)."""
    return f"{random.randint(0, 9999):04d}"


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Génère un jeton JWT de session longue durée pour maintenir la connexion."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Décode et valide le jeton JWT."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None