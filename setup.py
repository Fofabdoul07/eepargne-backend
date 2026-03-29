from flask import Blueprint, request, jsonify
from app import db
from models import User

setup_bp = Blueprint("setup", __name__)

@setup_bp.route("/activate-admin", methods=["POST"])
def activate_admin():
    """Endpoint temporaire pour activer le premier compte admin"""
    data = request.get_json()
    secret = data.get("secret", "")
    telephone = data.get("telephone", "")

    # Clé secrète pour sécuriser cet endpoint
    if secret != "eepargne-setup-2026":
        return jsonify({"erreur": "Clé secrète incorrecte"}), 403

    user = User.query.filter_by(telephone=telephone).first()
    if not user:
        return jsonify({"erreur": "Utilisateur non trouvé"}), 404

    user.is_active = True
    user.is_admin = True
    user.telephone_verifie = True
    db.session.commit()

    return jsonify({
        "message": f"Compte {user.prenom} {user.nom} activé comme administrateur !",
        "telephone": user.telephone,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
    }), 200
