import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, 
    ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# --- ÉNUMÉRATIONS (RÔLES ET STATUTS) ---

class RoleEnum(str, PyEnum):
    SUPER_ADMIN = "super_admin"
    GERANT_TOILETTES = "gerant_toilettes"
    GERANT_FLATS = "gerant_flats"
    GERANT_COMPTOIR = "gerant_comptoir"
    CUISINIER = "cuisinier"
    GERANT_SALLE = "gerant_salle"

class StatutChambreEnum(str, PyEnum):
    LIBRE = "libre"
    OCCUPEE = "occupee"
    HORS_SERVICE = "hors_service"

class StatutReservationEnum(str, PyEnum):
    CONFIRMEE = "confirmee"
    ANNULEE = "annulee"

# --- TABLES DE STRUCTURE ET UTILISATEURS ---

class Etablissement(Base):
    """Multi-établissement : Isolation stricte par établissement (Section 4.4)"""
    __tablename__ = "etablissements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nom = Column(String(100), nullable=False)
    taux_change_usd_cdf = Column(Float, nullable=False, default=2800.0)  # Taux USD -> CDF (Section 4.5)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    utilisateurs = relationship("Utilisateur", back_populates="etablissement")


class Utilisateur(Base):
    """Utilisateurs et gérants (Section 2)"""
    __tablename__ = "utilisateurs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    nom_complet = Column(String(100), nullable=False)
    role = Column(Enum(RoleEnum), nullable=False)
    pin_hash = Column(String(255), nullable=False)  # Argon2 hash (Section 4.1)
    est_actif = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    etablissement = relationship("Etablissement", back_populates="utilisateurs")


# --- MODULE TOILETTES ---

class ConfigToilettes(Base):
    """Tarification automatique des toilettes (Section 3.1)"""
    __tablename__ = "config_toilettes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    prix_petit_besoin = Column(Float, nullable=False)
    prix_grand_besoin = Column(Float, nullable=False)


class EntreeToilette(Base):
    """Enregistrement des entrées aux toilettes (Section 3.1)"""
    __tablename__ = "entrees_toilettes"

    id = Column(String(36), primary_key=True)  # UUID généré côté client pour sync hors-ligne
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    gerant_id = Column(String(36), ForeignKey("utilisateurs.id"), nullable=False)
    montant_paye = Column(Float, nullable=False)
    devise = Column(String(3), default="CDF", nullable=False)
    type_besoin = Column(String(20), nullable=False)  # "petit_besoin" ou "grand_besoin"
    nombre_personnes = Column(Integer, default=1, nullable=False)
    
    # Règle d'annulation universelle (Section 2 & 6)
    annule = Column(Boolean, default=False, nullable=False)
    motif_annulation = Column(Text, nullable=True)
    annule_par_id = Column(String(36), ForeignKey("utilisateurs.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# --- MODULE FLATS (CHAMBRES À L'HEURE) ---

class Chambre(Base):
    """Gestion du parc de chambres (Section 3.2)"""
    __tablename__ = "chambres"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    nom = Column(String(50), nullable=False)  # ex: "Ch. 1"
    prix_par_heure = Column(Float, nullable=False)
    statut = Column(Enum(StatutChambreEnum), default=StatutChambreEnum.LIBRE, nullable=False)

    sejours = relationship("SejourFlat", back_populates="chambre")


class SejourFlat(Base):
    """Occupation d'une chambre (Section 3.2)"""
    __tablename__ = "sejours_flats"

    id = Column(String(36), primary_key=True)  # UUID généré côté client
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    chambre_id = Column(String(36), ForeignKey("chambres.id"), nullable=False)
    gerant_id = Column(String(36), ForeignKey("utilisateurs.id"), nullable=False)
    nom_client = Column(String(100), nullable=True)
    
    duree_heures = Column(Integer, nullable=False)
    montant_paye = Column(Float, nullable=False)
    devise = Column(String(3), default="CDF", nullable=False)
    
    date_debut = Column(DateTime, default=datetime.utcnow, nullable=False)
    date_fin_prevue = Column(DateTime, nullable=False)
    date_liberation_effective = Column(DateTime, nullable=True)
    
    # Traçabilité des prolongations sans effacer la saisie initiale
    est_prolongation = Column(Boolean, default=False, nullable=False)
    sejour_parent_id = Column(String(36), ForeignKey("sejours_flats.id"), nullable=True)

    # Règle d'annulation universelle
    annule = Column(Boolean, default=False, nullable=False)
    motif_annulation = Column(Text, nullable=True)
    annule_par_id = Column(String(36), ForeignKey("utilisateurs.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    chambre = relationship("Chambre", back_populates="sejours")


# --- MODULE COMPTOIR ---

class ProduitComptoir(Base):
    """Catalogue produits et stock du comptoir (Section 3.3)"""
    __tablename__ = "produits_comptoir"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    nom = Column(String(100), nullable=False)
    prix_achat = Column(Float, nullable=False)
    prix_vente = Column(Float, nullable=False)
    quantite_stock = Column(Integer, default=0, nullable=False)
    seuil_alerte = Column(Integer, default=5, nullable=False)


class VenteComptoir(Base):
    """Enregistrement des ventes au comptoir (Section 3.3)"""
    __tablename__ = "ventes_comptoir"

    id = Column(String(36), primary_key=True)  # UUID généré côté client
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    produit_id = Column(String(36), ForeignKey("produits_comptoir.id"), nullable=False)
    gerant_id = Column(String(36), ForeignKey("utilisateurs.id"), nullable=False)
    
    quantite = Column(Integer, nullable=False)
    prix_total = Column(Float, nullable=False)
    benefice_calcule = Column(Float, nullable=False)
    devise = Column(String(3), default="CDF", nullable=False)

    annule = Column(Boolean, default=False, nullable=False)
    motif_annulation = Column(Text, nullable=True)
    annule_par_id = Column(String(36), ForeignKey("utilisateurs.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# --- MODULE CUISINE / RESTAURANT ---

class PlatCuisine(Base):
    """Stock journalier des plats préparés (Section 3.4)"""
    __tablename__ = "plats_cuisine"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    nom = Column(String(100), nullable=False)
    prix_vente = Column(Float, nullable=False)
    quantite_preparee = Column(Integer, default=0, nullable=False)
    quantite_restante = Column(Integer, default=0, nullable=False)


class VentePlat(Base):
    """Ventes de plats enregistrées par le cuisinier (Section 3.4)"""
    __tablename__ = "ventes_plats"

    id = Column(String(36), primary_key=True)  # UUID généré côté client
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    plat_id = Column(String(36), ForeignKey("plats_cuisine.id"), nullable=False)
    cuisinier_id = Column(String(36), ForeignKey("utilisateurs.id"), nullable=False)
    
    quantite = Column(Integer, default=1, nullable=False)
    montant_vente = Column(Float, nullable=False)
    description_plat = Column(Text, nullable=True)
    devise = Column(String(3), default="CDF", nullable=False)

    annule = Column(Boolean, default=False, nullable=False)
    motif_annulation = Column(Text, nullable=True)
    annule_par_id = Column(String(36), ForeignKey("utilisateurs.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DepenseCuisine(Base):
    """Achats d'ingrédients par la cuisine (Section 3.4)"""
    __tablename__ = "depenses_cuisine"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    cuisinier_id = Column(String(36), ForeignKey("utilisateurs.id"), nullable=False)
    description = Column(String(255), nullable=False)
    montant = Column(Float, nullable=False)
    devise = Column(String(3), default="CDF", nullable=False)

    annule = Column(Boolean, default=False, nullable=False)
    motif_annulation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# --- MODULE SALLE DE FÊTE ---

class ReservationSalle(Base):
    """Réservations d'événements (Section 3.5)"""
    __tablename__ = "reservations_salle"

    id = Column(String(36), primary_key=True)  # UUID généré côté client
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    nom_client = Column(String(100), nullable=False)
    telephone_client = Column(String(20), nullable=False)
    date_evenement = Column(DateTime, nullable=False)
    
    prix_total = Column(Float, nullable=False)
    acompte_verse = Column(Float, default=0.0, nullable=False)
    solde_restant = Column(Float, nullable=False)
    devise = Column(String(3), default="CDF", nullable=False)
    
    statut = Column(Enum(StatutReservationEnum), default=StatutReservationEnum.CONFIRMEE, nullable=False)
    forcage_super_admin = Column(Boolean, default=False, nullable=False)
    montant_rembourse = Column(Float, default=0.0, nullable=False)  # En cas d'annulation

    annule = Column(Boolean, default=False, nullable=False)
    motif_annulation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# --- MODULE LOCATAIRES (BAIL LONGUE DURÉE) ---

class Locataire(Base):
    """Fiche locataire (Section 3.6)"""
    __tablename__ = "locataires"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    nom_complet = Column(String(100), nullable=False)
    telephone = Column(String(20), nullable=False)
    numero_logement = Column(String(20), nullable=False)
    
    montant_loyer = Column(Float, nullable=False)
    montant_garantie = Column(Float, nullable=False)
    jour_echeance_mensuelle = Column(Integer, nullable=False)  # ex: 5 pour le 5 du mois
    devise = Column(String(3), default="CDF", nullable=False)
    
    garantie_restituee = Column(Float, default=0.0, nullable=False)
    est_actif = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaiementLoyer(Base):
    """Enregistrement des loyers (Section 3.6)"""
    __tablename__ = "paiements_loyers"

    id = Column(String(36), primary_key=True)
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    locataire_id = Column(String(36), ForeignKey("locataires.id"), nullable=False)
    
    montant = Column(Float, nullable=False)
    devise = Column(String(3), default="CDF", nullable=False)
    reference_transaction = Column(String(100), nullable=True)  # Référence Mobile Money
    mois_concerne = Column(String(7), nullable=False)  # ex: "2026-09"

    annule = Column(Boolean, default=False, nullable=False)
    motif_annulation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# --- CLÔTURE DE CAISSE ET AUDIT LOG ---

class ClotureCaisse(Base):
    """Clôture de fin de service par gérant (Section 3.8)"""
    __tablename__ = "clotures_caisse"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    gerant_id = Column(String(36), ForeignKey("utilisateurs.id"), nullable=False)
    poste = Column(String(50), nullable=False)  # ex: "comptoir", "toilettes"
    
    total_attendu = Column(Float, nullable=False)
    total_compte = Column(Float, nullable=False)
    ecart = Column(Float, nullable=False)
    motif_ecart = Column(Text, nullable=True)
    devise = Column(String(3), default="CDF", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(Base):
    """Journal d'audit infalsifiable (Section 4.1)"""
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    etablissement_id = Column(String(36), ForeignKey("etablissements.id"), nullable=False)
    utilisateur_id = Column(String(36), ForeignKey("utilisateurs.id"), nullable=False)
    action = Column(String(100), nullable=False)  # ex: "ANNULATION_VENTE", "CLOTURE_CAISSE"
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)