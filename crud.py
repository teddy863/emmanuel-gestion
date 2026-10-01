from sqlalchemy.orm import Session
import models

# --- ISOLATION : RECUPERER LES DONNEES D'UNE ORGANISATION/ETABLISSEMENT ---

def get_chambres_by_etablissement(db: Session, etablissement_id: str):
    return db.query(models.Chambre).filter(models.Chambre.etablissement_id == etablissement_id).all()

def get_produits_by_etablissement(db: Session, etablissement_id: str):
    return db.query(models.Produit).filter(models.Produit.etablissement_id == etablissement_id).all()

def get_ventes_by_etablissement_et_module(db: Session, etablissement_id: str, module: str):
    return db.query(models.Vente).filter(
        models.Vente.etablissement_id == etablissement_id,
        models.Vente.module == module
    ).all()

def get_clotures_by_etablissement(db: Session, etablissement_id: str):
    return db.query(models.Cloture).filter(models.Cloture.etablissement_id == etablissement_id).all()

# --- FONCTION D'ENREGISTREMENT UNE VENTE SÉCURISÉE ---

def enregistrer_vente(db: Session, etablissement_id: str, module: str, description: str, montant: float, gerant_nom: str, quantite: int = 1):
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