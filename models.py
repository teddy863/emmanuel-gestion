import uuid
from sqlalchemy import Column, String, Float, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Etablissement(Base):
    __tablename__ = "etablissements"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom = Column(String, nullable=False)  # ex: "Emmanuel - Bandal", "Emmanuel - Tchangu"
    est_actif = Column(Boolean, default=True)

    utilisateurs = relationship("Utilisateur", back_populates="etablissement")
    chambres = relationship("Chambre", back_populates="etablissement")
    produits = relationship("Produit", back_populates="etablissement")
    clotures = relationship("Cloture", back_populates="etablissement")

class Utilisateur(Base):
    __tablename__ = "utilisateurs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom_complet = Column(String, nullable=False)
    role = Column(String, nullable=False)  # super_admin, gerant_toilettes, gerant_flats, gerant_comptoir, cuisinier
    role_label = Column(String, nullable=False)
    pin = Column(String, nullable=False)
    est_actif = Column(Boolean, default=True)
    etablissement_id = Column(String, ForeignKey("etablissements.id"), nullable=True)  # None pour le Super Admin global

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

class Vente(Base):
    __tablename__ = "ventes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    module = Column(String, nullable=False)  # toilettes, flats, comptoir, cuisine
    description = Column(String, nullable=False)
    quantite = Column(Integer, default=1)
    montant = Column(Float, nullable=False)
    gerant_nom = Column(String, nullable=False)
    date_vente = Column(DateTime, default=datetime.utcnow)
    etablissement_id = Column(String, ForeignKey("etablissements.id"), nullable=False)

class Depense(Base):
    __tablename__ = "depenses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    description = Column(String, nullable=False)
    montant = Column(Float, nullable=False)
    gerant_nom = Column(String, nullable=False)
    date_depense = Column(DateTime, default=datetime.utcnow)
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