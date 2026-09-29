from database import engine, Base, SessionLocal
import models

def init_database():
    print("Création des tables Multi-Tenant dans Supabase...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    # 1. Création de l'établissement par défaut
    site_bandal = db.query(models.Etablissement).filter(models.Etablissement.nom == "Emmanuel - Bandal").first()
    if not site_bandal:
        site_bandal = models.Etablissement(nom="Emmanuel - Bandal", est_actif=True)
        db.add(site_bandal)
        db.commit()
        db.refresh(site_bandal)
        print("Établissement 'Emmanuel - Bandal' créé par défaut.")

    # 2. Création du Super Admin Global
    admin = db.query(models.Utilisateur).filter(models.Utilisateur.role == "super_admin").first()
    if not admin:
        admin_user = models.Utilisateur(
            nom_complet="Emmanuel K.",
            role="super_admin",
            role_label="Super Admin Global",
            pin="1234",
            est_actif=True,
            etablissement_id=None # Accès multi-sites
        )
        db.add(admin_user)
        db.commit()
        print("Super Admin créé par défaut (PIN: 1234).")

    db.close()
    print("Base de données initialisée avec succès !")

if __name__ == "__main__":
    init_database()