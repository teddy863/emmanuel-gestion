from fastapi import FastAPI, Request, Form, status, Cookie
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
DB_GERANTS = [
    {"id": "admin_1", "nom_complet": "Emmanuel K.", "role": "super_admin", "role_label": "Super Admin", "pin": "1234", "est_actif": True},
    {"id": "toilette_1", "nom_complet": "Jeanne M.", "role": "gerant_toilettes", "role_label": "Gérant Toilettes", "pin": "5678", "est_actif": True},
    {"id": "flat_1", "nom_complet": "Patrick N.", "role": "gerant_flats", "role_label": "Gérant Flats", "pin": "9012", "est_actif": True},
    {"id": "comptoir_1", "nom_complet": "Bibiche T.", "role": "gerant_comptoir", "role_label": "Gérant Comptoir", "pin": "1111", "est_actif": True},
    {"id": "cuisine_1", "nom_complet": "Sœur Anne", "role": "cuisinier", "role_label": "Cuisinier", "pin": "2222", "est_actif": True},
]

CONFIG_TOILETTES = {"petit_besoin": 500.0, "grand_besoin": 1000.0}
DB_TOILETTES = []

DB_CHAMBRES = [
    {"id": "1", "nom": "Ch. 1", "statut": "libre", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
    {"id": "2", "nom": "Ch. 2", "statut": "occupee", "prix_par_heure": 5000.0, "montant_recu": 10000.0, "duree": 2},
    {"id": "3", "nom": "Ch. 3", "statut": "libre", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
    {"id": "4", "nom": "Ch. 4", "statut": "hors_service", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
    {"id": "5", "nom": "Ch. 5", "statut": "libre", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
    {"id": "6", "nom": "Ch. 6", "statut": "libre", "prix_par_heure": 5000.0, "montant_recu": 0.0, "duree": 0},
]
DB_SEJOURS_FLATS = []

DB_COMPTOIR = [
    {"id": "1", "nom": "Eau 1,5 L", "unites_par_casier": 12, "prix_achat_casier": 18000.0, "prix_vente": 2000.0, "quantite_stock": 24},
    {"id": "2", "nom": "Mützig 65cl", "unites_par_casier": 12, "prix_achat_casier": 30000.0, "prix_vente": 3500.0, "quantite_stock": 36},
    {"id": "3", "nom": "Coca 33cl", "unites_par_casier": 24, "prix_achat_casier": 36000.0, "prix_vente": 2000.0, "quantite_stock": 48},
]
DB_VENTES_COMPTOIR = []

DB_CUISINE_VENTES = []
DB_CUISINE_DEPENSES = []

# Historique centralisé des clôtures de caisse
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
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
def login(request: Request, pin: str = Form(...)):
    for g in DB_GERANTS:
        if g["pin"] == pin and g["est_actif"]:
            token = create_access_token({"sub": g["id"], "role": g["role"]})
            
            if g["role"] == "super_admin":
                target_url = "/dashboard"
            elif g["role"] == "gerant_toilettes":
                target_url = "/toilettes"
            elif g["role"] == "gerant_flats":
                target_url = "/flats"
            elif g["role"] == "gerant_comptoir":
                target_url = "/comptoir"
            elif g["role"] == "cuisinier":
                target_url = "/cuisine"
            else:
                target_url = "/"

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
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("session_token")
    return response

# --- TABLEAU DE BORD SUPER ADMIN ---
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    total_toilettes = sum(e["montant"] for e in DB_TOILETTES)
    total_flats = sum(s["montant"] for s in DB_SEJOURS_FLATS)
    total_comptoir = sum(v["montant"] for v in DB_VENTES_COMPTOIR)
    total_cuisine = sum(v["montant"] for v in DB_CUISINE_VENTES)
    
    recette_jour = total_toilettes + total_flats + total_comptoir + total_cuisine
    recette_semaine = recette_jour * 5.2

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "recette_jour": recette_jour,
            "recette_semaine": recette_semaine,
            "total_toilettes": total_toilettes,
            "total_flats": total_flats,
            "total_comptoir": total_comptoir,
            "total_cuisine": total_cuisine,
            "clotures": DB_CLOTURES
        }
    )

# --- GESTION DES GÉRANTS ---
@app.get("/gerants", response_class=HTMLResponse)
def gerants_page(request: Request, nouveau_pin: Optional[str] = None, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="gerants.html", 
        context={"user": user, "gerants": DB_GERANTS, "nouveau_pin": nouveau_pin}
    )

@app.post("/gerants/creer")
def creer_gerant(nom_complet: str = Form(...), role: str = Form(...), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    pin_auto = generate_auto_pin()
    nouveau_gerant = {
        "id": str(uuid.uuid4()),
        "nom_complet": nom_complet,
        "role": role,
        "role_label": ROLES_LABELS.get(role, role),
        "pin": pin_auto,
        "est_actif": True
    }
    DB_GERANTS.append(nouveau_gerant)
    return RedirectResponse(url=f"/gerants?nouveau_pin={pin_auto}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/gerants/toggle/{gerant_id}")
def toggle_gerant(gerant_id: str, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    for g in DB_GERANTS:
        if g["id"] == gerant_id and g["role"] != "super_admin":
            g["est_actif"] = not g["est_actif"]
            break
    return RedirectResponse(url="/gerants", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/gerants/supprimer/{gerant_id}")
def supprimer_gerant(gerant_id: str, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] != "super_admin":
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    global DB_GERANTS
    DB_GERANTS = [g for g in DB_GERANTS if not (g["id"] == gerant_id and g["role"] != "super_admin")]
    return RedirectResponse(url="/gerants", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE TOILETTES ---
@app.get("/toilettes", response_class=HTMLResponse)
def toilettes_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_toilettes", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    total_recette = sum(e["montant"] for e in DB_TOILETTES)
    return templates.TemplateResponse(
        request=request,
        name="toilettes.html", 
        context={
            "user": user, 
            "total_toilettes": total_recette, 
            "passages": DB_TOILETTES,
            "tarif_petit": CONFIG_TOILETTES["petit_besoin"],
            "tarif_grand": CONFIG_TOILETTES["grand_besoin"]
        }
    )

@app.post("/toilettes/encaisser")
def encaisser_toilette(montant: float = Form(...), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_toilettes", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    type_besoin = "Petit besoin" if montant == CONFIG_TOILETTES["petit_besoin"] else "Grand besoin"
    DB_TOILETTES.append({"id": str(uuid.uuid4()), "montant": montant, "type_besoin": type_besoin, "gerant": user["nom_complet"]})
    return RedirectResponse(url="/toilettes", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE FLATS ---
@app.get("/flats", response_class=HTMLResponse)
def flats_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(request=request, name="flats.html", context={"user": user, "chambres": DB_CHAMBRES})

@app.post("/flats/occuper")
def occuper_chambre(
    chambre_id: str = Form(...),
    montant_percu: float = Form(...),
    duree: int = Form(...),
    session_token: Optional[str] = Cookie(None)
):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_flats", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    for ch in DB_CHAMBRES:
        if ch["id"] == chambre_id and ch["statut"] == "libre":
            ch["statut"] = "occupee"
            ch["montant_recu"] = montant_percu
            ch["duree"] = duree
            DB_SEJOURS_FLATS.append({
                "chambre": ch["nom"], 
                "montant": montant_percu, 
                "duree": duree, 
                "gerant": user["nom_complet"]
            })
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

# --- MODULE COMPTOIR ---
@app.get("/comptoir", response_class=HTMLResponse)
def comptoir_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["gerant_comptoir", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request, 
        name="comptoir.html", 
        context={
            "user": user, 
            "produits": DB_COMPTOIR, 
            "ventes": DB_VENTES_COMPTOIR
        }
    )

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
            
            DB_VENTES_COMPTOIR.append({
                "produit": p["nom"], 
                "quantite": 1, 
                "montant": p["prix_vente"], 
                "benefice": benefice, 
                "gerant": user["nom_complet"]
            })
            break
    return RedirectResponse(url="/comptoir", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/comptoir/ajouter_stock")
def ajouter_stock_casier(
    nom: str = Form(...),
    unites_par_casier: int = Form(...),
    nombre_casiers: int = Form(...),
    prix_achat_casier: float = Form(...),
    prix_vente_bouteille: float = Form(...),
    session_token: Optional[str] = Cookie(None)
):
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
        DB_COMPTOIR.append({
            "id": str(uuid.uuid4()),
            "nom": nom,
            "unites_par_casier": unites_par_casier,
            "prix_achat_casier": prix_achat_casier,
            "prix_vente": prix_vente_bouteille,
            "quantite_stock": nouvelles_bouteilles
        })

    return RedirectResponse(url="/comptoir", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE CUISINE & RESTAURANT ---
@app.get("/cuisine", response_class=HTMLResponse)
def cuisine_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    total_ventes = sum(v["montant"] for v in DB_CUISINE_VENTES)
    total_depenses = sum(d["montant"] for d in DB_CUISINE_DEPENSES)

    return templates.TemplateResponse(
        request=request,
        name="cuisine.html", 
        context={
            "user": user, 
            "total_ventes": total_ventes, 
            "total_depenses": total_depenses,
            "depenses": DB_CUISINE_DEPENSES
        }
    )

@app.post("/cuisine/vendre")
def vendre_combinaison_cuisine(
    description_plat: str = Form(...),
    prix_vente: float = Form(...),
    quantite: int = Form(...),
    session_token: Optional[str] = Cookie(None)
):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    total = prix_vente * quantite
    DB_CUISINE_VENTES.append({
        "plat": description_plat, 
        "quantite": quantite, 
        "montant": total, 
        "cuisinier": user["nom_complet"]
    })
    return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/cuisine/depense")
def enregistrer_depense_cuisine(
    description: str = Form(...),
    montant: float = Form(...),
    session_token: Optional[str] = Cookie(None)
):
    user = get_current_user(session_token)
    if not user or user["role"] not in ["cuisinier", "super_admin"]:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    DB_CUISINE_DEPENSES.append({
        "description": description, 
        "montant": montant, 
        "cuisinier": user["nom_complet"]
    })
    return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

# --- CLÔTURE DE CAISSE HORODATÉE ---
@app.get("/cloture", response_class=HTMLResponse)
def cloture_page(request: Request, session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    total_attendu = 0.0
    if user["role"] == "gerant_toilettes":
        total_attendu = sum(e["montant"] for e in DB_TOILETTES)
    elif user["role"] == "gerant_flats":
        total_attendu = sum(s["montant"] for s in DB_SEJOURS_FLATS)
    elif user["role"] == "gerant_comptoir":
        total_attendu = sum(v["montant"] for v in DB_VENTES_COMPTOIR)
    elif user["role"] == "cuisinier":
        total_attendu = sum(v["montant"] for v in DB_CUISINE_VENTES)
    elif user["role"] == "super_admin":
        total_attendu = (
            sum(e["montant"] for e in DB_TOILETTES) + 
            sum(s["montant"] for s in DB_SEJOURS_FLATS) + 
            sum(v["montant"] for v in DB_VENTES_COMPTOIR) + 
            sum(v["montant"] for v in DB_CUISINE_VENTES)
        )

    return templates.TemplateResponse(
        request=request,
        name="cloture.html", 
        context={"user": user, "total_attendu": total_attendu, "message": None}
    )

@app.post("/cloture/valider", response_class=HTMLResponse)
def valider_cloture(request: Request, montant_compte: float = Form(...), session_token: Optional[str] = Cookie(None)):
    user = get_current_user(session_token)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    total_attendu = 0.0
    if user["role"] == "gerant_toilettes":
        total_attendu = sum(e["montant"] for e in DB_TOILETTES)
    elif user["role"] == "gerant_flats":
        total_attendu = sum(s["montant"] for s in DB_SEJOURS_FLATS)
    elif user["role"] == "gerant_comptoir":
        total_attendu = sum(v["montant"] for v in DB_VENTES_COMPTOIR)
    elif user["role"] == "cuisinier":
        total_attendu = sum(v["montant"] for v in DB_CUISINE_VENTES)
    elif user["role"] == "super_admin":
        total_attendu = (
            sum(e["montant"] for e in DB_TOILETTES) + 
            sum(s["montant"] for s in DB_SEJOURS_FLATS) + 
            sum(v["montant"] for v in DB_VENTES_COMPTOIR) + 
            sum(v["montant"] for v in DB_CUISINE_VENTES)
        )

    ecart = montant_compte - total_attendu
    heure_actuelle = datetime.now().strftime("%H:%M:%S")

    # Enregistrement de la clôture avec l'heure exacte
    DB_CLOTURES.append({
        "id": str(uuid.uuid4()),
        "gerant": user["nom_complet"],
        "role_label": ROLES_LABELS.get(user["role"], user["role"]),
        "montant_attendu": total_attendu,
        "montant_compte": montant_compte,
        "ecart": ecart,
        "heure_cloture": heure_actuelle
    })

    message_succes = f"Clôture enregistrée à {heure_actuelle} ! Écart : {ecart:,.0f} FC"

    return templates.TemplateResponse(
        request=request,
        name="cloture.html", 
        context={"user": user, "total_attendu": total_attendu, "message": message_succes}
    )