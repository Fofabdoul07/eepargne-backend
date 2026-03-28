from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, date
from app import db
from models import Pret, Groupe, Membership, Paiement, Notification, User
from routes.payments import calculer_commission

loans_bp = Blueprint("loans", __name__)


# ─── DEMANDER UN PRÊT ───────────────────────────────────────────────
@loans_bp.route("/demander", methods=["POST"])
@jwt_required()
def demander_pret():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    groupe_id = data.get("groupe_id")
    montant = data.get("montant")
    taux_interet = data.get("taux_interet", 5.0)
    motif = data.get("motif", "")
    date_echeance = data.get("date_echeance")

    if not groupe_id or not montant:
        return jsonify({"erreur": "Groupe et montant obligatoires"}), 400

    groupe = Groupe.query.get_or_404(groupe_id)
    membership = Membership.query.filter_by(groupe_id=groupe_id, user_id=user_id, statut="actif").first()
    if not membership:
        return jsonify({"erreur": "Vous n'êtes pas membre de ce groupe"}), 403

    # Vérifier qu'il n'a pas déjà un prêt en cours
    pret_actif = Pret.query.filter(
        Pret.groupe_id == groupe_id,
        Pret.emprunteur_id == user_id,
        Pret.statut.in_(["approuvé", "en_cours"])
    ).first()
    if pret_actif:
        return jsonify({"erreur": "Vous avez déjà un prêt actif dans ce groupe"}), 400

    montant_a_rembourser = round(float(montant) * (1 + float(taux_interet) / 100), 2)

    pret = Pret(
        groupe_id=groupe_id,
        emprunteur_id=user_id,
        montant=montant,
        taux_interet=taux_interet,
        montant_a_rembourser=montant_a_rembourser,
        motif=motif,
        date_echeance=datetime.strptime(date_echeance, "%Y-%m-%d").date() if date_echeance else None,
        statut="demande",
    )
    db.session.add(pret)

    # Notifier l'admin du groupe
    notif = Notification(
        user_id=groupe.createur_id,
        titre="Demande de prêt 📋",
        message=f"Un membre a demandé un prêt de {montant} FCFA dans '{groupe.nom}'",
        type_notif="pret"
    )
    db.session.add(notif)
    db.session.commit()

    return jsonify({"message": "Demande de prêt envoyée", "pret": pret.to_dict()}), 201


# ─── APPROUVER / REFUSER UN PRÊT ────────────────────────────────────
@loans_bp.route("/<int:pret_id>/decision", methods=["PUT"])
@jwt_required()
def decider_pret(pret_id):
    user_id = int(get_jwt_identity())
    data = request.get_json()
    decision = data.get("decision", "").lower()  # "approuvé" ou "refusé"

    if decision not in ["approuvé", "refusé"]:
        return jsonify({"erreur": "Décision invalide. Choisir 'approuvé' ou 'refusé'"}), 400

    pret = Pret.query.get_or_404(pret_id)
    groupe = Groupe.query.get(pret.groupe_id)

    # Vérifier droits
    membership = Membership.query.filter_by(groupe_id=pret.groupe_id, user_id=user_id).first()
    est_admin = membership and membership.role in ["admin_groupe", "tresorier"]
    est_createur = groupe.createur_id == user_id
    user = User.query.get(user_id)

    if not (est_admin or est_createur or user.is_admin):
        return jsonify({"erreur": "Accès refusé. Admin groupe requis"}), 403

    pret.statut = decision
    pret.valideur_id = user_id
    if decision == "approuvé":
        pret.approved_at = datetime.utcnow()
        pret.statut = "en_cours"
        msg = f"Votre demande de prêt de {pret.montant} FCFA a été approuvée 🎉"
    else:
        msg = f"Votre demande de prêt de {pret.montant} FCFA a été refusée."

    notif = Notification(
        user_id=pret.emprunteur_id,
        titre="Décision sur votre prêt",
        message=msg,
        type_notif="pret"
    )
    db.session.add(notif)
    db.session.commit()

    return jsonify({"message": f"Prêt {decision}", "pret": pret.to_dict()}), 200


# ─── REMBOURSER UN PRÊT ─────────────────────────────────────────────
@loans_bp.route("/<int:pret_id>/rembourser", methods=["POST"])
@jwt_required()
def rembourser_pret(pret_id):
    user_id = int(get_jwt_identity())
    data = request.get_json()
    montant_versement = float(data.get("montant", 0))
    mode_paiement = data.get("mode_paiement", "wave")
    numero_paiement = data.get("numero_paiement", "")

    pret = Pret.query.get_or_404(pret_id)

    if pret.emprunteur_id != user_id:
        return jsonify({"erreur": "Ce prêt ne vous appartient pas"}), 403

    if pret.statut not in ["approuvé", "en_cours"]:
        return jsonify({"erreur": "Ce prêt ne peut pas être remboursé"}), 400

    restant = float(pret.montant_a_rembourser) - float(pret.montant_rembourse)
    if montant_versement > restant:
        return jsonify({"erreur": f"Montant dépasse le restant dû ({restant} FCFA)"}), 400

    commission, montant_net = calculer_commission(montant_versement)

    paiement = Paiement(
        user_id=user_id,
        groupe_id=pret.groupe_id,
        montant_brut=montant_versement,
        commission=commission,
        montant_net=montant_net,
        mode_paiement=mode_paiement,
        numero_paiement=numero_paiement,
        statut="en_attente",
        type_paiement="remboursement_pret",
    )
    db.session.add(paiement)

    pret.montant_rembourse = float(pret.montant_rembourse) + montant_versement

    if float(pret.montant_rembourse) >= float(pret.montant_a_rembourser):
        pret.statut = "remboursé"
        notif_msg = "Votre prêt a été entièrement remboursé ✅"
    else:
        notif_msg = f"Versement de {montant_versement} FCFA enregistré. Restant : {restant - montant_versement} FCFA"

    notif = Notification(
        user_id=user_id,
        titre="Remboursement enregistré",
        message=notif_msg,
        type_notif="pret"
    )
    db.session.add(notif)
    db.session.commit()

    return jsonify({
        "message": "Remboursement enregistré",
        "montant_rembourse": float(pret.montant_rembourse),
        "restant_du": float(pret.montant_a_rembourser) - float(pret.montant_rembourse),
        "statut_pret": pret.statut,
    }), 200


# ─── MES PRÊTS ──────────────────────────────────────────────────────
@loans_bp.route("/mes-prets", methods=["GET"])
@jwt_required()
def mes_prets():
    user_id = int(get_jwt_identity())
    prets = Pret.query.filter_by(emprunteur_id=user_id).order_by(Pret.created_at.desc()).all()
    return jsonify([p.to_dict() for p in prets]), 200


# ─── PRÊTS D'UN GROUPE (admin) ──────────────────────────────────────
@loans_bp.route("/groupe/<int:groupe_id>", methods=["GET"])
@jwt_required()
def prets_groupe(groupe_id):
    user_id = int(get_jwt_identity())
    groupe = Groupe.query.get_or_404(groupe_id)
    membership = Membership.query.filter_by(groupe_id=groupe_id, user_id=user_id).first()

    if not (membership and membership.role in ["admin_groupe", "tresorier"]) and groupe.createur_id != user_id:
        return jsonify({"erreur": "Accès refusé"}), 403

    statut = request.args.get("statut")
    query = Pret.query.filter_by(groupe_id=groupe_id)
    if statut:
        query = query.filter_by(statut=statut)

    prets = query.order_by(Pret.created_at.desc()).all()
    return jsonify([p.to_dict() for p in prets]), 200
