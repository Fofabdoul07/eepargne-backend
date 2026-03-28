from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from app import db
from models import User, OTP, Notification
from config import Config
import random

auth_bp = Blueprint("auth", __name__)


def envoyer_otp(telephone, code):
    """Envoi OTP via Africa's Talking (ou simulé en dev)"""
    print(f"[OTP] Envoi du code {code} au {telephone}")
    # En production, décommenter et utiliser Africa's Talking :
    # import africastalking
    # africastalking.initialize(Config.AFRICAS_TALKING_USERNAME, Config.AFRICAS_TALKING_API_KEY)
    # sms = africastalking.SMS
    # sms.send(f"Votre code E-épargne : {code}", [telephone], Config.SENDER_ID)
    return True


# ─── INSCRIPTION ────────────────────────────────────────────────────
@auth_bp.route("/inscription", methods=["POST"])
def inscription():
    data = request.get_json()
    nom = data.get("nom", "").strip()
    prenom = data.get("prenom", "").strip()
    telephone = data.get("telephone", "").strip()
    email = data.get("email", "").strip() or None
    password = data.get("password", "")
    code_parrain = data.get("code_parrainage", None)

    if not all([nom, prenom, telephone, password]):
        return jsonify({"erreur": "Champs obligatoires manquants"}), 400

    if User.query.filter_by(telephone=telephone).first():
        return jsonify({"erreur": "Ce numéro est déjà enregistré"}), 409

    parrain_id = None
    if code_parrain:
        parrain = User.query.filter_by(code_parrainage=code_parrain.upper()).first()
        if parrain:
            parrain_id = parrain.id

    user = User(
        nom=nom,
        prenom=prenom,
        telephone=telephone,
        email=email,
        password_hash=generate_password_hash(password),
        parrain_id=parrain_id,
        is_active=False,
    )
    db.session.add(user)
    db.session.flush()  # pour obtenir l'ID

    # Générer OTP
    code_otp = str(random.randint(100000, 999999))
    otp = OTP(
        telephone=telephone,
        code=code_otp,
        expire_at=datetime.utcnow() + timedelta(minutes=Config.OTP_EXPIRY_MINUTES),
    )
    db.session.add(otp)
    db.session.commit()

    envoyer_otp(telephone, code_otp)

    return jsonify({
        "message": f"Inscription réussie. Code OTP envoyé au {telephone}",
        "telephone": telephone
    }), 201


# ─── VÉRIFICATION OTP ───────────────────────────────────────────────
@auth_bp.route("/verifier-otp", methods=["POST"])
def verifier_otp():
    data = request.get_json()
    telephone = data.get("telephone", "").strip()
    code = data.get("code", "").strip()

    otp = OTP.query.filter_by(
        telephone=telephone, code=code, utilise=False
    ).order_by(OTP.created_at.desc()).first()

    if not otp:
        return jsonify({"erreur": "Code OTP invalide"}), 400

    if datetime.utcnow() > otp.expire_at:
        return jsonify({"erreur": "Code OTP expiré. Veuillez en demander un nouveau"}), 400

    otp.utilise = True
    user = User.query.filter_by(telephone=telephone).first()
    if user:
        user.is_active = True
        user.telephone_verifie = True

        # Notification de bienvenue
        notif = Notification(
            user_id=user.id,
            titre="Bienvenue sur E-épargne 🎉",
            message=f"Bonjour {user.prenom} ! Votre compte est activé. Votre code de parrainage : {user.code_parrainage}",
            type_notif="info"
        )
        db.session.add(notif)

    db.session.commit()
    return jsonify({"message": "Téléphone vérifié avec succès. Compte activé."}), 200


# ─── RENVOI OTP ─────────────────────────────────────────────────────
@auth_bp.route("/renvoyer-otp", methods=["POST"])
def renvoyer_otp():
    data = request.get_json()
    telephone = data.get("telephone", "").strip()

    user = User.query.filter_by(telephone=telephone).first()
    if not user:
        return jsonify({"erreur": "Numéro non trouvé"}), 404

    code_otp = str(random.randint(100000, 999999))
    otp = OTP(
        telephone=telephone,
        code=code_otp,
        expire_at=datetime.utcnow() + timedelta(minutes=Config.OTP_EXPIRY_MINUTES),
    )
    db.session.add(otp)
    db.session.commit()
    envoyer_otp(telephone, code_otp)

    return jsonify({"message": "Nouveau code OTP envoyé"}), 200


# ─── CONNEXION ──────────────────────────────────────────────────────
@auth_bp.route("/connexion", methods=["POST"])
def connexion():
    data = request.get_json()
    telephone = data.get("telephone", "").strip()
    password = data.get("password", "")

    user = User.query.filter_by(telephone=telephone).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"erreur": "Identifiants incorrects"}), 401

    if not user.is_active:
        return jsonify({"erreur": "Compte non activé. Vérifiez votre OTP."}), 403

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "utilisateur": user.to_dict()
    }), 200


# ─── PROFIL ─────────────────────────────────────────────────────────
@auth_bp.route("/profil", methods=["GET"])
@jwt_required()
def profil():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict()), 200


# ─── MODIFIER PROFIL ─────────────────────────────────────────────────
@auth_bp.route("/profil", methods=["PUT"])
@jwt_required()
def modifier_profil():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if "nom" in data:
        user.nom = data["nom"].strip()
    if "prenom" in data:
        user.prenom = data["prenom"].strip()
    if "email" in data:
        user.email = data["email"].strip()
    if "password" in data and data["password"]:
        user.password_hash = generate_password_hash(data["password"])

    db.session.commit()
    return jsonify({"message": "Profil mis à jour", "utilisateur": user.to_dict()}), 200


# ─── REFRESH TOKEN ───────────────────────────────────────────────────
@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    new_token = create_access_token(identity=user_id)
    return jsonify({"access_token": new_token}), 200
