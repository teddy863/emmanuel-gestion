import uuid
import random
import datetime as _dt
from sqlalchemy.orm import Session
import models

# ==============================================================================
#                           CHAMBRES / FLATS
# ==============================================================================

def get_chambres_by_etablissement(db: Session, etablissement_id: str):
    return db.query(models.Chambre).filter(models.Chambre.etablissement_id == etablissement_id).all()

def get_chambre_by_id(db: Session, chambre_id: str, etablissements_autorises: list):
    return db.query(models.Chambre).filter(
        models.Chambre.id == chambre_id,
        models.Chambre.etablissement_id.in_(etablissements_autorises)
    ).first()

def creer_chambre(db: Session, etablissement_id: str, nom: str, prix_par_heure: float):
    chambre = models.Chambre(etablissement_id=etablissement_id, nom=nom, prix_par_heure=prix_par_heure)
    db.add(chambre)
    db.commit()
    db.refresh(chambre)
    return chambre

def occuper_chambre(db: Session, chambre: models.Chambre, montant: float, duree: int):
    chambre.statut = "occupee"
    chambre.montant_recu = montant
    chambre.duree = duree
    db.commit()
    return chambre

def liberer_chambre(db: Session, chambre: models.Chambre):
    chambre.statut = "libre"
    chambre.montant_recu = 0.0
    chambre.duree = 0
    db.commit()
    return chambre

def changer_statut_chambre(db: Session, chambre: models.Chambre, nouveau_statut: str):
    chambre.statut = nouveau_statut
    if nouveau_statut == "hors_service":
        chambre.montant_recu = 0.0
        chambre.duree = 0
    db.commit()
    return chambre

def renommer_chambre(db: Session, chambre: models.Chambre, nouveau_nom: str):
    chambre.nom = nouveau_nom
    db.commit()
    return chambre


# ==============================================================================
#                           PRODUITS / COMPTOIR
# ==============================================================================

def get_produits_by_etablissement(db: Session, etablissement_id: str):
    return db.query(models.Produit).filter(models.Produit.etablissement_id == etablissement_id).all()

def get_produit_by_id(db: Session, produit_id: str, etablissements_autorises: list):
    return db.query(models.Produit).filter(
        models.Produit.id == produit_id,
        models.Produit.etablissement_id.in_(etablissements_autorises)
    ).first()

def get_produit_par_nom(db: Session, etablissement_id: str, nom: str):
    return db.query(models.Produit).filter(
        models.Produit.etablissement_id == etablissement_id,
        models.Produit.nom.ilike(nom.strip())
    ).first()

def decrementer_stock(db: Session, produit: models.Produit, quantite: int = 1):
    produit.quantite_stock -= quantite
    db.commit()
    return produit

def ajouter_ou_creer_stock(db: Session, etablissement_id: str, nom: str, unites_par_casier: int,
                            nombre_casiers: int, prix_achat_casier: float, prix_vente_bouteille: float):
    produit = get_produit_par_nom(db, etablissement_id, nom)
    nouvelles_unites = unites_par_casier * nombre_casiers
    if produit:
        produit.quantite_stock += nouvelles_unites
        produit.prix_achat_casier = prix_achat_casier
        produit.prix_vente_bouteille = prix_vente_bouteille
        db.commit()
        return produit
    produit = models.Produit(
        etablissement_id=etablissement_id,
        nom=nom.strip(),
        unites_par_casier=unites_par_casier,
        prix_achat_casier=prix_achat_casier,
        prix_vente_bouteille=prix_vente_bouteille,
        quantite_stock=nouvelles_unites
    )
    db.add(produit)
    db.commit()
    db.refresh(produit)
    return produit


# ==============================================================================
#                           MENU CUISINE
# ==============================================================================

def get_menu_by_etablissement(db: Session, etablissement_id: str):
    return db.query(models.PlatMenu).filter(models.PlatMenu.etablissement_id == etablissement_id).all()

def ajouter_plat_menu(db: Session, etablissement_id: str, nom: str, prix: float, unite: str):
    plat = models.PlatMenu(etablissement_id=etablissement_id, nom=nom.strip(), prix=prix, unite=unite.strip())
    db.add(plat)
    db.commit()
    db.refresh(plat)
    return plat


# ==============================================================================
#                           VENTES (toilettes, flats, comptoir, cuisine, salle, locataires)
# ==============================================================================

def enregistrer_vente(db: Session, etablissement_id: str, module: str, description: str,
                       montant: float, gerant_nom: str, quantite: int = 1, cout_achat: float = 0.0):
    nouvelle_vente = models.Vente(
        etablissement_id=etablissement_id,
        module=module,
        description=description,
        montant=montant,
        gerant_nom=gerant_nom,
        quantite=quantite,
        cout_achat=cout_achat
    )
    db.add(nouvelle_vente)
    db.commit()
    db.refresh(nouvelle_vente)
    return nouvelle_vente

def get_ventes_non_cloturees(db: Session, etablissements_autorises: list, module: str = None):
    """Ventes pas encore comptées dans une clôture (cloture_id est vide). C'est le "total attendu" courant."""
    q = db.query(models.Vente).filter(
        models.Vente.etablissement_id.in_(etablissements_autorises),
        models.Vente.cloture_id.is_(None)
    )
    if module:
        q = q.filter(models.Vente.module == module)
    return q.order_by(models.Vente.date_vente.desc()).all()


# ==============================================================================
#                           DÉPENSES (cuisine)
# ==============================================================================

def enregistrer_depense(db: Session, etablissement_id: str, description: str, montant: float, gerant_nom: str, module: str = None):
    depense = models.Depense(etablissement_id=etablissement_id, description=description, montant=montant, gerant_nom=gerant_nom, module=module)
    db.add(depense)
    db.commit()
    db.refresh(depense)
    return depense

def get_depenses_non_cloturees(db: Session, etablissements_autorises: list, module: str = None):
    q = db.query(models.Depense).filter(
        models.Depense.etablissement_id.in_(etablissements_autorises),
        models.Depense.cloture_id.is_(None)
    )
    if module:
        q = q.filter(models.Depense.module == module)
    return q.order_by(models.Depense.date_depense.desc()).all()


# ==============================================================================
#                           DETTES (crédits clients)
# ==============================================================================

def enregistrer_dette(db: Session, etablissement_id: str, client_nom: str, client_telephone: str,
                       montant: float, motif: str, gerant_nom: str, module: str = None):
    dette = models.Dette(
        etablissement_id=etablissement_id, client_nom=client_nom, client_telephone=client_telephone,
        montant=montant, motif=motif, gerant_nom=gerant_nom, module=module
    )
    db.add(dette)
    db.commit()
    db.refresh(dette)
    return dette

def get_dettes(db: Session, etablissements_autorises: list, uniquement_impayees: bool = False):
    q = db.query(models.Dette).filter(models.Dette.etablissement_id.in_(etablissements_autorises))
    if uniquement_impayees:
        q = q.filter(models.Dette.est_payee == False)
    return q.order_by(models.Dette.date_creation.desc()).all()

def payer_dette(db: Session, dette_id: str, etablissements_autorises: list):
    dette = db.query(models.Dette).filter(
        models.Dette.id == dette_id,
        models.Dette.etablissement_id.in_(etablissements_autorises)
    ).first()
    if dette:
        dette.est_payee = True
        dette.date_paiement = _dt.datetime.utcnow()
        db.commit()
    return dette


# ==============================================================================
#                           SERVICES ACTIFS (modules à la carte)
# ==============================================================================

TOUS_LES_SERVICES = ["toilettes", "flats", "comptoir", "cuisine", "salle", "locataires"]

def get_services_actifs(db: Session, organisation_id: str) -> list:
    """Retourne la liste des modules activés pour cette organisation. Si rien n'est défini
    (compte créé avant cette fonctionnalité), tous les modules sont actifs par défaut."""
    if not organisation_id:
        return TOUS_LES_SERVICES
    org = db.query(models.Organisation).filter(models.Organisation.id == organisation_id).first()
    if not org or not org.services_actifs:
        return TOUS_LES_SERVICES
    return [s.strip() for s in org.services_actifs.split(",") if s.strip()]


# ==============================================================================
#                           COMMANDES DE TABLE (restaurant / cuisine)
# ==============================================================================

def get_commandes_ouvertes(db: Session, etablissements_autorises: list):
    return db.query(models.CommandeTable).filter(
        models.CommandeTable.etablissement_id.in_(etablissements_autorises),
        models.CommandeTable.est_payee == False
    ).order_by(models.CommandeTable.date_creation.asc()).all()

def get_commande_par_id(db: Session, commande_id: str, etablissements_autorises: list):
    return db.query(models.CommandeTable).filter(
        models.CommandeTable.id == commande_id,
        models.CommandeTable.etablissement_id.in_(etablissements_autorises)
    ).first()

def ajouter_articles_a_table(db: Session, etablissement_id: str, numero_table: str,
                              description: str, montant: float, gerant_nom: str,
                              montant_comptoir: float = 0.0, cout_comptoir: float = 0.0):
    """Ouvre l'addition de cette table si elle n'existe pas encore (impayée), sinon y ajoute les articles.
    montant_comptoir / cout_comptoir : part de ce montant qui vient des boissons du comptoir."""
    commande = db.query(models.CommandeTable).filter(
        models.CommandeTable.etablissement_id == etablissement_id,
        models.CommandeTable.numero_table == numero_table,
        models.CommandeTable.est_payee == False
    ).first()
    if commande:
        commande.articles_details += f" | {description}"
        commande.total_montant += montant
        commande.total_comptoir = (commande.total_comptoir or 0.0) + montant_comptoir
        commande.cout_comptoir = (commande.cout_comptoir or 0.0) + cout_comptoir
    else:
        commande = models.CommandeTable(
            etablissement_id=etablissement_id,
            numero_table=numero_table,
            articles_details=description,
            total_montant=montant,
            total_comptoir=montant_comptoir,
            cout_comptoir=cout_comptoir,
            gerant_nom=gerant_nom
        )
        db.add(commande)
    db.commit()
    db.refresh(commande)
    return commande

def regler_commande_table(db: Session, commande_id: str, etablissements_autorises: list, gerant_nom: str):
    """Marque l'addition payée et crée les ventes correspondantes : une pour la cuisine, une pour le
    comptoir (avec son coût d'achat), pour que chaque module garde sa vraie recette. Jamais de suppression."""
    commande = get_commande_par_id(db, commande_id, etablissements_autorises)
    if not commande or commande.est_payee:
        return None
    commande.est_payee = True
    commande.date_reglement = _dt.datetime.utcnow()
    db.commit()

    part_comptoir = commande.total_comptoir or 0.0
    part_cuisine = commande.total_montant - part_comptoir
    libelle = f"Table {commande.numero_table} : {commande.articles_details}"
    if part_cuisine > 0:
        enregistrer_vente(db, commande.etablissement_id, "cuisine", libelle, part_cuisine, gerant_nom)
    if part_comptoir > 0:
        enregistrer_vente(db, commande.etablissement_id, "comptoir", libelle, part_comptoir, gerant_nom,
                          cout_achat=commande.cout_comptoir or 0.0)
    return commande


# ==============================================================================
#                           CLÔTURES
# ==============================================================================

def get_clotures_by_etablissement(db: Session, etablissements_autorises: list):
    return db.query(models.Cloture).filter(
        models.Cloture.etablissement_id.in_(etablissements_autorises)
    ).order_by(models.Cloture.date_cloture.desc()).all()

def creer_cloture_et_marquer(db: Session, etablissement_id: str, gerant_nom: str, role_label: str,
                              montant_compte: float, ventes_a_cloturer: list, depenses_a_cloturer: list,
                              heure_str: str):
    """
    Crée la clôture, calcule l'écart, puis MARQUE (ne supprime jamais) les ventes et dépenses
    concernées avec l'id de cette clôture, pour qu'elles ne soient plus comptées la prochaine fois
    tout en restant consultables dans l'historique.
    """
    total_attendu = sum(v.montant for v in ventes_a_cloturer)
    ecart = montant_compte - total_attendu

    cloture = models.Cloture(
        gerant_nom=gerant_nom,
        role_label=role_label,
        montant_attendu=total_attendu,
        montant_compte=montant_compte,
        ecart=ecart,
        heure_cloture=heure_str,
        etablissement_id=etablissement_id
    )
    db.add(cloture)
    db.commit()
    db.refresh(cloture)

    for v in ventes_a_cloturer:
        v.cloture_id = cloture.id
    for d in depenses_a_cloturer:
        d.cloture_id = cloture.id
    db.commit()

    return cloture


# ==============================================================================
#                           GÉRANTS (Utilisateur)
# ==============================================================================

def get_gerants_by_etablissements(db: Session, etablissements_autorises: list):
    return db.query(models.Utilisateur).filter(
        models.Utilisateur.etablissement_id.in_(etablissements_autorises),
        models.Utilisateur.role != "super_admin_fondateur"
    ).all()

def get_utilisateur_par_pin(db: Session, pin: str):
    return db.query(models.Utilisateur).filter(
        models.Utilisateur.pin == pin,
        models.Utilisateur.est_actif == True
    ).first()

def creer_gerant(db: Session, nom_complet: str, role: str, role_label: str, salaire: float, etablissement_id: str):
    pin_auto = f"{random.randint(0, 9999):04d}"
    gerant = models.Utilisateur(
        nom_complet=nom_complet,
        role=role,
        role_label=role_label,
        pin=pin_auto,
        salaire=salaire,
        etablissement_id=etablissement_id
    )
    db.add(gerant)
    db.commit()
    db.refresh(gerant)
    return gerant

def desactiver_gerant(db: Session, gerant_id: str, etablissements_autorises: list):
    """Désactive (jamais ne supprime) un gérant, uniquement s'il appartient au périmètre autorisé."""
    gerant = db.query(models.Utilisateur).filter(
        models.Utilisateur.id == gerant_id,
        models.Utilisateur.etablissement_id.in_(etablissements_autorises),
        models.Utilisateur.role != "super_admin"
    ).first()
    if gerant:
        gerant.est_actif = False
        db.commit()
    return gerant


# ==============================================================================
#                           ÉTABLISSEMENTS
# ==============================================================================

def get_etablissements_by_organisation(db: Session, organisation_id: str):
    return db.query(models.Etablissement).filter(models.Etablissement.organisation_id == organisation_id).all()

def get_etablissement_ids_by_organisation(db: Session, organisation_id: str) -> list:
    try:
        rows = db.query(models.Etablissement.id).filter(models.Etablissement.organisation_id == organisation_id).all()
        return [r.id for r in rows]
    except Exception as e:
        # CRITIQUE : sans ce rollback, Postgres refuse ensuite TOUTE requête de cette
        # même connexion avec "InFailedSqlTransaction" jusqu'à la fin de la requête HTTP.
        db.rollback()
        print(f"Avertissement BDD get_etablissement_ids_by_organisation : {e}", flush=True)
        return []


# ==============================================================================
#                           COMPTABILITÉ : BÉNÉFICE NET
# ==============================================================================

def calculer_bilan(ventes: list, depenses: list) -> dict:
    """Bilan à partir de listes d'objets Vente et Depense :
    chiffre d'affaires, coût d'achat, marge brute, dépenses, bénéfice net."""
    chiffre_affaires = sum(v.montant for v in ventes)
    cout_achat = sum((v.cout_achat or 0.0) for v in ventes)
    total_depenses = sum(d.montant for d in depenses)
    marge_brute = chiffre_affaires - cout_achat
    return {
        "chiffre_affaires": chiffre_affaires,
        "cout_achat": cout_achat,
        "marge_brute": marge_brute,
        "total_depenses": total_depenses,
        "benefice_net": marge_brute - total_depenses,
    }