import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def envoyer_code_otp_email(destinataire_email: str, code_otp: str, nom_etablissement: str):
    # Configuration SMTP gratuite (Gmail ou autre serveur SMTP gratuit)
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    sender_email = os.getenv("SENDER_EMAIL", "votre_email_saas@gmail.com")
    sender_password = os.getenv("SENDER_PASSWORD", "votre_mot_de_passe_app")

    sujet = f"Code de vérification - Activation de {nom_etablissement}"
    corps = f"""
    Bonjour,

    Merci de vous être inscrit sur notre plateforme de gestion SaaS.

    Voici votre code de confirmation à 6 chiffres pour activer votre établissement '{nom_etablissement}' :

    👉 CODE OTP : {code_otp}

    Ce code est valide pendant 15 minutes. Ne le partagez avec personne.

    L'équipe de Gestion.
    """

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = destinataire_email
    msg['Subject'] = sujet
    msg.attach(MIMEText(corps, 'plain'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, destinataire_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Erreur d'envoi e-mail (Mode fallback activé) : {e}")
        return False