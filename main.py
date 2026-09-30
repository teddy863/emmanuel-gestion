from fastapi import FastAPI, Request, Form, status, Cookie, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uuid
from datetime import datetime
from typing import Optional
from security import hash_pin, verify_pin, create_access_token, decode_access_token, generate_auto_pin

app = FastAPI(title="Emmanuel - Application de Gestion")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- BASE DE DONNÉES EN MÉMOIRE CENTRALISÉE ---
DB_ETABLISSEMENTS = [
    {"id": "site_1", "nom": "Emmanuel - Bandal", "est_actif": True},
    {"id": "site_2", "nom": "Emmanuel - Tchangu", "est_actif": True}
]

DB_GERANTS = [
    {"id": "admin_1", "nom_complet": "Emmanuel K.", "role": "super_admin", "role_label": "Super Admin", "pin": "1234", "salaire": 0.0, "est_actif": True, "etablissement_id": None, "etablissement_nom": "Tous les sites"},
    {"id": "toilette_1", "nom_complet": "Jeanne M.", "role": "gerant_toilettes", "role_label": "Gérant Toilettes", "pin": "5678", "salaire": 150000.0, "est_actif": True, "etablissement_id": "site_1", "etablissement_nom": "Emmanuel - Bandal"},
    {"id": "flat_1", "nom_complet": "Patrick N.", "role": "gerant_flats", "role_label": "Gérant Flats", "pin": "9012", "salaire": 200000.0, "est_actif": True, "etablissement_id": "site_1", "etablissement_nom": "Emmanuel - Bandal"},
    {"id": "comptoir_1", "nom_complet": "Bibiche T.", "role": "gerant_comptoir", "role_label": "Gérant Comptoir", "pin": "1111", "salaire": 180000.0, "est_actif": True, "etablissement_id": "site_1", "etablissement_nom": "Emmanuel - Bandal"},
    {"id": "cuisine_1", "nom_complet": "Sœur Anne", "role": "cuisinier", "role_label": "Cuisinier", "pin": "2222", "salaire": 180000.0, "est_actif": True, "etablissement_id": "site_1", "etablissement_nom": "Emmanuel - Bandal"},
]

TARIFS_SYSTEME = {
    "toilettes_petit": 500.0,
    "toilettes_grand": 1000.0,
    "flat_heure": 5000.0
}

# Ventes et Dépenses actives
DB_TOILETTES = []
DB_SEJOURS_FLATS = []
DB_VENTES_COMPTOIR = []
DB_CUISINE_VENTES = []
DB_CUISINE_DEPENSES = []

# Registre des dettes enregistrées par les gérants
DB_DETTES = []

DB_CHAMBRES = [
    {"id": "1", "nom": "Ch. 1", "statut": "libre", "montant_recu": 0.0, "duree": 0},
    {"id": "2", "nom": "Ch. 2", "statut": "libre", "montant_recu": 0.0, "duree": 0},
    {"id": "3", "nom": "Ch. 3", "statut": "libre", "montant_recu": 0.0, "duree": 0},
    {"id": "4", "nom": "Ch. 4", "statut": "hors_service", "montant_recu": 0.0, "duree": 0},
    {"id": "5", "nom": "Ch. 5", "statut": "libre", "montant_recu": 0.0, "duree": 0},
    {"id": "6", "nom": "Ch. 6", "statut": "libre", "montant_recu": 0.0, "duree": 0},
]

DB_COMPTOIR = [
    {"id": "1", "nom": "Eau 1,5 L", "unites_par_casier": 12, "prix_achat_casier": 18000.0, "prix_vente": 2000.0, "quantite_stock": 24},
    {"id": "2", "nom": "Mützig 65cl", "unites_par_casier": 12, "prix_achat_casier": 30000.0, "prix_vente": 3500.0, "quantite_stock": 36},
    {"id": "3", "nom": "Coca 33cl", "unites_par_casier": 24, "prix_achat_casier": 36000.0, "prix_vente": 2000.0, "quantite_stock": 48},
]

DB_SALLE_FETES = []
DB_LOCATAIRES = []
DB_CLOTURES = []

ROLES_LABELS = {
    "gerant_toilettes": "Gérant Toilettes",
    "gerant_flats": "Gérant Flats",
    "gerant_comptoir": "Gérant Comptoir",
    "cuisinier": "Cuisinier / Restaurant"
}

def get_current_user(session_token: Optional[str]):
    if not session_token:
        return None
    payload = decode_access_token(session_token)
    if not payload:
        return None
    user_id = payload.get("sub")
    for g in DB_GERANTS:
        if g["id"] == user_id and g["est_actif"]:
            return g
    return None

# --- AUTHENTIFICATION ---
@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
def login(request: Request, pin: str = Form(...)):
    for g in DB_GERANTS:
        if g["pin"] == pin and g["est_actif"]:
            token = create_access_token({"sub": g["id"], "role": g["role"]})
            target_url = "/dashboard" if g["role"] == "super_admin" else f"/{g['role'].replace('gerant_', '')}"
            if g["role"] == "cuisinier":
                target_url = "/cuisine"
            response = RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(key="session_token", value=token, httponly=True)
            return response

    return templates.TemplateResponse(request=request, name="login.html", context={"error": "Code PIN incorrect ou compte désactivé"}, status_code=400)

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("session_token")
    return response

# --- TABLEAU DE BORD & TARIFS SUPER ADMIN ---
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    recette_toilettes = sum(e["montant"] for e in DB_TOILETTES)
    recette_flats = sum(s["montant"] for s in DB_SEJOURS_FLATS)
    recette_comptoir = sum(v["montant"] for v in DB_VENTES_COMPTOIR)
    recette_cuisine = sum(v["montant"] for v in DB_CUISINE_VENTES)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "recette_jour": recette_toilettes + recette_flats + recette_comptoir + recette_cuisine,
            "total_toilettes": recette_toilettes,
            "total_flats": recette_flats,
            "total_comptoir": recette_comptoir,
            "total_cuisine": recette_cuisine,
            "etablissements": DB_ETABLISSEMENTS,
            "clotures": DB_CLOTURES,
            "dettes": DB_DETTES,
            "tarifs": TARIFS_SYSTEME
        }
    )

@app.post("/configuration/tarifs")
@app.post("/admin/configuration/tarifs")
def ajuster_tarifs(
    toilettes_petit: float = Form(...),
    toilettes_grand: float = Form(...),
    flat_heure: float = Form(...),
    session_token: Optional[str] = Cookie(None)
):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    TARIFS_SYSTEME["toilettes_petit"] = toilettes_petit
    TARIFS_SYSTEME["toilettes_grand"] = toilettes_grand
    TARIFS_SYSTEME["flat_heure"] = flat_heure

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

# --- ÉTABLISSEMENTS & GÉRANTS ---
@app.get("/etablissements", response_class=HTMLResponse)
def page_etablissements(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="etablissements.html", context={"user": user, "etablissements": DB_ETABLISSEMENTS})

@app.post("/etablissements/creer")
def creer_etablissement(nom: str = Form(...), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    DB_ETABLISSEMENTS.append({"id": str(uuid.uuid4()), "nom": nom, "est_actif": True})
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/gerants", response_class=HTMLResponse)
def gerants_page(request: Request, nouveau_pin: Optional[str] = None, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="gerants.html", context={"user": user, "gerants": DB_GERANTS, "etablissements": DB_ETABLISSEMENTS, "nouveau_pin": nouveau_pin})

@app.post("/gerants/creer")
def creer_gerant(nom_complet: str = Form(...), role: str = Form(...), salaire: float = Form(150000.0), etablissement_id: Optional[str] = Form(None), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    pin_auto = generate_auto_pin()
    nom_site = next((s["nom"] for s in DB_ETABLISSEMENTS if s["id"] == etablissement_id), "Tous les sites")
    DB_GERANTS.append({
        "id": str(uuid.uuid4()),
        "nom_complet": nom_complet,
        "role": role,
        "role_label": ROLES_LABELS.get(role, role),
        "pin": pin_auto,
        "salaire": salaire,
        "est_actif": True,
        "etablissement_id": etablissement_id,
        "etablissement_nom": nom_site
    })
    return RedirectResponse(url=f"/gerants?nouveau_pin={pin_auto}", status_code=status.HTTP_303_SEE_OTHER)

# --- GESTION DES DETTES CLIENTS ---
@app.post("/dettes/ajouter")
def enregistrer_dette(client_nom: str = Form(...), client_telephone: str = Form(...), montant: float = Form(...), motif: str = Form(...), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    DB_DETTES.append({
        "id": str(uuid.uuid4()),
        "client_nom": client_nom,
        "client_telephone": client_telephone,
        "montant": montant,
        "motif": motif,
        "gerant": user["nom_complet"],
        "est_payee": False,
        "date": datetime.now().strftime("%d/%m/%Y %H:%M")
    })
    return RedirectResponse(url=f"/{user['role'].replace('gerant_', '') if user['role'] != 'cuisinier' else 'cuisine'}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/dettes/payer/{dette_id}")
def regler_dette(dette_id: str, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    for d in DB_DETTES:
        if d["id"] == dette_id:
            d["est_payee"] = True
            d["date_paiement"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            break
    return RedirectResponse(url="/dashboard" if user and user["role"] == "super_admin" else "/", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULES MÉTIERS (ACCÈS ISOLÉ PAR RÔLE) ---
@app.get("/toilettes", response_class=HTMLResponse)
def toilettes_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_toilettes", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="toilettes.html", context={"user": user, "total_toilettes": sum(e["montant"] for e in DB_TOILETTES), "passages": DB_TOILETTES, "tarif_petit": TARIFS_SYSTEME["toilettes_petit"], "tarif_grand": TARIFS_SYSTEME["toilettes_grand"]})

@app.post("/toilettes/encaisser")
def encaisser_toilette(montant: float = Form(...), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_toilettes", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    type_besoin = "Petit besoin" if montant == TARIFS_SYSTEME["toilettes_petit"] else "Grand besoin"
    DB_TOILETTES.append({"id": str(uuid.uuid4()), "montant": montant, "type_besoin": type_besoin, "gerant": user["nom_complet"]})
    return RedirectResponse(url="/toilettes", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/flats", response_class=HTMLResponse)
def flats_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="flats.html", context={"user": user, "chambres": DB_CHAMBRES, "tarif_heure": TARIFS_SYSTEME["flat_heure"]})

@app.post("/flats/occuper")
def occuper_chambre(chambre_id: str = Form(...), montant_percu: float = Form(...), duree: int = Form(...), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    for ch in DB_CHAMBRES:
        if ch["id"] == chambre_id and ch["statut"] == "libre":
            ch["statut"] = "occupee"
            ch["montant_recu"] = montant_percu
            ch["duree"] = duree
            DB_SEJOURS_FLATS.append({"chambre": ch["nom"], "montant": montant_percu, "duree": duree, "gerant": user["nom_complet"]})
            break
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/flats/liberer/{chambre_id}")
def liberer_chambre(chambre_id: str, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    for ch in DB_CHAMBRES:
        if ch["id"] == chambre_id and ch["statut"] == "occupee":
            ch["statut"] = "libre"
            ch["montant_recu"] = 0.0
            ch["duree"] = 0
            break
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/comptoir", response_class=HTMLResponse)
def comptoir_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_comptoir", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="comptoir.html", context={"user": user, "produits": DB_COMPTOIR, "ventes": DB_VENTES_COMPTOIR})

@app.get("/comptoir/vendre_une/{produit_id}")
def vendre_une_bouteille(produit_id: str, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_comptoir", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    for p in DB_COMPTOIR:
        if p["id"] == produit_id and p["quantite_stock"] > 0:
            p["quantite_stock"] -= 1
            cout_unitaire = p["prix_achat_casier"] / p["unites_par_casier"]
            benefice = p["prix_vente"] - cout_unitaire
            DB_VENTES_COMPTOIR.append({"produit": p["nom"], "quantite": 1, "montant": p["prix_vente"], "benefice": benefice, "gerant": user["nom_complet"]})
            break
    return RedirectResponse(url="/comptoir", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/comptoir/ajouter_stock")
def ajouter_stock_casier(nom: str = Form(...), unites_par_casier: int = Form(...), nombre_casiers: int = Form(...), prix_achat_casier: float = Form(...), prix_vente_bouteille: float = Form(...), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_comptoir", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    nouvelles_bouteilles = unites_par_casier * nombre_casiers
    trouve = False
    for p in DB_COMPTOIR:
        if p["nom"].lower() == nom.lower():
            p["quantite_stock"] += nouvelles_bouteilles
            p["prix_achat_casier"] = prix_achat_casier
            p["prix_vente"] = prix_vente_bouteille
            trouve = True
            break
    if not trouve:
        DB_COMPTOIR.append({"id": str(uuid.uuid4()), "nom": nom, "unites_par_casier": unites_par_casier, "prix_achat_casier": prix_achat_casier, "prix_vente": prix_vente_bouteille, "quantite_stock": nouvelles_bouteilles})
    return RedirectResponse(url="/comptoir", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/cuisine", response_class=HTMLResponse)
def cuisine_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="cuisine.html", context={"user": user, "total_ventes": sum(v["montant"] for v in DB_CUISINE_VENTES), "total_depenses": sum(d["montant"] for d in DB_CUISINE_DEPENSES), "depenses": DB_CUISINE_DEPENSES})

@app.post("/cuisine/vendre")
def vendre_combinaison_cuisine(description_plat: str = Form(...), prix_vente: float = Form(...), quantite: int = Form(...), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    total = prix_vente * quantite
    DB_CUISINE_VENTES.append({"plat": description_plat, "quantite": quantite, "montant": total, "cuisinier": user["nom_complet"]})
    return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/cuisine/depense")
def enregistrer_depense_cuisine(description: str = Form(...), montant: float = Form(...), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    DB_CUISINE_DEPENSES.append({"description": description, "montant": montant, "cuisinier": user["nom_complet"]})
    return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/salle", response_class=HTMLResponse)
def salle_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="salle.html", context={"user": user, "reservations": DB_SALLE_FETES})

@app.get("/locataires", response_class=HTMLResponse)
def locataires_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="locataires.html", context={"user": user, "locataires": DB_LOCATAIRES})

# --- CLÔTURE ISOLÉE PAR RÔLE & REINITIALISATION ---
@app.get("/cloture", response_class=HTMLResponse)
def cloture_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # Calcul du montant propre uniquement au rôle connecté
    if user["role"] == "gerant_toilettes":
        total_attendu = sum(e["montant"] for e in DB_TOILETTES)
    elif user["role"] == "gerant_flats":
        total_attendu = sum(s["montant"] for s in DB_SEJOURS_FLATS)
    elif user["role"] == "gerant_comptoir":
        total_attendu = sum(v["montant"] for v in DB_VENTES_COMPTOIR)
    elif user["role"] == "cuisinier":
        total_attendu = sum(v["montant"] for v in DB_CUISINE_VENTES)
    else: # Super Admin
        total_attendu = sum(e["montant"] for e in DB_TOILETTES) + sum(s["montant"] for s in DB_SEJOURS_FLATS) + sum(v["montant"] for v in DB_VENTES_COMPTOIR) + sum(v["montant"] for v in DB_CUISINE_VENTES)

    return templates.TemplateResponse(
        request=request,
        name="cloture.html", 
        context={"user": user, "total_attendu": total_attendu, "clotures": DB_CLOTURES, "message": None}
    )

@app.post("/cloture/valider", response_class=HTMLResponse)
def valider_cloture(request: Request, montant_compte: float = Form(...), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    global DB_TOILETTES, DB_SEJOURS_FLATS, DB_VENTES_COMPTOIR, DB_CUISINE_VENTES, DB_CUISINE_DEPENSES

    # 1. Calcul du montant propre à l'utilisateur
    if user["role"] == "gerant_toilettes":
        total_attendu = sum(e["montant"] for e in DB_TOILETTES)
        detail_txt = f"Toilettes: {total_attendu:,.0f} FC"
        DB_TOILETTES.clear()
    elif user["role"] == "gerant_flats":
        total_attendu = sum(s["montant"] for s in DB_SEJOURS_FLATS)
        detail_txt = f"Flats: {total_attendu:,.0f} FC"
        DB_SEJOURS_FLATS.clear()
        for ch in DB_CHAMBRES:
            if ch["statut"] == "occupee":
                ch["statut"] = "libre"
                ch["montant_recu"] = 0.0
                ch["duree"] = 0
    elif user["role"] == "gerant_comptoir":
        total_attendu = sum(v["montant"] for v in DB_VENTES_COMPTOIR)
        detail_txt = f"Comptoir: {total_attendu:,.0f} FC"
        DB_VENTES_COMPTOIR.clear()
    elif user["role"] == "cuisinier":
        total_attendu = sum(v["montant"] for v in DB_CUISINE_VENTES)
        detail_txt = f"Cuisine: {total_attendu:,.0f} FC"
        DB_CUISINE_VENTES.clear()
        DB_CUISINE_DEPENSES.clear()
    else: # Super admin
        t_toil = sum(e["montant"] for e in DB_TOILETTES)
        t_flat = sum(s["montant"] for s in DB_SEJOURS_FLATS)
        t_comp = sum(v["montant"] for v in DB_VENTES_COMPTOIR)
        t_cuis = sum(v["montant"] for v in DB_CUISINE_VENTES)
        total_attendu = t_toil + t_flat + t_comp + t_cuis
        detail_txt = f"Toilettes: {t_toil:,.0f} FC | Flats: {t_flat:,.0f} FC | Comptoir: {t_comp:,.0f} FC | Cuisine: {t_cuis:,.0f} FC"
        DB_TOILETTES.clear()
        DB_SEJOURS_FLATS.clear()
        DB_VENTES_COMPTOIR.clear()
        DB_CUISINE_VENTES.clear()
        DB_CUISINE_DEPENSES.clear()

    ecart = montant_compte - total_attendu
    maintenant = datetime.now()
    date_str = maintenant.strftime("%d/%m/%Y")
    heure_str = maintenant.strftime("%H:%M:%S")

    # 2. Archivage
    DB_CLOTURES.insert(0, {
        "id": str(uuid.uuid4()),
        "date": date_str,
        "heure": heure_str,
        "gerant": user["nom_complet"],
        "role_label": ROLES_LABELS.get(user["role"], user["role"]),
        "montant_attendu": total_attendu,
        "montant_compte": montant_compte,
        "ecart": ecart,
        "detail": detail_txt
    })

    message_succes = f"Service clôturé avec succès à {heure_str} ! Recette ({montant_compte:,.0f} FC) envoyée aux archives."

    return templates.TemplateResponse(
        request=request,
        name="cloture.html", 
        context={"user": user, "total_attendu": 0.0, "clotures": DB_CLOTURES, "message": message_succes}
    )