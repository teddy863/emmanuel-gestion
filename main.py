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

ROLES_GERANTS_POSTE = set(ROLES_LABELS.keys())

# Mapping des redirections automatiques par rôle
ROLE_REDIRECT_MAP = {
    "gerant_toilettes": "/toilettes",
    "gerant_flats": "/flats",
    "gerant_comptoir": "/comptoir",
    "cuisinier": "/cuisine",
    "gerant_salle": "/salle",
    "gerant_locataires": "/locataires"
}

# --- DONNÉES EN MÉMOIRE POUR LES SITES EXISTANTS ---
DB_ETABLISSEMENTS = [
    {"id": "site_1", "organisation_id": "org_demo_emmanuel", "nom": "Emmanuel - Bandal", "est_actif": True},
    {"id": "site_2", "organisation_id": "org_demo_emmanuel", "nom": "Emmanuel - Tchangu", "est_actif": True}
]

DB_GERANTS = [
    {"id": "admin_1", "nom_complet": "Emmanuel K.", "role": "super_admin", "role_label": "Super Admin", "pin": "1234", "salaire": 0.0, "est_actif": True, "etablissement_id": None, "organisation_id": "org_demo_emmanuel", "etablissement_nom": "Tous les sites"},
    {"id": "fondateur_1", "nom_complet": "Fondateur SaaS", "role": "super_admin_fondateur", "role_label": "Super Admin Fondateur", "pin": "0000", "salaire": 0.0, "est_actif": True, "etablissement_id": None, "organisation_id": None, "etablissement_nom": "Tous les sites"},
    {"id": "toilette_1", "nom_complet": "Jeanne M.", "role": "gerant_toilettes", "role_label": "Gérant Toilettes", "pin": "5678", "salaire": 150000.0, "est_actif": True, "etablissement_id": "site_1", "organisation_id": "org_demo_emmanuel", "etablissement_nom": "Emmanuel - Bandal"},
    {"id": "flat_1", "nom_complet": "Patrick N.", "role": "gerant_flats", "role_label": "Gérant Flats", "pin": "9012", "salaire": 200000.0, "est_actif": True, "etablissement_id": "site_1", "organisation_id": "org_demo_emmanuel", "etablissement_nom": "Emmanuel - Bandal"},
    {"id": "comptoir_1", "nom_complet": "Bibiche T.", "role": "gerant_comptoir", "role_label": "Gérant Comptoir", "pin": "1111", "salaire": 180000.0, "est_actif": True, "etablissement_id": "site_1", "organisation_id": "org_demo_emmanuel", "etablissement_nom": "Emmanuel - Bandal"},
    {"id": "cuisine_1", "nom_complet": "Sœur Anne", "role": "cuisinier", "role_label": "Cuisinier / Restaurant", "pin": "2222", "salaire": 180000.0, "est_actif": True, "etablissement_id": "site_1", "organisation_id": "org_demo_emmanuel", "etablissement_nom": "Emmanuel - Bandal"},
    {"id": "salle_1", "nom_complet": "Marc L.", "role": "gerant_salle", "role_label": "Gérant Salle de Fêtes", "pin": "3333", "salaire": 180000.0, "est_actif": True, "etablissement_id": "site_1", "organisation_id": "org_demo_emmanuel", "etablissement_nom": "Emmanuel - Bandal"},
    {"id": "locataire_1", "nom_complet": "Clarisse V.", "role": "gerant_locataires", "role_label": "Gérant Locataires", "pin": "4444", "salaire": 180000.0, "est_actif": True, "etablissement_id": "site_1", "organisation_id": "org_demo_emmanuel", "etablissement_nom": "Emmanuel - Bandal"},
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
    {"id": "1", "etablissement_id": "site_1", "nom": "Ch. 1", "statut": "libre", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
    {"id": "2", "etablissement_id": "site_1", "nom": "Ch. 2", "statut": "libre", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
    {"id": "3", "etablissement_id": "site_1", "nom": "Ch. 3", "statut": "libre", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
    {"id": "4", "etablissement_id": "site_1", "nom": "Ch. 4", "statut": "hors_service", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
    {"id": "5", "etablissement_id": "site_1", "nom": "Ch. 5", "statut": "libre", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
    {"id": "6", "etablissement_id": "site_1", "nom": "Ch. 6", "statut": "libre", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
]

DB_COMPTOIR = [
    {"id": "1", "etablissement_id": "site_1", "nom": "Eau 1,5 L", "unites_par_casier": 12, "prix_achat_casier": 18000.0, "prix_vente": 2000.0, "quantite_stock": 24},
    {"id": "2", "etablissement_id": "site_1", "nom": "Mützig 65cl", "unites_par_casier": 12, "prix_achat_casier": 30000.0, "prix_vente": 3500.0, "quantite_stock": 36},
    {"id": "3", "etablissement_id": "site_1", "nom": "Coca 33cl", "unites_par_casier": 24, "prix_achat_casier": 36000.0, "prix_vente": 2000.0, "quantite_stock": 48},
]

DB_CUISINE_MENU = [
    {"id": "1", "etablissement_id": "site_1", "nom": "Cuisse de poulet", "prix": 5000.0, "unite": "morceau"},
    {"id": "2", "etablissement_id": "site_1", "nom": "Poisson grillé", "prix": 10000.0, "unite": "morceau"},
    {"id": "3", "etablissement_id": "site_1", "nom": "Foufou", "prix": 500.0, "unite": "boule"},
    {"id": "4", "etablissement_id": "site_1", "nom": "Makemba", "prix": 1000.0, "unite": "portion"},
    {"id": "5", "etablissement_id": "site_1", "nom": "Pondu", "prix": 1000.0, "unite": "portion"}
]

# ==============================================================================
#                 OUTILS D'ISOLATION MULTI-TENANT & RESTRICTIONS
# ==============================================================================
def etablissements_autorises(user: dict) -> list:
    if not user:
        return []
    role = user.get("role")
    if role == "super_admin_fondateur":
        return []
    if role == "super_admin":
        org_id = user.get("organisation_id")
        if not org_id:
            etab_id = user.get("etablissement_id")
            return [etab_id] if etab_id else []
        return [e["id"] for e in DB_ETABLISSEMENTS if e.get("organisation_id") == org_id]
    etab_id = user.get("etablissement_id")
    return [etab_id] if etab_id else []

def filtrer(liste: list, user: dict) -> list:
    autorises = etablissements_autorises(user)
    return [x for x in liste if x.get("etablissement_id") in autorises]

def dans_perimetre(objet: dict, user: dict) -> bool:
    return objet.get("etablissement_id") in etablissements_autorises(user)

def refuser_si_fondateur(user: dict):
    if user and user.get("role") == "super_admin_fondateur":
        return RedirectResponse(url="/admin/plateforme", status_code=status.HTTP_303_SEE_OTHER)
    return None

# NOUVELLE FONCTION DE RESTRICTION POUR LES GÉRANTS DE POSTE
def rediriger_si_gerant_poste(user: dict):
    """
    Empêche un gérant de poste d'accéder au Dashboard.
    Il est immédiatement réorienté vers son espace dédié.
    """
    if user and user.get("role") in ROLES_GERANTS_POSTE:
        target = ROLE_REDIRECT_MAP.get(user.get("role"), "/login")
        return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    return None

# --- FONCTION UTILISATEUR UNIFIÉE & SÉCURISÉE ---
def get_current_user(session_token: Optional[str], db: Optional[Session] = None):
    if not session_token:
        return None
    token_val = session_token
    if isinstance(session_token, dict):
        token_val = session_token.get("access_token") or session_token.get("session_token")
    token_str = str(token_val).strip()

    if token_str == "0000":
        return {"id": "0000", "nom_complet": "Fondateur SaaS", "role": "super_admin_fondateur", "etablissement_id": None, "organisation_id": None}

    payload = decode_access_token(token_str)
    if payload and "sub" in payload:
        user_id = str(payload.get("sub"))
        role = payload.get("role", "super_admin")
        if user_id == "0000" or role == "super_admin_fondateur":
            return {"id": "0000", "nom_complet": "Fondateur SaaS", "role": "super_admin_fondateur", "etablissement_id": None, "organisation_id": None}

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
                    organisation_id = None
                    if db_user.etablissement_id:
                        try:
                            etab = db.query(models.Etablissement.organisation_id).filter(
                                models.Etablissement.id == db_user.etablissement_id
                            ).first()
                            if etab:
                                organisation_id = etab.organisation_id
                        except Exception as e:
                            print(f"Avertissement BDD lecture organisation_id: {e}", flush=True)

                    return {
                        "id": str(db_user.id),
                        "nom_complet": db_user.nom_complet,
                        "role": db_user.role,
                        "etablissement_id": db_user.etablissement_id,
                        "organisation_id": organisation_id
                    }
            except Exception as e:
                print(f"Avertissement BDD get_current_user: {e}", flush=True)

        for g in DB_GERANTS:
            if str(g["id"]) == user_id or str(g["pin"]) == user_id:
                return g
        return {"id": user_id, "nom_complet": "Super Admin", "role": role, "etablissement_id": None, "organisation_id": None}

    for g in DB_GERANTS:
        if str(g["pin"]) == token_str or str(g["id"]) == token_str:
            return g
    return None

# --- AUTHENTIFICATION & DÉCONNEXION ---
@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

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

    # 1. DÉVELOPPEUR / FONDATEUR (0000)
    if valeur_pin == "0000":
        token = create_access_token({"sub": "0000", "role": "super_admin_fondateur"})
        response = RedirectResponse(url="/admin/plateforme", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="session_token", value=token, httponly=True)
        return response

    # 2. SUPABASE BDD
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
                # Redirection vers le module du poste ou vers le dashboard pour le super_admin
                target_url = ROLE_REDIRECT_MAP.get(db_user.role, "/dashboard")
                response = RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)
                response.set_cookie(key="session_token", value=token, httponly=True)
                return response
        except Exception as e:
            print(f"Erreur connexion BDD Supabase : {e}", flush=True)

    # 3. COMPTES LOCAUX
    for g in DB_GERANTS:
        if str(g.get("pin")) == valeur_pin and g.get("est_actif", True):
            token = create_access_token({"sub": str(g["id"]), "role": g["role"]})
            target_url = ROLE_REDIRECT_MAP.get(g.get("role"), "/dashboard")
            response = RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(key="session_token", value=token, httponly=True)
            return response

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Code PIN incorrect ou compte désactivé"},
        status_code=400
    )

@app.get("/logout")
@app.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session_token")
    return response

# --- ESPACE DÉVELOPPEUR / FONDATEUR SAAS ---
@app.get("/admin/plateforme", response_class=HTMLResponse)
def page_plateforme_admin(
    request: Request,
    session_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    token_str = session_token or request.cookies.get("session_token")
    user = get_current_user(token_str, db)
    if not user and (token_str == "0000" or request.cookies.get("session_token") == "0000"):
        user = {"id": "0000", "nom_complet": "Fondateur SaaS", "role": "super_admin_fondateur", "etablissement_id": None, "organisation_id": None}
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

# --- TABLEAU DE BORD (ACCÈS RÉSERVÉ AU SUPER ADMIN EXCLUSIVEMENT) ---
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

    # Bloque le Fondateur
    redirection_fondateur = refuser_si_fondateur(user)
    if redirection_fondateur:
        return redirection_fondateur

    # BLOQUE TOUS LES GÉRANTS DE POSTE : Redirige directement vers leur propre module
    redirection_gerant = rediriger_si_gerant_poste(user)
    if redirection_gerant:
        return redirection_gerant

    # À ce stade, SEUL LE SUPER_ADMIN CLIENT ACCÈDE AU DASHBOARD
    mes_toilettes = filtrer(DB_TOILETTES, user)
    mes_flats = filtrer(DB_SEJOURS_FLATS, user)
    mes_comptoir = filtrer(DB_VENTES_COMPTOIR, user)
    mes_cuisine = filtrer(DB_CUISINE_VENTES, user)
    mes_salle = filtrer(DB_SALLE_FETES, user)
    mes_locataires = filtrer(DB_LOCATAIRES, user)
    mes_depenses_cuisine = filtrer(DB_CUISINE_DEPENSES, user)
    mes_clotures = filtrer(DB_CLOTURES, user)
    mes_dettes = filtrer(DB_DETTES, user)
    mes_etablissements = [e for e in DB_ETABLISSEMENTS if e["id"] in etablissements_autorises(user)]
    mes_produits = filtrer(DB_COMPTOIR, user)

    recette_toilettes = sum(e.get("montant", 0) for e in mes_toilettes)
    recette_flats = sum(s.get("montant", 0) for s in mes_flats)
    recette_comptoir = sum(v.get("montant", 0) for v in mes_comptoir)
    recette_cuisine = sum(v.get("montant", 0) for v in mes_cuisine)
    recette_salle = sum(r.get("montant", 0) for r in mes_salle)
    recette_locataires = sum(l.get("montant", 0) for l in mes_locataires)
    alertes_stock = [p for p in mes_produits if p.get("quantite_stock", 0) < 5]

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
            "clotures": mes_clotures,
            "dettes": mes_dettes,
            "depenses_cuisine": mes_depenses_cuisine,
            "alertes_stock": alertes_stock,
            "tarifs": TARIFS_SYSTEME
        }
    )

@app.post("/configuration/tarifs")
@app.post("/admin/configuration/tarifs")
def ajuster_tarifs(
    toilettes_petit: float = Form(...),
    toilettes_grand: float = Form(...),
    flat_heure: float = Form(...),
    session_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    TARIFS_SYSTEME["toilettes_petit"] = toilettes_petit
    TARIFS_SYSTEME["toilettes_grand"] = toilettes_grand
    TARIFS_SYSTEME["flat_heure"] = flat_heure
    return RedirectResponse(url="/toilettes", status_code=status.HTTP_303_SEE_OTHER)

# --- ÉTABLISSEMENTS & GÉRANTS ---
@app.get("/etablissements", response_class=HTMLResponse)
def page_etablissements(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mes_etablissements = [e for e in DB_ETABLISSEMENTS if e["id"] in etablissements_autorises(user)]
    return templates.TemplateResponse(request=request, name="etablissements.html", context={"user": user, "etablissements": mes_etablissements})

@app.get("/gerants", response_class=HTMLResponse)
def gerants_page(request: Request, nouveau_pin: Optional[str] = None, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mes_gerants = [
        g for g in DB_GERANTS
        if g.get("role") != "super_admin_fondateur" and g.get("etablissement_id") in etablissements_autorises(user)
    ]
    mes_etablissements = [e for e in DB_ETABLISSEMENTS if e["id"] in etablissements_autorises(user)]
    return templates.TemplateResponse(request=request, name="gerants.html", context={"user": user, "gerants": mes_gerants, "etablissements": mes_etablissements, "roles_labels": ROLES_LABELS, "nouveau_pin": nouveau_pin})

@app.post("/gerants/creer")
def creer_gerant(nom_complet: str = Form(...), role: str = Form(...), salaire: float = Form(150000.0), etablissement_id: Optional[str] = Form(None), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user)
    if etablissement_id not in autorises:
        etablissement_id = autorises[0] if autorises else None
    pin_auto = generate_auto_pin()
    nom_site = next((s["nom"] for s in DB_ETABLISSEMENTS if s["id"] == etablissement_id), "Établissement inconnu")
    DB_GERANTS.append({
        "id": str(uuid.uuid4()),
        "nom_complet": nom_complet,
        "role": role,
        "role_label": ROLES_LABELS.get(role, role),
        "pin": pin_auto,
        "salaire": salaire,
        "est_actif": True,
        "etablissement_id": etablissement_id,
        "organisation_id": user.get("organisation_id"),
        "etablissement_nom": nom_site
    })
    return RedirectResponse(url=f"/gerants?nouveau_pin={pin_auto}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/gerants/supprimer/{gerant_id}")
@app.post("/gerants/supprimer/{gerant_id}")
def supprimer_gerant(gerant_id: str, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user)
    global DB_GERANTS
    DB_GERANTS = [
        g for g in DB_GERANTS
        if not (
            g["id"] == gerant_id
            and g["role"] != "super_admin"
            and g.get("etablissement_id") in autorises
        )
    ]
    return RedirectResponse(url="/gerants", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE FLATS & CHAMBRES ---
@app.get("/flats", response_class=HTMLResponse)
@app.get("/flat", response_class=HTMLResponse)
def flats_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mes_chambres = filtrer(DB_CHAMBRES, user)
    mes_sejours = filtrer(DB_SEJOURS_FLATS, user)
    return templates.TemplateResponse(
        request=request,
        name="flats.html",
        context={
            "user": user,
            "chambres": mes_chambres,
            "tarif_heure": TARIFS_SYSTEME["flat_heure"],
            "total_flats": sum(s["montant"] for s in mes_sejours)
        }
    )

@app.get("/flats/chambre/statut/{chambre_id}/{nouveau_statut}")
def changer_statut_chambre(chambre_id: str, nouveau_statut: str, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    for ch in DB_CHAMBRES:
        if ch["id"] == chambre_id and dans_perimetre(ch, user):
            if nouveau_statut in ["libre", "hors_service"]:
                ch["statut"] = nouveau_statut
                if nouveau_statut == "hors_service":
                    ch["montant_recu"] = 0.0
                    ch["duree"] = 0
            break
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/flats/chambre/creer")
def ajouter_chambre(nom: str = Form(...), prix_par_heure: Optional[float] = Form(None), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user)
    mon_etablissement = autorises[0] if autorises else None
    nouvel_id = str(uuid.uuid4())
    tarif = prix_par_heure if prix_par_heure else TARIFS_SYSTEME["flat_heure"]
    DB_CHAMBRES.append({
        "id": nouvel_id,
        "etablissement_id": mon_etablissement,
        "nom": nom.strip(),
        "statut": "libre",
        "prix_par_heure": tarif,
        "montant_recu": 0.0,
        "duree": 0
    })
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/flats/chambre/modifier")
def modifier_chambre(chambre_id: str = Form(...), nouveau_nom: str = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    for ch in DB_CHAMBRES:
        if ch["id"] == chambre_id and dans_perimetre(ch, user):
            ch["nom"] = nouveau_nom.strip()
            break
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/flats/occuper")
def occuper_chambre(chambre_id: str = Form(...), montant_percu: float = Form(...), duree: int = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    for ch in DB_CHAMBRES:
        if ch["id"] == chambre_id and ch["statut"] == "libre" and dans_perimetre(ch, user):
            ch["statut"] = "occupee"
            ch["montant_recu"] = montant_percu
            ch["duree"] = duree
            DB_SEJOURS_FLATS.insert(0, {
                "etablissement_id": ch["etablissement_id"],
                "chambre": ch["nom"],
                "montant": montant_percu,
                "duree": duree,
                "gerant": user["nom_complet"],
                "heure": datetime.now().strftime("%H:%M:%S")
            })
            break
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/flats/liberer/{chambre_id}")
def liberer_chambre(chambre_id: str, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    for ch in DB_CHAMBRES:
        if ch["id"] == chambre_id and ch["statut"] == "occupee" and dans_perimetre(ch, user):
            ch["statut"] = "libre"
            ch["montant_recu"] = 0.0
            ch["duree"] = 0
            break
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE COMPTOIR ---
@app.get("/comptoir", response_class=HTMLResponse)
def comptoir_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_comptoir", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mes_produits = filtrer(DB_COMPTOIR, user)
    mes_ventes = filtrer(DB_VENTES_COMPTOIR, user)
    return templates.TemplateResponse(
        request=request,
        name="comptoir.html",
        context={
            "user": user,
            "produits": mes_produits,
            "ventes": mes_ventes,
            "total_ventes": sum(v["montant"] for v in mes_ventes),
            "erreur_stock": None
        }
    )

@app.get("/comptoir/vendre_une/{produit_id}")
def vendre_une_bouteille(request: Request, produit_id: str, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_comptoir", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    for p in DB_COMPTOIR:
        if p["id"] == produit_id and dans_perimetre(p, user):
            if p["quantite_stock"] <= 0:
                mes_produits = filtrer(DB_COMPTOIR, user)
                mes_ventes = filtrer(DB_VENTES_COMPTOIR, user)
                return templates.TemplateResponse(
                    request=request,
                    name="comptoir.html",
                    context={
                        "user": user,
                        "produits": mes_produits,
                        "ventes": mes_ventes,
                        "total_ventes": sum(v["montant"] for v in mes_ventes),
                        "erreur_stock": f"Stock épuisé pour '{p['nom']}' ! Veuillez réapprovisionner."
                    }
                )
            p["quantite_stock"] -= 1
            DB_VENTES_COMPTOIR.insert(0, {
                "etablissement_id": p["etablissement_id"],
                "produit": p["nom"],
                "quantite": 1,
                "montant": p["prix_vente"],
                "heure": datetime.now().strftime("%H:%M:%S"),
                "gerant": user["nom_complet"]
            })
            break
    return RedirectResponse(url="/comptoir", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/comptoir/ajouter_stock")
def ajouter_stock_casier(nom: str = Form(...), unites_par_casier: int = Form(...), nombre_casiers: int = Form(...), prix_achat_casier: float = Form(...), prix_vente_bouteille: float = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_comptoir", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    nouvelles_bouteilles = unites_par_casier * nombre_casiers
    trouve = False
    mon_etablissement = user.get("etablissement_id") or (etablissements_autorises(user)[0] if etablissements_autorises(user) else None)
    for p in DB_COMPTOIR:
        if p["nom"].strip().lower() == nom.strip().lower() and dans_perimetre(p, user):
            p["quantite_stock"] += nouvelles_bouteilles
            p["prix_achat_casier"] = prix_achat_casier
            p["prix_vente"] = prix_vente_bouteille
            trouve = True
            break
    if not trouve:
        DB_COMPTOIR.append({
            "id": str(uuid.uuid4()),
            "etablissement_id": mon_etablissement,
            "nom": nom.strip(),
            "unites_par_casier": unites_par_casier,
            "prix_achat_casier": prix_achat_casier,
            "prix_vente": prix_vente_bouteille,
            "quantite_stock": nouvelles_bouteilles
        })
    return RedirectResponse(url="/comptoir", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE CUISINE ---
@app.get("/cuisine", response_class=HTMLResponse)
def cuisine_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mes_menu = filtrer(DB_CUISINE_MENU, user)
    mes_ventes = filtrer(DB_CUISINE_VENTES, user)
    mes_depenses = filtrer(DB_CUISINE_DEPENSES, user)
    total_v = sum(v["montant"] for v in mes_ventes)
    total_d = sum(d["montant"] for d in mes_depenses)
    return templates.TemplateResponse(
        request=request,
        name="cuisine.html",
        context={
            "user": user,
            "menu": mes_menu,
            "ventes": mes_ventes,
            "depenses": mes_depenses,
            "total_ventes": total_v,
            "total_depenses": total_d,
            "benefice_net": total_v - total_d
        }
    )

@app.post("/cuisine/vendre_combinaison")
async def vendre_combinaison(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    form_data = await request.form()
    mon_etablissement = user.get("etablissement_id") or (etablissements_autorises(user)[0] if etablissements_autorises(user) else None)
    details_plat = []
    total_plat = 0.0
    for m in filtrer(DB_CUISINE_MENU, user):
        qty_key = f"qty_{m['id']}"
        if qty_key in form_data and form_data[qty_key]:
            try:
                qty = int(form_data[qty_key])
                if qty > 0:
                    sous_total = qty * m["prix"]
                    total_plat += sous_total
                    details_plat.append(f"{qty} {m['unite']}(s) {m['nom']}")
            except ValueError:
                pass
    if details_plat:
        description_complet = " + ".join(details_plat)
        DB_CUISINE_VENTES.insert(0, {
            "etablissement_id": mon_etablissement,
            "plat": description_complet,
            "montant": total_plat,
            "heure": datetime.now().strftime("%H:%M:%S"),
            "cuisinier": user["nom_complet"]
        })
    return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/cuisine/menu/ajouter")
def ajouter_plat_menu(nom: str = Form(...), prix: float = Form(...), unite: str = Form("morceau"), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mon_etablissement = user.get("etablissement_id") or (etablissements_autorises(user)[0] if etablissements_autorises(user) else None)
    DB_CUISINE_MENU.append({
        "id": str(uuid.uuid4()),
        "etablissement_id": mon_etablissement,
        "nom": nom.strip(),
        "prix": prix,
        "unite": unite.strip()
    })
    return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/cuisine/depense")
def enregistrer_depense_cuisine(description: str = Form(...), montant: float = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mon_etablissement = user.get("etablissement_id") or (etablissements_autorises(user)[0] if etablissements_autorises(user) else None)
    DB_CUISINE_DEPENSES.insert(0, {
        "etablissement_id": mon_etablissement,
        "description": description.strip(),
        "montant": montant,
        "heure": datetime.now().strftime("%H:%M:%S"),
        "cuisinier": user["nom_complet"]
    })
    return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE SALLE DE FÊTES & LOCATAIRES ---
@app.get("/salle", response_class=HTMLResponse)
def salle_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_salle", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mes_reservations = filtrer(DB_SALLE_FETES, user)
    return templates.TemplateResponse(request=request, name="salle.html", context={"user": user, "reservations": mes_reservations, "total_salle": sum(r["montant"] for r in mes_reservations)})

@app.get("/locataires", response_class=HTMLResponse)
def locataires_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_locataires", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mes_locataires = filtrer(DB_LOCATAIRES, user)
    return templates.TemplateResponse(request=request, name="locataires.html", context={"user": user, "locataires": mes_locataires, "total_locataires": sum(l["montant"] for l in mes_locataires)})

# --- MODULE TOILETTES ---
@app.get("/toilettes", response_class=HTMLResponse)
def toilettes_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_toilettes", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mes_passages = filtrer(DB_TOILETTES, user)
    return templates.TemplateResponse(request=request, name="toilettes.html", context={"user": user, "total_toilettes": sum(e["montant"] for e in mes_passages), "passages": mes_passages, "tarif_petit": TARIFS_SYSTEME["toilettes_petit"], "tarif_grand": TARIFS_SYSTEME["toilettes_grand"], "tarif_heure": TARIFS_SYSTEME["flat_heure"]})

@app.post("/toilettes/encaisser")
def encaisser_toilette(montant: float = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_toilettes", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mon_etablissement = user.get("etablissement_id") or (etablissements_autorises(user)[0] if etablissements_autorises(user) else None)
    type_besoin = "Petit besoin" if montant == TARIFS_SYSTEME["toilettes_petit"] else "Grand besoin"
    DB_TOILETTES.insert(0, {
        "id": str(uuid.uuid4()),
        "etablissement_id": mon_etablissement,
        "montant": montant,
        "type_besoin": type_besoin,
        "gerant": user["nom_complet"],
        "heure": datetime.now().strftime("%H:%M:%S")
    })
    return RedirectResponse(url="/toilettes", status_code=status.HTTP_303_SEE_OTHER)

# --- CLÔTURE ISOLÉE PAR GÉRANT ET PAR ÉTABLISSEMENT ---
@app.get("/cloture", response_class=HTMLResponse)
def cloture_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redirection = refuser_si_fondateur(user)
    if redirection:
        return redirection

    if user["role"] == "gerant_toilettes":
        total_attendu = sum(e["montant"] for e in filtrer(DB_TOILETTES, user))
    elif user["role"] == "gerant_flats":
        total_attendu = sum(s["montant"] for s in filtrer(DB_SEJOURS_FLATS, user))
    elif user["role"] == "gerant_comptoir":
        total_attendu = sum(v["montant"] for v in filtrer(DB_VENTES_COMPTOIR, user))
    elif user["role"] == "cuisinier":
        total_attendu = sum(v["montant"] for v in filtrer(DB_CUISINE_VENTES, user))
    elif user["role"] == "gerant_salle":
        total_attendu = sum(r["montant"] for r in filtrer(DB_SALLE_FETES, user))
    elif user["role"] == "gerant_locataires":
        total_attendu = sum(l["montant"] for l in filtrer(DB_LOCATAIRES, user))
    else:
        total_attendu = (
            sum(e["montant"] for e in filtrer(DB_TOILETTES, user))
            + sum(s["montant"] for s in filtrer(DB_SEJOURS_FLATS, user))
            + sum(v["montant"] for v in filtrer(DB_VENTES_COMPTOIR, user))
            + sum(v["montant"] for v in filtrer(DB_CUISINE_VENTES, user))
            + sum(r["montant"] for r in filtrer(DB_SALLE_FETES, user))
            + sum(l["montant"] for l in filtrer(DB_LOCATAIRES, user))
        )
    if user["role"] == "super_admin":
        mes_clotures = filtrer(DB_CLOTURES, user)
    else:
        mes_clotures = [c for c in filtrer(DB_CLOTURES, user) if c["gerant"] == user["nom_complet"]]
    return templates.TemplateResponse(request=request, name="cloture.html", context={"user": user, "total_attendu": total_attendu, "clotures": mes_clotures, "message": None})

@app.post("/cloture/valider", response_class=HTMLResponse)
def valider_cloture(request: Request, montant_compte: float = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redirection = refuser_si_fondateur(user)
    if redirection:
        return redirection

    mon_etablissement = user.get("etablissement_id") or (etablissements_autorises(user)[0] if etablissements_autorises(user) else None)
    autorises = etablissements_autorises(user)
    global DB_TOILETTES, DB_SEJOURS_FLATS, DB_VENTES_COMPTOIR, DB_CUISINE_VENTES, DB_CUISINE_DEPENSES, DB_SALLE_FETES, DB_LOCATAIRES

    def retirer_de(liste):
        a_garder = [x for x in liste if x.get("etablissement_id") not in autorises]
        a_cloturer = [x for x in liste if x.get("etablissement_id") in autorises]
        liste.clear()
        liste.extend(a_garder)
        return a_cloturer

    if user["role"] == "gerant_toilettes":
        clotures_items = retirer_de(DB_TOILETTES)
        total_attendu = sum(e["montant"] for e in clotures_items)
        detail_txt = f"Toilettes: {total_attendu:,.0f} FC"
    elif user["role"] == "gerant_flats":
        clotures_items = retirer_de(DB_SEJOURS_FLATS)
        total_attendu = sum(s["montant"] for s in clotures_items)
        detail_txt = f"Flats: {total_attendu:,.0f} FC"
        for ch in DB_CHAMBRES:
            if ch["statut"] == "occupee" and dans_perimetre(ch, user):
                ch["statut"] = "libre"
                ch["montant_recu"] = 0.0
                ch["duree"] = 0
    elif user["role"] == "gerant_comptoir":
        clotures_items = retirer_de(DB_VENTES_COMPTOIR)
        total_attendu = sum(v["montant"] for v in clotures_items)
        detail_txt = f"Comptoir: {total_attendu:,.0f} FC"
    elif user["role"] == "cuisinier":
        clotures_items = retirer_de(DB_CUISINE_VENTES)
        retirer_de(DB_CUISINE_DEPENSES)
        total_attendu = sum(v["montant"] for v in clotures_items)
        detail_txt = f"Cuisine: {total_attendu:,.0f} FC"
    elif user["role"] == "gerant_salle":
        clotures_items = retirer_de(DB_SALLE_FETES)
        total_attendu = sum(r["montant"] for r in clotures_items)
        detail_txt = f"Salle de Fêtes: {total_attendu:,.0f} FC"
    elif user["role"] == "gerant_locataires":
        clotures_items = retirer_de(DB_LOCATAIRES)
        total_attendu = sum(l["montant"] for l in clotures_items)
        detail_txt = f"Locataires: {total_attendu:,.0f} FC"
    else:
        t_toil_items = retirer_de(DB_TOILETTES)
        t_flat_items = retirer_de(DB_SEJOURS_FLATS)
        t_comp_items = retirer_de(DB_VENTES_COMPTOIR)
        t_cuis_items = retirer_de(DB_CUISINE_VENTES)
        retirer_de(DB_CUISINE_DEPENSES)
        t_sall_items = retirer_de(DB_SALLE_FETES)
        t_loca_items = retirer_de(DB_LOCATAIRES)
        for ch in DB_CHAMBRES:
            if ch["statut"] == "occupee" and dans_perimetre(ch, user):
                ch["statut"] = "libre"
                ch["montant_recu"] = 0.0
                ch["duree"] = 0
        t_toil = sum(e["montant"] for e in t_toil_items)
        t_flat = sum(s["montant"] for s in t_flat_items)
        t_comp = sum(v["montant"] for v in t_comp_items)
        t_cuis = sum(v["montant"] for v in t_cuis_items)
        t_sall = sum(r["montant"] for r in t_sall_items)
        t_loca = sum(l["montant"] for l in t_loca_items)
        total_attendu = t_toil + t_flat + t_comp + t_cuis + t_sall + t_loca
        detail_txt = f"Toilettes: {t_toil:,.0f} FC | Flats: {t_flat:,.0f} FC | Comptoir: {t_comp:,.0f} FC | Cuisine: {t_cuis:,.0f} FC | Salle: {t_sall:,.0f} FC | Locataires: {t_loca:,.0f} FC"

    ecart = montant_compte - total_attendu
    maintenant = datetime.now()
    DB_CLOTURES.insert(0, {
        "id": str(uuid.uuid4()),
        "etablissement_id": mon_etablissement,
        "date": maintenant.strftime("%d/%m/%Y"),
        "heure": maintenant.strftime("%H:%M:%S"),
        "gerant": user["nom_complet"],
        "role_label": ROLES_LABELS.get(user["role"], user["role"]),
        "montant_attendu": total_attendu,
        "montant_compte": montant_compte,
        "ecart": ecart,
        "detail": detail_txt
    })
    if user["role"] == "super_admin":
        mes_clotures = filtrer(DB_CLOTURES, user)
    else:
        mes_clotures = [c for c in filtrer(DB_CLOTURES, user) if c["gerant"] == user["nom_complet"]]
    return templates.TemplateResponse(
        request=request,
        name="cloture.html",
        context={"user": user, "total_attendu": 0.0, "clotures": mes_clotures, "message": f"Service clôturé avec succès ! Recette ({montant_compte:,.0f} FC) envoyée aux archives de la direction."}
    )

# ==============================================================================
#                 ROUTES INSCRIPTION SAAS, OTP & ESPACE FONDATEUR
# ==============================================================================
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
            context={"email": email_clean, "error": "Session expirée ou invalide. Veuillez réessayer."}
        )
    data = DB_OTP_TEMP[email_clean]
    if datetime.utcnow() > data["expire"]:
        del DB_OTP_TEMP[email_clean]
        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={"email": email_clean, "error": "Le code OTP a expiré."}
        )
    if data["code"] != code.strip():
        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={"email": email_clean, "error": "Code OTP incorrect."}
        )

    new_user_id = str(uuid.uuid4())
    new_org_id = str(uuid.uuid4())
    new_etab_id = str(uuid.uuid4())
    pin_client = data["pin"]
    nom_proprio = data["nom_proprietaire"]
    nom_entreprise = data["nom_entreprise"]

    if db:
        try:
            nouvelle_org = models.Organisation(
                id=new_org_id,
                nom_entreprise=nom_entreprise,
                nom_proprietaire=nom_proprio,
                email=email_clean,
                telephone=data["telephone"],
                est_active=True,
                est_en_essai=True
            )
            db.add(nouvelle_org)
            db.commit()

            etab_args = {"id": new_etab_id, "organisation_id": new_org_id, "est_actif": True}
            if hasattr(models.Etablissement, 'nom'):
                etab_args['nom'] = nom_entreprise
            nouvel_etablissement = models.Etablissement(**etab_args)
            db.add(nouvel_etablissement)
            db.commit()

            from sqlalchemy import text
            sql_insert = text("""
                INSERT INTO utilisateurs (id, nom_complet, role, role_label, pin, est_actif, etablissement_id)
                VALUES (:id, :nom_complet, :role, :role_label, :pin, :est_actif, :etablissement_id)
            """)
            db.execute(sql_insert, {
                "id": new_user_id,
                "nom_complet": nom_proprio,
                "role": "super_admin",
                "role_label": "Propriétaire / Admin",
                "pin": pin_client,
                "est_actif": True,
                "etablissement_id": new_etab_id
            })
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"=== AVERTISSEMENT BDD (Fallback memoire active) : {e} ===", flush=True)

    DB_ETABLISSEMENTS.append({
        "id": new_etab_id,
        "organisation_id": new_org_id,
        "nom": nom_entreprise,
        "est_actif": True
    })
    DB_GERANTS.append({
        "id": new_user_id,
        "nom_complet": nom_proprio,
        "role": "super_admin",
        "role_label": "Propriétaire / Admin",
        "pin": pin_client,
        "salaire": 0.0,
        "est_actif": True,
        "etablissement_id": new_etab_id,
        "organisation_id": new_org_id,
        "etablissement_nom": nom_entreprise
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