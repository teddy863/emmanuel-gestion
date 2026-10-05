import uuid
import random
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Form, status, Cookie, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from database import engine, Base, get_db
import models
import crud
from security import hash_pin, verify_pin, create_access_token, decode_access_token, generate_auto_pin
from services.email_service import envoyer_code_otp_email

# 1. Initialisation de l'application FastAPI
app = FastAPI(title="Emmanuel - Application de Gestion SaaS")

# 2. Création automatique des tables sur Supabase au démarrage
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Avertissement Connexion Supabase : {e}")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Stockage temporaire des codes OTP d'inscription
DB_OTP_TEMP = {}

ROLES_LABELS = {
    "gerant_toilettes": "Gérant Toilettes",
    "gerant_flats": "Gérant Flats",
    "gerant_comptoir": "Gérant Comptoir",
    "cuisinier": "Cuisinier / Restaurant",
    "gerant_salle": "Gérant Salle de Fêtes",
    "gerant_locataires": "Gérant Locataires"
}

# --- DONNÉES EN MÉMOIRE ISOLÉES AVEC PROPRIÉTAIRE (owner_id) ---
DB_ETABLISSEMENTS = [
    {"id": "site_1", "nom": "Emmanuel - Bandal", "est_actif": True, "owner_id": "admin_1"},
    {"id": "site_2", "nom": "Emmanuel - Tchangu", "est_actif": True, "owner_id": "admin_1"}
]

# Les comptes d'exemple pour le premier compte de démo
DB_GERANTS = [
    {"id": "admin_1", "nom_complet": "Emmanuel K.", "role": "super_admin", "role_label": "Super Admin", "pin": "1234", "salaire": 0.0, "est_actif": True, "etablissement_id": None, "owner_id": "admin_1"},
    {"id": "toilette_1", "nom_complet": "Jeanne M.", "role": "gerant_toilettes", "role_label": "Gérant Toilettes", "pin": "5678", "salaire": 150000.0, "est_actif": True, "etablissement_id": "site_1", "owner_id": "admin_1"},
    {"id": "flat_1", "nom_complet": "Patrick N.", "role": "gerant_flats", "role_label": "Gérant Flats", "pin": "9012", "salaire": 200000.0, "est_actif": True, "etablissement_id": "site_1", "owner_id": "admin_1"},
]

TARIFS_SYSTEME = {
    "toilettes_petit": 500.0,
    "toilettes_grand": 1000.0,
    "flat_heure": 5000.0
}

DB_TOILETTES = []
DB_SEJOURS_FLATS = []
DB_VENTES_COMPTOIR = []
DB_CUISINE_VENTES = []
DB_CUISINE_DEPENSES = []
DB_SALLE_FETES = []
DB_LOCATAIRES = []
DB_DETTES = []
DB_CLOTURES = []

DB_CHAMBRES = [
    {"id": "1", "nom": "Ch. 1", "statut": "libre", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
    {"id": "2", "nom": "Ch. 2", "statut": "libre", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
]

DB_COMPTOIR = []
DB_CUISINE_MENU = []

# --- FONCTION UTILISATEUR SECURISEE ET ISOLEE ---
def get_current_user(session_token: Optional[str], db: Optional[Session] = None):
    if not session_token:
        return None
    
    token_val = session_token
    if isinstance(session_token, dict):
        token_val = session_token.get("access_token") or session_token.get("session_token")
    
    token_str = str(token_val).strip()

    # 1. ACCÈS DÉVELOPPEUR / FONDATEUR (0000)
    if token_str == "0000":
        return {"id": "0000", "nom_complet": "Fondateur SaaS", "role": "super_admin_fondateur", "owner_id": "0000"}

    # 2. Décodage du jeton JWT
    payload = decode_access_token(token_str)
    if payload and "sub" in payload:
        user_id = str(payload.get("sub"))
        role = payload.get("role", "super_admin")

        if user_id == "0000" or role == "super_admin_fondateur":
            return {"id": "0000", "nom_complet": "Fondateur SaaS", "role": "super_admin_fondateur", "owner_id": "0000"}

        # Recherche BDD Supabase
        if db:
            try:
                db_user = db.query(
                    models.Utilisateur.id,
                    models.Utilisateur.nom_complet,
                    models.Utilisateur.role,
                    models.Utilisateur.pin,
                    models.Utilisateur.etablissement_id
                ).filter(
                    (models.Utilisateur.id == user_id) | (models.Utilisateur.pin == user_id),
                    models.Utilisateur.est_actif == True
                ).first()

                if db_user:
                    return {
                        "id": str(db_user.id),
                        "nom_complet": db_user.nom_complet,
                        "role": db_user.role,
                        "owner_id": str(db_user.id),
                        "etablissement_id": db_user.etablissement_id
                    }
            except Exception as e:
                print(f"Avertissement BDD get_current_user: {e}", flush=True)

        # Recherche fallback comptes gérants locaux
        for g in DB_GERANTS:
            if str(g["id"]) == user_id or str(g["pin"]) == user_id:
                return g

        return {"id": user_id, "nom_complet": "Super Admin", "role": role, "owner_id": user_id}

    # 3. Recherche directe par PIN brut si non JWT
    for g in DB_GERANTS:
        if str(g["pin"]) == token_str or str(g["id"]) == token_str:
            return g

    return None

# --- AUTHENTIFICATION & DECONNEXION ---
@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

# INTEGRATION DE LA ROUTE LOGOUT DEMANDÉE
@app.get("/logout")
@app.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session_token")
    return response

@app.post("/login")
def login(
    request: Request,
    pin: Optional[str] = Form(None),
    code_pin: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    valeur_pin = (pin or code_pin or "").strip()
    if not valeur_pin:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Veuillez entrer votre code PIN."},
            status_code=400
        )

    # 1. ACCÈS DÉVELOPPEUR / FONDATEUR (0000) -> Redirige vers la Plateforme SaaS
    if valeur_pin == "0000":
        token = create_access_token({"sub": "0000", "role": "super_admin_fondateur"})
        response = RedirectResponse(url="/admin/plateforme", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="session_token", value=token, httponly=True)
        return response

    # 2. VÉRIFICATION DANS SUPABASE
    if db:
        try:
            db_user = db.query(
                models.Utilisateur.id,
                models.Utilisateur.nom_complet,
                models.Utilisateur.role,
                models.Utilisateur.pin
            ).filter(
                models.Utilisateur.pin == valeur_pin
            ).first()

            if db_user:
                token = create_access_token({"sub": str(db_user.id), "role": db_user.role})
                target_url = "/cuisine" if db_user.role == "cuisinier" else "/dashboard"
                response = RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)
                response.set_cookie(key="session_token", value=token, httponly=True)
                return response
        except Exception as e:
            print(f"Erreur connexion BDD Supabase : {e}", flush=True)

    # 3. VÉRIFICATION COMPTES LOCAUX
    for g in DB_GERANTS:
        if str(g.get("pin")) == valeur_pin and g.get("est_actif", True):
            token = create_access_token({"sub": str(g["id"]), "role": g["role"]})
            target_url = "/cuisine" if g.get("role") == "cuisinier" else "/dashboard"
            response = RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(key="session_token", value=token, httponly=True)
            return response

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Code PIN incorrect ou compte désactivé"},
        status_code=400
    )

# --- ESPACE EXCLUSIF DÉVELOPPEUR / FONDATEUR ---
@app.get("/admin/plateforme", response_class=HTMLResponse)
def page_plateforme_admin(
    request: Request, 
    session_token: Optional[str] = Cookie(None), 
    db: Session = Depends(get_db)
):
    token_str = session_token or request.cookies.get("session_token")
    user = get_current_user(token_str, db)

    if not user or user.get("role") != "super_admin_fondateur":
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    organisations = []
    if db:
        try:
            organisations = db.query(models.Organisation).all()
        except Exception as e:
            print(f"Erreur lecture organisations: {e}", flush=True)

    return templates.TemplateResponse(
        request=request,
        name="admin_plateforme.html",
        context={"user": user, "organisations": organisations}
    )

# --- TABLEAU DE BORD (DONNÉES TOTALEMENT FILTRÉES ET ISOLÉES) ---
@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/admin/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request, 
    session_token: Optional[str] = Cookie(None), 
    db: Session = Depends(get_db)
):
    token_str = session_token or request.cookies.get("session_token")
    user = get_current_user(token_str, db)

    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    owner_id = user.get("owner_id") or user.get("id")

    # Isolation stricte des données de l'utilisateur connecté
    clotures_visibles = [c for c in DB_CLOTURES if c.get("owner_id") == owner_id or c.get("gerant") == user.get("nom_complet")]
    
    recette_toilettes = sum(e.get("montant", 0) for e in DB_TOILETTES if e.get("owner_id") == owner_id)
    recette_flats = sum(s.get("montant", 0) for s in DB_SEJOURS_FLATS if s.get("owner_id") == owner_id)
    recette_comptoir = sum(v.get("montant", 0) for v in DB_VENTES_COMPTOIR if v.get("owner_id") == owner_id)
    recette_cuisine = sum(v.get("montant", 0) for v in DB_CUISINE_VENTES if v.get("owner_id") == owner_id)
    recette_salle = sum(r.get("montant", 0) for r in DB_SALLE_FETES if r.get("owner_id") == owner_id)
    recette_locataires = sum(l.get("montant", 0) for l in DB_LOCATAIRES if l.get("owner_id") == owner_id)

    mes_etablissements = [et for et in DB_ETABLISSEMENTS if et.get("owner_id") == owner_id]

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "recette_jour": recette_toilettes + recette_flats + recette_comptoir + recette_cuisine + recette_salle + recette_locataires,
            "total_toilettes": recette_toilettes,
            "total_flats": recette_flats,
            "total_comptoir": recette_comptoir,
            "total_cuisine": recette_cuisine,
            "total_salle": recette_salle,
            "total_locataires": recette_locataires,
            "etablissements": mes_etablissements,
            "clotures": clotures_visibles,
            "dettes": DB_DETTES,
            "depenses_cuisine": DB_CUISINE_DEPENSES,
            "alertes_stock": DB_COMPTOIR,
            "tarifs": TARIFS_SYSTEME
        }
    )

# --- GESTION DES GÉRANTS (FONDATEUR 0000 TOTALEMENT MASQUÉ ET COMPTES ISOLÉS) ---
@app.get("/gerants", response_class=HTMLResponse)
def gerants_page(
    request: Request, 
    nouveau_pin: Optional[str] = None, 
    session_token: Optional[str] = Cookie(None), 
    db: Session = Depends(get_db)
):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["super_admin", "super_admin_fondateur"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    owner_id = user.get("owner_id") or user.get("id")

    # Exclusions strictes du compte Développeur et des autres entreprises
    mes_gerants = [
        g for g in DB_GERANTS 
        if g.get("role") != "super_admin_fondateur" 
        and g.get("pin") != "0000"
        and (g.get("owner_id") == owner_id or g.get("id") == user["id"])
    ]

    mes_etablissements = [et for et in DB_ETABLISSEMENTS if et.get("owner_id") == owner_id]

    return templates.TemplateResponse(
        request=request, 
        name="gerants.html", 
        context={
            "user": user, 
            "gerants": mes_gerants, 
            "etablissements": mes_etablissements, 
            "roles_labels": ROLES_LABELS, 
            "nouveau_pin": nouveau_pin
        }
    )

@app.post("/gerants/creer")
def creer_gerant(
    nom_complet: str = Form(...), 
    role: str = Form(...), 
    salaire: float = Form(150000.0), 
    etablissement_id: Optional[str] = Form(None), 
    session_token: Optional[str] = Cookie(None), 
    db: Session = Depends(get_db)
):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["super_admin", "super_admin_fondateur"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    owner_id = user.get("owner_id") or user.get("id")
    pin_auto = generate_auto_pin()
    
    DB_GERANTS.append({
        "id": str(uuid.uuid4()),
        "nom_complet": nom_complet,
        "role": role,
        "role_label": ROLES_LABELS.get(role, role),
        "pin": pin_auto,
        "salaire": salaire,
        "est_actif": True,
        "etablissement_id": etablissement_id,
        "owner_id": owner_id
    })
    return RedirectResponse(url=f"/gerants?nouveau_pin={pin_auto}", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULES D'EXPLOITATION ---
@app.get("/flats", response_class=HTMLResponse)
def flats_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_flats", "super_admin", "super_admin_fondateur"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse(
        request=request, 
        name="flats.html", 
        context={
            "user": user, 
            "chambres": DB_CHAMBRES, 
            "tarif_heure": TARIFS_SYSTEME["flat_heure"],
            "total_flats": sum(s["montant"] for s in DB_SEJOURS_FLATS)
        }
    )

@app.get("/comptoir", response_class=HTMLResponse)
def comptoir_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_comptoir", "super_admin", "super_admin_fondateur"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request, 
        name="comptoir.html", 
        context={
            "user": user, 
            "produits": DB_COMPTOIR, 
            "ventes": DB_VENTES_COMPTOIR,
            "total_ventes": sum(v["montant"] for v in DB_VENTES_COMPTOIR),
            "erreur_stock": None
        }
    )

@app.get("/cuisine", response_class=HTMLResponse)
def cuisine_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["cuisinier", "super_admin", "super_admin_fondateur"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request, 
        name="cuisine.html", 
        context={
            "user": user, 
            "menu": DB_CUISINE_MENU,
            "ventes": DB_CUISINE_VENTES,
            "depenses": DB_CUISINE_DEPENSES,
            "total_ventes": sum(v["montant"] for v in DB_CUISINE_VENTES), 
            "total_depenses": sum(d["montant"] for d in DB_CUISINE_DEPENSES),
            "benefice_net": 0.0
        }
    )

@app.get("/toilettes", response_class=HTMLResponse)
def toilettes_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_toilettes", "super_admin", "super_admin_fondateur"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="toilettes.html", context={"user": user, "total_toilettes": sum(e["montant"] for e in DB_TOILETTES), "passages": DB_TOILETTES, "tarif_petit": TARIFS_SYSTEME["toilettes_petit"], "tarif_grand": TARIFS_SYSTEME["toilettes_grand"], "tarif_heure": TARIFS_SYSTEME["flat_heure"]})

@app.get("/cloture", response_class=HTMLResponse)
def cloture_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    owner_id = user.get("owner_id") or user.get("id")
    mes_clotures = [c for c in DB_CLOTURES if c.get("owner_id") == owner_id or c.get("gerant") == user["nom_complet"]]

    return templates.TemplateResponse(request=request, name="cloture.html", context={"user": user, "total_attendu": 0.0, "clotures": mes_clotures, "message": None})

# --- INSCRIPTION SAAS & OTP ---
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")

@app.post("/register")
def register_client(
    request: Request,
    nom_entreprise: str = Form(...),
    nom_proprietaire: str = Form(...),
    email: str = Form(...),
    telephone: str = Form(...),
    pin: str = Form(...),
    db: Session = Depends(get_db)
):
    email_clean = email.strip().lower()
    code_otp = str(random.randint(100000, 999999))
    
    DB_OTP_TEMP[email_clean] = {
        "code": code_otp,
        "expire": datetime.utcnow() + timedelta(minutes=15),
        "nom_entreprise": nom_entreprise.strip(),
        "nom_proprietaire": nom_proprietaire.strip(),
        "telephone": telephone.strip(),
        "pin": pin.strip()
    }
    try:
        envoyer_code_otp_email(email_clean, code_otp, nom_entreprise.strip())
    except Exception as e:
        print(f"Erreur envoi OTP Email: {e}", flush=True)

    return RedirectResponse(url=f"/verify-otp?email={email_clean}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/verify-otp", response_class=HTMLResponse)
def page_verify_otp(request: Request, email: str):
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Vérification Code OTP</title>
        <style>
            body {{ background: #121A21; color: #FFF; font-family: sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
            .card {{ background: #1C2732; padding: 25px; border-radius: 12px; width: 100%; max-width: 380px; text-align: center; border: 1px solid #2A3847; }}
            input {{ width: 100%; padding: 12px; margin: 15px 0; background: #121A21; border: 1px solid #2A3847; color: #FFF; border-radius: 8px; text-align: center; font-size: 1.5em; letter-spacing: 5px; box-sizing: border-box; }}
            button {{ background: #0077B6; color: #FFF; border: 0; padding: 12px; border-radius: 8px; width: 100%; font-weight: bold; cursor: pointer; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Vérification E-mail</h2>
            <p>Entrez le code à 6 chiffres envoyé à<br><strong>{email}</strong></p>
            <form action="/verify-otp" method="POST">
                <input type="hidden" name="email" value="{email}">
                <input type="text" name="code" maxlength="6" required placeholder="000000" autofocus>
                <button type="submit">VALIDER ET ACTIVER MON COMPTE</button>
            </form>
        </div>
    </body>
    </html>
    """)

@app.post("/verify-otp")
def valider_otp(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    email_clean = email.strip().lower()
    template_name = "register.html"

    if email_clean not in DB_OTP_TEMP:
        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={"email": email_clean, "error": "Session expirée ou invalide."}
        )

    data = DB_OTP_TEMP[email_clean]

    if data["code"] != code.strip():
        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={"email": email_clean, "error": "Code OTP incorrect."}
        )

    new_user_id = str(uuid.uuid4())
    pin_client = data["pin"]
    nom_proprio = data["nom_proprietaire"]
    nom_entreprise = data["nom_entreprise"]

    # Création du Super Admin client avec son owner_id unique
    DB_GERANTS.append({
        "id": new_user_id,
        "nom_complet": nom_proprio,
        "role": "super_admin",
        "role_label": "Propriétaire / Admin",
        "pin": pin_client,
        "salaire": 0.0,
        "est_actif": True,
        "etablissement_id": None,
        "owner_id": new_user_id
    })

    del DB_OTP_TEMP[email_clean]
    return RedirectResponse(url="/login?success=compte_cree", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/plateforme/toggle/{org_id}")
def changer_statut_organisation(
    org_id: str, 
    session_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin_fondateur":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    try:
        org = db.query(models.Organisation).filter(models.Organisation.id == org_id).first()
        if org:
            org.est_active = not org.est_active
            db.commit()
    except Exception:
        pass
    return RedirectResponse(url="/admin/plateforme", status_code=status.HTTP_303_SEE_OTHER)