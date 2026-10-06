import uuid
from sqlalchemy import Column, String, Float, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

# --- CLIENT SAAS (ORGANISATION) ---
class Organisation(Base):
    __tablename__ = "organisations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom_entreprise = Column(String, nullable=False)
    nom_proprietaire = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    telephone = Column(String, nullable=True)
    est_active = Column(Boolean, default=True)
    est_en_essai = Column(Boolean, default=True)
    date_creation = Column(DateTime, default=datetime.utcnow)
    
    # Choix des services à la carte lors de l'inscription (ex: "comptoir,cuisine,flats")
    services_actifs = Column(String, nullable=True)

    etablissements = relationship("Etablissement", back_populates="organisation")


class Etablissement(Base):
    __tablename__ = "etablissements"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organisation_id = Column(String, ForeignKey("organisations.id"), nullable=True)
    nom = Column(String, nullable=False)
    est_actif = Column(Boolean, default=True)

    organisation = relationship("Organisation", back_populates="etablissements")
    utilisateurs = relationship("Utilisateur", back_populates="etablissement")
    chambres = relationship("Chambre", back_populates="etablissement")
    produits = relationship("Produit", back_populates="etablissement")
    clotures = relationship("Cloture", back_populates="etablissement")
    plats_menu = relationship("PlatMenu", back_populates="etablissement")
    commandes_tables = relationship("CommandeTable", back_populates="etablissement")


class Utilisateur(Base):
    __tablename__ = "utilisateurs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom_complet = Column(String, nullable=False)
    role = Column(String, nullable=False)
    role_label = Column(String, nullable=False)
    pin = Column(String, nullable=False)
    salaire = Column(Float, default=0.0)
    est_actif = Column(Boolean, default=True)
    etablissement_id = Column(String, ForeignKey("etablissements.id"), nullable=True)

    etablissement = relationship("Etablissement", back_populates="utilisateurs")


class Chambre(Base):
    __tablename__ = "chambres"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom = Column(String, nullable=False)
    statut = Column(String, default="libre")  # libre, occupee, hors_service
    prix_par_heure = Column(Float, default=5000.0)
    montant_recu = Column(Float, default=0.0)
    duree = Column(Integer, default=0)
    etablissement_id = Column(String, ForeignKey("etablissements.id"), nullable=False)

    etablissement = relationship("Etablissement", back_populates="chambres")


class Produit(Base):
    __tablename__ = "produits"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom = Column(String, nullable=False)
    unites_par_casier = Column(Integer, default=12)
    prix_achat_casier = Column(Float, nullable=False)
    prix_vente_bouteille = Column(Float, nullable=False)
    quantite_stock = Column(Integer, default=0)
    etablissement_id = Column(String, ForeignKey("etablissements.id"), nullable=False)

    etablissement = relationship("Etablissement", back_populates="produits")


class PlatMenu(Base):
    """Menu de la cuisine / restaurant."""
    __tablename__ = "plats_menu"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom = Column(String, nullable=False)
    prix = Column(Float, nullable=False)
    unite = Column(String, default="morceau")
    etablissement_id = Column(String, ForeignKey("etablissements.id"), nullable=False)

    etablissement = relationship("Etablissement", back_populates="plats_menu")


class CommandeTable(Base):
    """Facturation / Addition ouverte par table (Cuisine, Restaurant, Comptoir)."""
    __tablename__ = "commandes_tables"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    numero_table = Column(String, nullable=False)
    articles_details = Column(String, nullable=False)
    total_montant = Column(Float, default=0.0)
    est_payee = Column(Boolean, default=False)
    gerant_nom = Column(String, nullable=False)
    date_ouverture = Column(DateTime, default=datetime.utcnow)
    date_cloture = Column(DateTime, nullable=True)

    etablissement_id = Column(String, ForeignKey("etablissements.id"), nullable=False)
    etablissement = relationship("Etablissement", back_populates="commandes_tables")


class Vente(Base):
    __tablename__ = "ventes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    module = Column(String, nullable=False)  # toilettes, flats, comptoir, cuisine, salle, locataires
    description = Column(String, nullable=False)
    quantite = Column(Integer, default=1)
    montant = Column(Float, nullable=False)
    
    # Nouveau pour le calcul du Bénéfice Net
    cout_achat = Column(Float, default=0.0)

    gerant_nom = Column(String, nullable=False)
    date_vente = Column(DateTime, default=datetime.utcnow)
    etablissement_id = Column(String, ForeignKey("etablissements.id"), nullable=False)
    cloture_id = Column(String, ForeignKey("clotures.id"), nullable=True)


class Depense(Base):
    __tablename__ = "depenses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    module = Column(String, nullable=True)  # toilettes, flats, comptoir, cuisine, salle, locataires
    description = Column(String, nullable=False)
    montant = Column(Float, nullable=False)
    gerant_nom = Column(String, nullable=False)
    date_depense = Column(DateTime, default=datetime.utcnow)
    etablissement_id = Column(String, ForeignKey("etablissements.id"), nullable=False)
    cloture_id = Column(String, ForeignKey("clotures.id"), nullable=True)


class Dette(Base):
    """Crédit laissé par un client (Comptoir, Cuisine, Flats, etc.)."""
    __tablename__ = "dettes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    module = Column(String, nullable=True)
    client_nom = Column(String, nullable=False)
    client_telephone = Column(String, nullable=True)
    montant = Column(Float, nullable=False)
    motif = Column(String, nullable=True)
    gerant_nom = Column(String, nullable=False)
    est_payee = Column(Boolean, default=False)
    date_creation = Column(DateTime, default=datetime.utcnow)
    date_paiement = Column(DateTime, nullable=True)
    etablissement_id = Column(String, ForeignKey("etablissements.id"), nullable=False)


class Cloture(Base):
    __tablename__ = "clotures"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    gerant_nom = Column(String, nullable=False)
    role_label = Column(String, nullable=False)
    montant_attendu = Column(Float, nullable=False)
    montant_compte = Column(Float, nullable=False)
    ecart = Column(Float, nullable=False)
    heure_cloture = Column(String, nullable=False)
    date_cloture = Column(DateTime, default=datetime.utcnow)
    etablissement_id = Column(String, ForeignKey("etablissements.id"), nullable=False)

    etablissement = relationship("Etablissement", back_populates="clotures")