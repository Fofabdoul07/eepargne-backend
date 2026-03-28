from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from models import BonusParrainage, User

parrainage_bp = Blueprint("parrainage", __name__)


# ─── MON CODE DE PARRAINAGE ─────────────────────────────────────────
@parrainage_bp.route("/mon-code", methods=["GET"])
@jwt_required()
def mon_code():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    return jsonify({
        "code_parrainage": user.code_parrainage,
        "lien_parrainage": f"https://e-epargne.com/inscription?parrain={user.code_parrainage}"
    }), 200


# ─── MES FILLEULS ───────────────────────────────────────────────────
@parrainage_bp.route("/mes-filleuls", methods=["GET"])
@jwt_required()
def mes_filleuls():
    user_id = int(get_jwt_identity())
    filleuls = User.query.filter_by(parrain_id=user_id).all()
    return jsonify([{
        "id": f.id,
        "nom": f.nom,
        "prenom": f.prenom,
        "telephone": f.telephone,
        "is_active": f.is_active,
        "joined_at": f.created_at.isoformat(),
    } for f in filleuls]), 200


# ─── MES BONUS ──────────────────────────────────────────────────────
@parrainage_bp.route("/mes-bonus", methods=["GET"])
@jwt_required()
def mes_bonus():
    user_id = int(get_jwt_identity())
    bonus = BonusParrainage.query.filter_by(parrain_id=user_id).order_by(BonusParrainage.created_at.desc()).all()
    total = sum(float(b.montant_bonus) for b in bonus if b.statut == "versé")
    en_attente = sum(float(b.montant_bonus) for b in bonus if b.statut == "en_attente")

    return jsonify({
        "total_verses": total,
        "total_en_attente": en_attente,
        "historique": [b.to_dict() for b in bonus]
    }), 200


# ─── VÉRIFIER UN CODE PARRAINAGE ────────────────────────────────────
@parrainage_bp.route("/verifier/<code>", methods=["GET"])
def verifier_code(code):
    user = User.query.filter_by(code_parrainage=code.upper()).first()
    if user:
        return jsonify({
            "valide": True,
            "parrain": f"{user.prenom} {user.nom}"
        }), 200
    return jsonify({"valide": False, "parrain": None}), 200
