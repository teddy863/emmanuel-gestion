from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from security import hash_pin, verify_pin, create_access_token

app = FastAPI(title="Emmanuel - Application de Gestion")

# Support PWA et fichiers statiques
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DEMO_PIN_HASH = hash_pin("1234")

# Données simulées en mémoire (Conformes au schéma models.py)
DB_TOILETTES = []
DB_CHAMBRES = [
    {"id": "1", "nom": "Ch. 1", "statut": "libre", "prix_par_heure": 5000.0},
    {"id": "2", "nom": "Ch. 2", "statut": "occupee", "prix_par_heure": 5000.0},
    {"id": "3", "nom": "Ch. 3", "statut": "libre", "prix_par_heure": 5000.0},
    {"id": "4", "nom": "Ch. 4", "statut": "libre", "prix_par_heure": 5000.0},
    {"id": "5", "nom": "Ch. 5", "statut": "libre", "prix_par_heure": 5000.0},
    {"id": "6", "nom": "Ch. 6", "statut": "libre", "prix_par_heure": 5000.0},
]
DB_COMPTOIR = [
    {"id": "1", "nom": "Eau minérale 1,5 L", "prix_vente": 2000.0, "quantite_stock": 4, "seuil_alerte": 5},
    {"id": "2", "nom": "Sucrerie (1 L)", "prix_vente": 6500.0, "quantite_stock": 18, "seuil_alerte": 5},
    {"id": "3", "nom": "Boisson gazeuse 33 cl", "prix_vente": 3500.0, "quantite_stock": 3, "seuil_alerte": 5},
]
DB_VENTES_COMPTOIR = []

DB_CUISINE = [
    {"id": "1", "nom": "Riz + poulet", "prix_vente": 3500.0, "quantite_restante": 12},
    {"id": "2", "nom": "Fufu + pondu", "prix_vente": 4000.0, "quantite_restante": 8},
    {"id": "3", "nom": "Poisson braisé + riz", "prix_vente": 5000.0, "quantite_restante": 2},
]
DB_VENTES_CUISINE = []

DB_SALLE = [
    {"nom_client": "Mariage Kabeya", "date_evenement": "2026-10-03", "prix_total": 1200000.0, "acompte": 600000.0, "solde": 600000.0}
]

DB_LOCATAIRES = [
    {"id": "1", "nom": "Kabila Mbala", "logement": "Logement 3", "loyer": 150000.0, "statut": "a_jour"},
    {"id": "2", "nom": "Nsimba Thérèse", "logement": "Logement 7", "loyer": 150000.0, "statut": "en_retard"}
]

@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
def login(request: Request, pin: str = Form(...)):
    if verify_pin(pin, DEMO_PIN_HASH):
        token = create_access_token({"sub": "admin_demo", "role": "super_admin"})
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="session_token", value=token, httponly=True)
        return response
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": "Code PIN incorrect"}, status_code=400
    )

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    total_toilettes = sum(entry["montant"] for entry in DB_TOILETTES)
    total_flats = sum(10000.0 for ch in DB_CHAMBRES if ch["statut"] == "occupee")
    total_comptoir = sum(v["montant"] for v in DB_VENTES_COMPTOIR)
    total_cuisine = sum(v["montant"] for v in DB_VENTES_CUISINE)
    total_salle = sum(r["acompte"] for r in DB_SALLE)
    
    recette_jour = total_toilettes + total_flats + total_comptoir + total_cuisine + total_salle
    recette_semaine = recette_jour * 5.2

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "recette_jour": recette_jour,
            "recette_semaine": recette_semaine,
            "total_toilettes": total_toilettes,
            "total_flats": total_flats,
            "total_comptoir": total_comptoir,
            "total_cuisine": total_cuisine,
        }
    )

# --- MODULE FLATS ---
@app.get("/flats", response_class=HTMLResponse)
def flats_page(request: Request):
    return templates.TemplateResponse(request=request, name="flats.html", context={"chambres": DB_CHAMBRES})

@app.get("/flats/occuper/{chambre_id}")
def occuper_chambre(chambre_id: str):
    for ch in DB_CHAMBRES:
        if ch["id"] == chambre_id:
            ch["statut"] = "occupee"
            break
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/flats/liberer/{chambre_id}")
def liberer_chambre(chambre_id: str):
    for ch in DB_CHAMBRES:
        if ch["id"] == chambre_id:
            ch["statut"] = "libre"
            break
    return RedirectResponse(url="/flats", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE TOILETTES ---
@app.get("/toilettes", response_class=HTMLResponse)
def toilettes_page(request: Request):
    total_toilettes = sum(entry["montant"] for entry in DB_TOILETTES)
    return templates.TemplateResponse(
        request=request, name="toilettes.html", context={"total_toilettes": total_toilettes, "passages": DB_TOILETTES}
    )

@app.get("/toilettes/payer")
def payer_toilette(montant: float, type: str):
    label = "Petit besoin" if type == "petit_besoin" else "Grand besoin"
    DB_TOILETTES.append({"montant": montant, "type_label": label})
    return RedirectResponse(url="/toilettes", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE COMPTOIR ---
@app.get("/comptoir", response_class=HTMLResponse)
def comptoir_page(request: Request):
    return templates.TemplateResponse(request=request, name="comptoir.html", context={"produits": DB_COMPTOIR})

@app.get("/comptoir/vendre/{produit_id}")
def vendre_comptoir(produit_id: str):
    for p in DB_COMPTOIR:
        if p["id"] == produit_id and p["quantite_stock"] > 0:
            p["quantite_stock"] -= 1
            DB_VENTES_COMPTOIR.append({"montant": p["prix_vente"]})
            break
    return RedirectResponse(url="/comptoir", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE CUISINE ---
@app.get("/cuisine", response_class=HTMLResponse)
def cuisine_page(request: Request):
    total_cuisine = sum(v["montant"] for v in DB_VENTES_CUISINE)
    return templates.TemplateResponse(
        request=request, name="cuisine.html", context={"plats": DB_CUISINE, "total_cuisine": total_cuisine}
    )

@app.get("/cuisine/vendre/{plat_id}")
def vendre_plat(plat_id: str):
    for p in DB_CUISINE:
        if p["id"] == plat_id and p["quantite_restante"] > 0:
            p["quantite_restante"] -= 1
            DB_VENTES_CUISINE.append({"montant": p["prix_vente"]})
            break
    return RedirectResponse(url="/cuisine", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE SALLE DE FÊTE ---
@app.get("/salle", response_class=HTMLResponse)
def salle_page(request: Request, error: str = None):
    return templates.TemplateResponse(
        request=request, name="salle.html", context={"reservations": DB_SALLE, "error": error}
    )

@app.post("/salle/reserver")
def reserver_salle(
    request: Request,
    nom_client: str = Form(...),
    telephone: str = Form(...),
    date_evenement: str = Form(...),
    prix_total: float = Form(...),
    acompte: float = Form(...)
):
    # Règle Exigence 3.5 : Blocage automatique des doublons sur la même date
    for r in DB_SALLE:
        if r["date_evenement"] == date_evenement:
            return templates.TemplateResponse(
                request=request,
                name="salle.html",
                context={"reservations": DB_SALLE, "error": f"La date du {date_evenement} est déjà réservée !"},
                status_code=400
            )
    
    solde = prix_total - acompte
    DB_SALLE.append({
        "nom_client": nom_client,
        "telephone": telephone,
        "date_evenement": date_evenement,
        "prix_total": prix_total,
        "acompte": acompte,
        "solde": solde
    })
    return RedirectResponse(url="/salle", status_code=status.HTTP_303_SEE_OTHER)

# --- MODULE LOCATAIRES ---
@app.get("/locataires", response_class=HTMLResponse)
def locataires_page(request: Request):
    return templates.TemplateResponse(request=request, name="locataires.html", context={"locataires": DB_LOCATAIRES})

@app.get("/locataires/contrat/{locataire_id}")
def contrat_bail(locataire_id: str):
    # Simulation de la génération du contrat de bail PDF (Section 3.6)
    return HTMLResponse(f"<h1>CONTRAT DE BAIL (PDF)</h1><p>Généré automatiquement avec le logo de l'établissement pour le locataire ID #{locataire_id}.</p><a href='/locataires'>Retour</a>")

# --- MODULE CLÔTURE DE CAISSE ---
@app.get("/cloture", response_class=HTMLResponse)
def cloture_page(request: Request):
    total_attendu = (
        sum(entry["montant"] for entry in DB_TOILETTES) +
        sum(v["montant"] for v in DB_VENTES_COMPTOIR) +
        sum(v["montant"] for v in DB_VENTES_CUISINE)
    )
    return templates.TemplateResponse(
        request=request, name="cloture.html", context={"total_attendu": total_attendu, "ecart": None}
    )

@app.post("/cloture/calculer", response_class=HTMLResponse)
def calculer_cloture(request: Request, montant_compte: float = Form(...)):
    total_attendu = (
        sum(entry["montant"] for entry in DB_TOILETTES) +
        sum(v["montant"] for v in DB_VENTES_COMPTOIR) +
        sum(v["montant"] for v in DB_VENTES_CUISINE)
    )
    ecart = montant_compte - total_attendu
    return templates.TemplateResponse(
        request=request, name="cloture.html", context={"total_attendu": total_attendu, "ecart": ecart}
    )