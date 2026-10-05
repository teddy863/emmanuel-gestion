import uuid
import random
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
                       montant: float, gerant_nom: str, quantite: int = 1):
    nouvelle_vente = models.Vente(
        etablissement_id=etablissement_id,
        module=module,
        description=description,
        montant=montant,
        gerant_nom=gerant_nom,
        quantite=quantite
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

def enregistrer_depense(db: Session, etablissement_id: str, description: str, montant: float, gerant_nom: str):
    depense = models.Depense(etablissement_id=etablissement_id, description=description, montant=montant, gerant_nom=gerant_nom)
    db.add(depense)
    db.commit()
    db.refresh(depense)
    return depense

def get_depenses_non_cloturees(db: Session, etablissements_autorises: list):
    return db.query(models.Depense).filter(
        models.Depense.etablissement_id.in_(etablissements_autorises),
        models.Depense.cloture_id.is_(None)
    ).order_by(models.Depense.date_depense.desc()).all()


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
    rows = db.query(models.Etablissement.id).filter(models.Etablissement.organisation_id == organisation_id).all()
    return [r.id for r in rows]