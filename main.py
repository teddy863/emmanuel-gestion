import uuid
import random
import io
import csv
from datetime import datetime, timedelta
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv()  # Charge le fichier .env (DATABASE_URL, etc.) avant toute autre importation

from fastapi import FastAPI, Request, Form, status, Cookie, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from database import engine, Base, get_db
import models
import crud
from security import hash_pin, verify_pin, create_access_token, decode_access_token, generate_auto_pin
from services.email_service import envoyer_code_otp_email

app = FastAPI(title="Emmanuel - Application de Gestion SaaS")

try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Avertissement Connexion Supabase : {e}")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

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

ROLE_REDIRECT_MAP = {
    "gerant_toilettes": "/toilettes",
    "gerant_flats": "/flats",
    "gerant_comptoir": "/comptoir",
    "cuisinier": "/cuisine",
    "gerant_salle": "/salle",
    "gerant_locataires": "/locataires"
}

TARIFS_SYSTEME = {
    "toilettes_petit": 500.0,
    "toilettes_grand": 1000.0,
    "flat_heure": 5000.0
}

DB_SALLE_FETES = []
DB_LOCATAIRES = []

MODULE_PAR_ROLE = {
    "gerant_toilettes": "toilettes", "gerant_flats": "flats", "gerant_comptoir": "comptoir",
    "cuisinier": "cuisine", "gerant_salle": "salle", "gerant_locataires": "locataires"
}

# ==============================================================================
#                 OUTILS D'ISOLATION MULTI-TENANT & RESTRICTIONS
# ==============================================================================

def etablissements_autorises(user: dict, db: Optional[Session] = None) -> list:
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
        if db:
            return crud.get_etablissement_ids_by_organisation(db, org_id)
        return []
    etab_id = user.get("etablissement_id")
    return [etab_id] if etab_id else []

def refuser_si_fondateur(user: dict):
    if user and user.get("role") == "super_admin_fondateur":
        return RedirectResponse(url="/admin/plateforme", status_code=status.HTTP_303_SEE_OTHER)
    return None

def rediriger_si_gerant_poste(user: dict):
    if user and user.get("role") in ROLES_GERANTS_POSTE:
        target = ROLE_REDIRECT_MAP.get(user.get("role"), "/login")
        return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    return None

def verifier_service_actif(user: dict, db: Optional[Session], module: str):
    if user.get("role") == "super_admin_fondateur":
        return None
    if db:
        try:
            services = crud.get_services_actifs(db, user.get("organisation_id"))
            if module not in services:
                return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        except Exception as e:
            print(f"Avertissement lecture services_actifs (Repli securite) : {e}", flush=True)
            db.rollback()
            return None
    return None

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
                        except Exception as e_etab:
                            db.rollback()
                            print(f"Avertissement BDD lecture organisation_id: {e_etab}", flush=True)

                    return {
                        "id": str(db_user.id),
                        "nom_complet": db_user.nom_complet,
                        "role": db_user.role,
                        "etablissement_id": db_user.etablissement_id,
                        "organisation_id": organisation_id
                    }
            except Exception as e:
                db.rollback()
                print(f"Avertissement BDD get_current_user: {e}", flush=True)

        return None

    return None

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

    if valeur_pin == "0000":
        token = create_access_token({"sub": "0000", "role": "super_admin_fondateur"})
        response = RedirectResponse(url="/admin/plateforme", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="session_token", value=token, httponly=True)
        return response

    if db:
        try:
            db_user = crud.get_utilisateur_par_pin(db, valeur_pin)
            if db_user:
                token = create_access_token({"sub": str(db_user.id), "role": db_user.role})
                target_url = ROLE_REDIRECT_MAP.get(db_user.role, "/dashboard")
                response = RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)
                response.set_cookie(key="session_token", value=token, httponly=True)
                return response
        except Exception as e:
            db.rollback()
            print(f"Erreur connexion BDD Supabase : {e}", flush=True)

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
            db.rollback()
            print(f"Erreur lecture organisations: {e}", flush=True)

    return templates.TemplateResponse(
        request=request,
        name="admin_plateforme.html",
        context={"user": user, "organisations": organisations}
    )

@app.get("/admin/export-excel")
def exporter_rapport_excel(
    session_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Accès réservé au Super Admin")

    autorises = etablissements_autorises(user, db)

    ventes = crud.get_ventes_non_cloturees(db, autorises)
    clotures = crud.get_clotures_by_etablissement(db, autorises)
    dettes = crud.get_dettes(db, autorises)
    depenses = crud.get_depenses_non_cloturees(db, autorises)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    writer.writerow(["--- RAPPORT FINANCIER ET COMPTABLE ---"])
    writer.writerow([])
    writer.writerow(["--- VENTES EN CAISSE (non clôturées) ---"])
    writer.writerow(["Date", "Module", "Description", "Montant (FC)", "Gérant"])
    for v in ventes:
        writer.writerow([v.date_vente.strftime("%d/%m/%Y %H:%M"), v.module, v.description, v.montant, v.gerant_nom])

    writer.writerow([])
    writer.writerow(["--- DÉPENSES (non clôturées) ---"])
    writer.writerow(["Date", "Module", "Description", "Montant (FC)", "Gérant"])
    for d in depenses:
        writer.writerow([d.date_depense.strftime("%d/%m/%Y %H:%M"), d.module or "-", d.description, d.montant, d.gerant_nom])

    writer.writerow([])
    writer.writerow(["--- HISTORIQUE DES CLÔTURES ---"])
    writer.writerow(["Date", "Heure", "Gérant", "Rôle", "Attendu (FC)", "Compté (FC)", "Écart (FC)"])
    for c in clotures:
        writer.writerow([c.date_cloture.strftime("%d/%m/%Y"), c.heure_cloture, c.gerant_nom, c.role_label, c.montant_attendu, c.montant_compte, c.ecart])

    writer.writerow([])
    writer.writerow(["--- DETTES ET CRÉDITS CLIENTS ---"])
    writer.writerow(["Client", "Téléphone", "Montant (FC)", "Motif", "Statut"])
    for d in dettes:
        statut = "PAYÉE" if d.est_payee else "EN ATTENTE"
        writer.writerow([d.client_nom, d.client_telephone or "-", d.montant, d.motif or "-", statut])

    output.seek(0)
    headers = {'Content-Disposition': 'attachment; filename="Rapport_Comptable.csv"'}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)

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

    redirection_fondateur = refuser_si_fondateur(user)
    if redirection_fondateur:
        return redirection_fondateur

    redirection_gerant = rediriger_si_gerant_poste(user)
    if redirection_gerant:
        return redirection_gerant

    autorises = etablissements_autorises(user, db)

    ventes_toilettes = crud.get_ventes_non_cloturees(db, autorises, "toilettes")
    ventes_flats = crud.get_ventes_non_cloturees(db, autorises, "flats")
    ventes_comptoir = crud.get_ventes_non_cloturees(db, autorises, "comptoir")
    ventes_cuisine = crud.get_ventes_non_cloturees(db, autorises, "cuisine")
    ventes_salle = [v for v in DB_SALLE_FETES if v.get("etablissement_id") in autorises]
    ventes_locataires = [v for v in DB_LOCATAIRES if v.get("etablissement_id") in autorises]
    depenses = crud.get_depenses_non_cloturees(db, autorises)
    dettes = crud.get_dettes(db, autorises)
    clotures = crud.get_clotures_by_etablissement(db, autorises)
    produits = []
    for etab_id in autorises:
        produits.extend(crud.get_produits_by_etablissement(db, etab_id))

    services = crud.get_services_actifs(db, user.get("organisation_id"))

    recette_toilettes = sum(v.montant for v in ventes_toilettes)
    recette_flats = sum(v.montant for v in ventes_flats)
    recette_comptoir = sum(v.montant for v in ventes_comptoir)
    recette_cuisine = sum(v.montant for v in ventes_cuisine)
    recette_salle = sum(r.get("montant", 0) for r in ventes_salle)
    recette_locataires = sum(l.get("montant", 0) for l in ventes_locataires)

    alertes_stock = [p for p in produits if p.quantite_stock < 5]
    mes_etablissements = crud.get_etablissements_by_organisation(db, user.get("organisation_id")) if user.get("organisation_id") else []

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
            "clotures": clotures,
            "dettes": dettes,
            "depenses_cuisine": [d for d in depenses if d.module == "cuisine"],
            "total_depenses_global": sum(d.montant for d in depenses),
            "alertes_stock": alertes_stock,
            "services": services,
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

@app.get("/etablissements", response_class=HTMLResponse)
def page_etablissements(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    mes_etablissements = crud.get_etablissements_by_organisation(db, user.get("organisation_id")) if user.get("organisation_id") else []
    return templates.TemplateResponse(request=request, name="etablissements.html", context={"user": user, "etablissements": mes_etablissements})

@app.get("/gerants", response_class=HTMLResponse)
def gerants_page(request: Request, nouveau_pin: Optional[str] = None, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    mes_gerants = crud.get_gerants_by_etablissements(db, autorises)
    mes_etablissements = crud.get_etablissements_by_organisation(db, user.get("organisation_id")) if user.get("organisation_id") else []
    return templates.TemplateResponse(request=request, name="gerants.html", context={"user": user, "gerants": mes_gerants, "etablissements": mes_etablissements, "roles_labels": ROLES_LABELS, "nouveau_pin": nouveau_pin})

@app.post("/gerants/creer")
def creer_gerant(nom_complet: str = Form(...), role: str = Form(...), salaire: float = Form(150000.0), etablissement_id: Optional[str] = Form(None), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    if etablissement_id not in autorises:
        etablissement_id = autorises[0] if autorises else None
    if not etablissement_id:
        return RedirectResponse(url="/gerants", status_code=status.HTTP_303_SEE_OTHER)
    nouveau = crud.creer_gerant(db, nom_complet, role, ROLES_LABELS.get(role, role), salaire, etablissement_id)
    return RedirectResponse(url=f"/gerants?nouveau_pin={nouveau.pin}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/gerants/supprimer/{gerant_id}")
@app.post("/gerants/supprimer/{gerant_id}")
def supprimer_gerant(gerant_id: str, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    crud.desactiver_gerant(db, gerant_id, autorises)
    return RedirectResponse(url="/gerants", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/flats", response_class=HTMLResponse)
@app.get("/flat", response_class=HTMLResponse)
def flats_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redir = verifier_service_actif(user, db, "flats")
    if redir:
        return redir
    autorises = etablissements_autorises(user, db)
    mes_chambres = []
    for etab_id in autorises:
        mes_chambres.extend(crud.get_chambres_by_etablissement(db, etab_id))
    mes_sejours = crud.get_ventes_non_cloturees(db, autorises, "flats")
    return templates.TemplateResponse(
        request=request,
        name="flats.html",
        context={
            "user": user,
            "chambres": mes_chambres,
            "tarif_heure": TARIFS_SYSTEME["flat_heure"],
            "total_flats": sum(v.montant for v in mes_sejours)
        }
    )

@app.get("/flats/chambre/statut/{chambre_id}/{nouveau_statut}")
def changer_statut_chambre(chambre_id: str, nouveau_statut: str, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    chambre = crud.get_chambre_by_id(db, chambre_id, autorises)
    if chambre and nouveau_statut in ["libre", "hors_service"]:
        crud.changer_statut_chambre(db, chambre, nouveau_statut)
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/flats/chambre/creer")
def ajouter_chambre(nom: str = Form(...), prix_par_heure: Optional[float] = Form(None), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    mon_etablissement = autorises[0] if autorises else None
    if not mon_etablissement:
        return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)
    tarif = prix_par_heure if prix_par_heure else TARIFS_SYSTEME["flat_heure"]
    crud.creer_chambre(db, mon_etablissement, nom.strip(), tarif)
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/flats/chambre/modifier")
def modifier_chambre(chambre_id: str = Form(...), nouveau_nom: str = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    chambre = crud.get_chambre_by_id(db, chambre_id, autorises)
    if chambre:
        crud.renommer_chambre(db, chambre, nouveau_nom.strip())
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/flats/occuper")
def occuper_chambre(chambre_id: str = Form(...), montant_percu: float = Form(...), duree: int = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    chambre = crud.get_chambre_by_id(db, chambre_id, autorises)
    if chambre and chambre.statut == "libre":
        crud.occuper_chambre(db, chambre, montant_percu, duree)
        crud.enregistrer_vente(db, chambre.etablissement_id, "flats", f"Chambre {chambre.nom}", montant_percu, user["nom_complet"])
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/flats/liberer/{chambre_id}")
def liberer_chambre(chambre_id: str, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    chambre = crud.get_chambre_by_id(db, chambre_id, autorises)
    if chambre and chambre.statut == "occupee":
        crud.liberer_chambre(db, chambre)
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/comptoir", response_class=HTMLResponse)
def comptoir_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_comptoir", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redir = verifier_service_actif(user, db, "comptoir")
    if redir:
        return redir
    autorises = etablissements_autorises(user, db)
    mes_produits = []
    for etab_id in autorises:
        mes_produits.extend(crud.get_produits_by_etablissement(db, etab_id))
    mes_ventes = crud.get_ventes_non_cloturees(db, autorises, "comptoir")
    return templates.TemplateResponse(
        request=request,
        name="comptoir.html",
        context={
            "user": user,
            "produits": mes_produits,
            "ventes": mes_ventes,
            "total_ventes": sum(v.montant for v in mes_ventes),
            "erreur_stock": None
        }
    )

@app.get("/comptoir/vendre_une/{produit_id}")
def vendre_une_bouteille(request: Request, produit_id: str, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_comptoir", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    produit = crud.get_produit_by_id(db, produit_id, autorises)
    if produit:
        if produit.quantite_stock <= 0:
            mes_produits = []
            for etab_id in autorises:
                mes_produits.extend(crud.get_produits_by_etablissement(db, etab_id))
            mes_ventes = crud.get_ventes_non_cloturees(db, autorises, "comptoir")
            return templates.TemplateResponse(
                request=request,
                name="comptoir.html",
                context={
                    "user": user,
                    "produits": mes_produits,
                    "ventes": mes_ventes,
                    "total_ventes": sum(v.montant for v in mes_ventes),
                    "erreur_stock": f"Stock épuisé pour '{produit.nom}' ! Veuillez réapprovisionner."
                }
            )
        crud.decrementer_stock(db, produit, 1)
        crud.enregistrer_vente(db, produit.etablissement_id, "comptoir", produit.nom, produit.prix_vente_bouteille, user["nom_complet"])
    return RedirectResponse(url="/comptoir", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/comptoir/ajouter_stock")
def ajouter_stock_casier(nom: str = Form(...), unites_par_casier: int = Form(...), nombre_casiers: int = Form(...), prix_achat_casier: float = Form(...), prix_vente_bouteille: float = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_comptoir", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    mon_etablissement = user.get("etablissement_id") or (autorises[0] if autorises else None)
    if mon_etablissement:
        crud.ajouter_ou_creer_stock(db, mon_etablissement, nom, unites_par_casier, nombre_casiers, prix_achat_casier, prix_vente_bouteille)
    return RedirectResponse(url="/comptoir", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/cuisine", response_class=HTMLResponse)
def cuisine_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redir = verifier_service_actif(user, db, "cuisine")
    if redir:
        return redir
    autorises = etablissements_autorises(user, db)
    mes_menu = []
    for etab_id in autorises:
        mes_menu.extend(crud.get_menu_by_etablissement(db, etab_id))
    mes_ventes = crud.get_ventes_non_cloturees(db, autorises, "cuisine")
    mes_depenses = crud.get_depenses_non_cloturees(db, autorises, "cuisine")
    commandes_tables = crud.get_commandes_ouvertes(db, autorises)
    total_v = sum(v.montant for v in mes_ventes)
    total_d = sum(d.montant for d in mes_depenses)
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
            "benefice_net": total_v - total_d,
            "commandes_tables": commandes_tables
        }
    )

@app.post("/cuisine/vendre_combinaison")
async def vendre_combinaison(
    request: Request,
    numero_table: Optional[str] = Form(None),
    session_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    mon_etablissement = user.get("etablissement_id") or (autorises[0] if autorises else None)
    form_data = await request.form()

    mes_menu = []
    for etab_id in autorises:
        mes_menu.extend(crud.get_menu_by_etablissement(db, etab_id))

    details_plat = []
    total_plat = 0.0
    for m in mes_menu:
        qty_key = f"qty_{m.id}"
        if qty_key in form_data and form_data[qty_key]:
            try:
                qty = int(form_data[qty_key])
                if qty > 0:
                    total_plat += qty * m.prix
                    details_plat.append(f"{qty} {m.unite}(s) {m.nom}")
            except ValueError:
                pass

    if details_plat and mon_etablissement:
        description_complete = " + ".join(details_plat)
        if numero_table and numero_table.strip():
            crud.ajouter_articles_a_table(db, mon_etablissement, numero_table.strip(), description_complete, total_plat, user["nom_complet"])
        else:
            crud.enregistrer_vente(db, mon_etablissement, "cuisine", description_complete, total_plat, user["nom_complet"])

    return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/cuisine/table/regler/{commande_id}")
def regler_addition_table(commande_id: str, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    crud.regler_commande_table(db, commande_id, autorises, user["nom_complet"])
    return RedirectResponse(url=f"/cuisine/table/facture/{commande_id}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/cuisine/table/facture/{commande_id}", response_class=HTMLResponse)
def facture_table(commande_id: str, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    commande = db.query(models.CommandeTable).filter(
        models.CommandeTable.id == commande_id,
        models.CommandeTable.etablissement_id.in_(autorises)
    ).first()
    if not commande:
        return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

    import os
    numero_mobile_money = os.getenv("MOBILE_MONEY_NUMERO", "")
    qr_data = f"Paiement;{numero_mobile_money};{commande.total_montant:.0f} FC"

    qr_base64 = None
    try:
        import qrcode
        import base64
        buf = io.BytesIO()
        qrcode.make(qr_data).save(buf, format="PNG")
        qr_base64 = base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        pass

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Facture Table {commande.numero_table}</title>
        <style>
            body {{ background:#121A21; color:#FFF; font-family: sans-serif; padding:20px; }}
            .facture {{ background:#1C2732; border-radius:12px; padding:20px; max-width:380px; margin:0 auto; border:1px solid #2A3847; }}
            .ligne {{ padding:6px 0; border-bottom:1px solid #2A3847; font-size:14px; }}
            .total {{ font-size:20px; font-weight:900; color:#32D785; text-align:right; margin-top:10px; }}
            img {{ display:block; margin:16px auto; background:#fff; padding:8px; border-radius:8px; }}
            button {{ width:100%; padding:12px; margin-top:10px; border:0; border-radius:8px; font-weight:900; cursor:pointer; }}
            .btn-print {{ background:#0E5C8C; color:#fff; }}
            .btn-bt {{ background:#1E9E63; color:#fff; }}
        </style>
    </head>
    <body>
        <div class="facture">
            <h2>Table {commande.numero_table}</h2>
            <div class="ligne">{commande.articles_details}</div>
            <div class="total">{commande.total_montant:,.0f} FC</div>
            {f'<img src="data:image/png;base64,{qr_base64}" width="180">' if qr_base64 else '<p style="color:#FF8888;text-align:center;">QR code indisponible (pip install qrcode[pil])</p>'}
            <p style="font-size:11px;color:#8E9BAE;text-align:center;">Scanner pour payer par Mobile Money : {numero_mobile_money or 'numéro non configuré (MOBILE_MONEY_NUMERO)'}</p>
            <button class="btn-print" onclick="window.print()">IMPRIMER</button>
            <button class="btn-bt" onclick="chercherImprimante()">RECHERCHER UNE IMPRIMANTE BLUETOOTH</button>
        </div>
        <script>
        async function chercherImprimante() {{
            try {{
                const device = await navigator.bluetooth.requestDevice({{ acceptAllDevices: true }});
                alert("Imprimante trouvée : " + device.name + "\\n(Connexion et impression ESC/POS à configurer selon le modèle exact.)");
            }} catch (e) {{
                alert("Recherche annulée ou Bluetooth indisponible sur cet appareil : " + e);
            }}
        }}
        </script>
    </body>
    </html>
    """)

@app.post("/cuisine/menu/ajouter")
def ajouter_plat_menu(nom: str = Form(...), prix: float = Form(...), unite: str = Form("morceau"), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    mon_etablissement = user.get("etablissement_id") or (autorises[0] if autorises else None)
    if mon_etablissement:
        crud.ajouter_plat_menu(db, mon_etablissement, nom, prix, unite)
    return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/cuisine/depense")
def enregistrer_depense_cuisine(description: str = Form(...), montant: float = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    mon_etablissement = user.get("etablissement_id") or (autorises[0] if autorises else None)
    if mon_etablissement:
        crud.enregistrer_depense(db, mon_etablissement, description.strip(), montant, user["nom_complet"], "cuisine")
    return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/depenses/ajouter")
def ajouter_depense_generique(description: str = Form(...), montant: float = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in list(MODULE_PAR_ROLE.keys()) + ["super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    mon_etablissement = user.get("etablissement_id") or (autorises[0] if autorises else None)
    module = MODULE_PAR_ROLE.get(user["role"])
    if mon_etablissement:
        crud.enregistrer_depense(db, mon_etablissement, description.strip(), montant, user["nom_complet"], module)
    redirection_url = f"/{module}" if module else "/dashboard"
    return RedirectResponse(url=redirection_url, status_code=status.HTTP_303_SEE_OTHER)

@app.post("/dettes/ajouter")
def ajouter_dette(client_nom: str = Form(...), client_telephone: Optional[str] = Form(None), montant: float = Form(...), motif: Optional[str] = Form(None), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in list(MODULE_PAR_ROLE.keys()) + ["super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    mon_etablissement = user.get("etablissement_id") or (autorises[0] if autorises else None)
    module = MODULE_PAR_ROLE.get(user["role"])
    if mon_etablissement:
        crud.enregistrer_dette(db, mon_etablissement, client_nom.strip(), (client_telephone or "").strip(), montant, (motif or "").strip(), user["nom_complet"], module)
    redirection_url = f"/{module}" if module else "/dashboard"
    return RedirectResponse(url=redirection_url, status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dettes/payer/{dette_id}")
def marquer_dette_payee(dette_id: str, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    crud.payer_dette(db, dette_id, autorises)
    return RedirectResponse(url="/dashboard" if user["role"] == "super_admin" else f"/{MODULE_PAR_ROLE.get(user['role'], 'dashboard')}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/salle", response_class=HTMLResponse)
def salle_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_salle", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redir = verifier_service_actif(user, db, "salle")
    if redir:
        return redir
    autorises = etablissements_autorises(user, db)
    mes_reservations = [r for r in DB_SALLE_FETES if r.get("etablissement_id") in autorises]
    return templates.TemplateResponse(request=request, name="salle.html", context={"user": user, "reservations": mes_reservations, "total_salle": sum(r["montant"] for r in mes_reservations)})

@app.get("/locataires", response_class=HTMLResponse)
def locataires_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_locataires", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redir = verifier_service_actif(user, db, "locataires")
    if redir:
        return redir
    autorises = etablissements_autorises(user, db)
    mes_locataires = [l for l in DB_LOCATAIRES if l.get("etablissement_id") in autorises]
    return templates.TemplateResponse(request=request, name="locataires.html", context={"user": user, "locataires": mes_locataires, "total_locataires": sum(l["montant"] for l in mes_locataires)})

@app.get("/toilettes", response_class=HTMLResponse)
def toilettes_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_toilettes", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redir = verifier_service_actif(user, db, "toilettes")
    if redir:
        return redir
    autorises = etablissements_autorises(user, db)
    mes_passages = crud.get_ventes_non_cloturees(db, autorises, "toilettes")
    return templates.TemplateResponse(request=request, name="toilettes.html", context={"user": user, "total_toilettes": sum(e.montant for e in mes_passages), "passages": mes_passages, "tarif_petit": TARIFS_SYSTEME["toilettes_petit"], "tarif_grand": TARIFS_SYSTEME["toilettes_grand"], "tarif_heure": TARIFS_SYSTEME["flat_heure"]})

@app.post("/toilettes/encaisser")
def encaisser_toilette(montant: float = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user or user["role"] not in ["gerant_toilettes", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    autorises = etablissements_autorises(user, db)
    mon_etablissement = user.get("etablissement_id") or (autorises[0] if autorises else None)
    if mon_etablissement:
        type_besoin = "Petit besoin" if montant == TARIFS_SYSTEME["toilettes_petit"] else "Grand besoin"
        crud.enregistrer_vente(db, mon_etablissement, "toilettes", type_besoin, montant, user["nom_complet"])
    return RedirectResponse(url="/toilettes", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/cloture", response_class=HTMLResponse)
def cloture_page(request: Request, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redirection = refuser_si_fondateur(user)
    if redirection:
        return redirection

    autorises = etablissements_autorises(user, db)
    module = MODULE_PAR_ROLE.get(user["role"])
    if module:
        ventes = crud.get_ventes_non_cloturees(db, autorises, module)
    else:
        ventes = crud.get_ventes_non_cloturees(db, autorises)
    total_attendu = sum(v.montant for v in ventes)

    toutes_clotures = crud.get_clotures_by_etablissement(db, autorises)
    if user["role"] == "super_admin":
        mes_clotures = toutes_clotures
    else:
        mes_clotures = [c for c in toutes_clotures if c.gerant_nom == user["nom_complet"]]

    return templates.TemplateResponse(request=request, name="cloture.html", context={"user": user, "total_attendu": total_attendu, "clotures": mes_clotures, "message": None})

@app.post("/cloture/valider", response_class=HTMLResponse)
def valider_cloture(request: Request, montant_compte: float = Form(...), session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user(session_token, db)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redirection = refuser_si_fondateur(user)
    if redirection:
        return redirection

    autorises = etablissements_autorises(user, db)
    mon_etablissement = user.get("etablissement_id") or (autorises[0] if autorises else None)
    module = MODULE_PAR_ROLE.get(user["role"])

    ventes_a_cloturer = crud.get_ventes_non_cloturees(db, autorises, module)
    depenses_a_cloturer = crud.get_depenses_non_cloturees(db, autorises, module) if module else crud.get_depenses_non_cloturees(db, autorises)

    crud.creer_cloture_et_marquer(
        db, mon_etablissement, user["nom_complet"], ROLES_LABELS.get(user["role"], user["role"]),
        montant_compte, ventes_a_cloturer, depenses_a_cloturer,
        datetime.now().strftime("%H:%M:%S")
    )

    if user["role"] == "gerant_flats":
        for etab_id in autorises:
            for ch in crud.get_chambres_by_etablissement(db, etab_id):
                if ch.statut == "occupee":
                    crud.liberer_chambre(db, ch)

    toutes_clotures = crud.get_clotures_by_etablissement(db, autorises)
    if user["role"] == "super_admin":
        mes_clotures = toutes_clotures
    else:
        mes_clotures = [c for c in toutes_clotures if c.gerant_nom == user["nom_complet"]]

    return templates.TemplateResponse(
        request=request,
        name="cloture.html",
        context={"user": user, "total_attendu": 0.0, "clotures": mes_clotures, "message": f"Service clôturé avec succès ! Recette ({montant_compte:,.0f} FC) envoyée aux archives de la direction."}
    )

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
    services: List[str] = Form([]),
    db: Session = Depends(get_db)
):
    email_clean = email.strip().lower()
    code_otp = str(random.randint(100000, 999999))

    services_valides = [s for s in services if s in crud.TOUS_LES_SERVICES]
    if not services_valides:
        services_valides = crud.TOUS_LES_SERVICES

    DB_OTP_TEMP[email_clean] = {
        "code": code_otp,
        "expire": datetime.utcnow() + timedelta(minutes=15),
        "nom_entreprise": nom_entreprise.strip(),
        "nom_proprietaire": nom_proprietaire.strip(),
        "telephone": telephone.strip(),
        "pin": pin.strip(),
        "services": services_valides
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

    new_org_id = str(uuid.uuid4())
    new_etab_id = str(uuid.uuid4())
    pin_client = data["pin"]
    nom_proprio = data["nom_proprietaire"]
    nom_entreprise = data["nom_entreprise"]
    services_choisis = ",".join(data.get("services", crud.TOUS_LES_SERVICES))

    try:
        nouvelle_org = models.Organisation(
            id=new_org_id,
            nom_entreprise=nom_entreprise,
            nom_proprietaire=nom_proprio,
            email=email_clean,
            telephone=data["telephone"],
            est_active=True,
            est_en_essai=True,
            services_actifs=services_choisis
        )
        db.add(nouvelle_org)
        db.commit()

        nouvel_etablissement = models.Etablissement(id=new_etab_id, organisation_id=new_org_id, nom=nom_entreprise, est_actif=True)
        db.add(nouvel_etablissement)
        db.commit()

        nouvel_utilisateur = models.Utilisateur(
            nom_complet=nom_proprio,
            role="super_admin",
            role_label="Propriétaire / Admin",
            pin=pin_client,
            est_actif=True,
            etablissement_id=new_etab_id
        )
        db.add(nouvel_utilisateur)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"=== ERREUR BDD lors de l'inscription : {e} ===", flush=True)
        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={"email": email_clean, "error": "Erreur technique lors de la création du compte. Réessaie dans un instant."}
        )

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
    except Exception as e:
        db.rollback()
        print(f"Erreur toggle organisation: {e}", flush=True)
    return RedirectResponse(url="/admin/plateforme", status_code=status.HTTP_303_SEE_OTHER)