from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from app import db
from models import User, Groupe, Paiement, Pret, BonusParrainage, Membership, Notification
import csv, io
from flask import Response

admin_bp = Blueprint("admin", __name__)


def verifier_admin(user_id):
    user = User.query.get(user_id)
    return user and user.is_admin


# ─── TABLEAU DE BORD STATISTIQUES ───────────────────────────────────
@admin_bp.route("/dashboard", methods=["GET"])
@jwt_required()
def dashboard():
    user_id = int(get_jwt_identity())
    if not verifier_admin(user_id):
        return jsonify({"erreur": "Accès réservé aux administrateurs"}), 403

    # Membres
    total_membres = User.query.filter_by(is_admin=False).count()
    membres_actifs = User.query.filter_by(is_active=True, is_admin=False).count()

    # Groupes
    total_groupes = Groupe.query.count()
    groupes_actifs = Groupe.query.filter_by(statut="actif").count()

    # Épargne totale
    total_epargne = db.session.query(func.sum(Paiement.montant_net)).filter(
        Paiement.statut == "confirmé", Paiement.type_paiement == "cotisation"
    ).scalar() or 0

    # Commissions collectées
    total_commissions = db.session.query(func.sum(Paiement.commission)).filter(
        Paiement.statut == "confirmé"
    ).scalar() or 0

    # Prêts
    total_prets = Pret.query.count()
    prets_en_cours = Pret.query.filter_by(statut="en_cours").count()
    prets_rembourses = Pret.query.filter_by(statut="remboursé").count()
    encours_prets = db.session.query(func.sum(Pret.montant)).filter(
        Pret.statut.in_(["approuvé", "en_cours"])
    ).scalar() or 0

    # Bonus parrainage
    total_bonus_verses = db.session.query(func.sum(BonusParrainage.montant_bonus)).filter(
        BonusParrainage.statut == "versé"
    ).scalar() or 0

    # Paiements récents (7 derniers)
    paiements_recents = Paiement.query.filter_by(statut="confirmé").order_by(
        Paiement.confirmed_at.desc()
    ).limit(7).all()

    # Cotisations par mois (6 derniers mois)
    cotisations_par_mois = db.session.query(
        Paiement.periode,
        func.sum(Paiement.montant_net).label("total"),
        func.count(Paiement.id).label("nombre")
    ).filter(
        Paiement.statut == "confirmé",
        Paiement.type_paiement == "cotisation",
        Paiement.periode.isnot(None)
    ).group_by(Paiement.periode).order_by(Paiement.periode.desc()).limit(6).all()

    return jsonify({
        "membres": {
            "total": total_membres,
            "actifs": membres_actifs,
            "inactifs": total_membres - membres_actifs,
        },
        "groupes": {
            "total": total_groupes,
            "actifs": groupes_actifs,
        },
        "finances": {
            "total_epargne": float(total_epargne),
            "total_commissions": float(total_commissions),
            "encours_prets": float(encours_prets),
            "total_bonus_verses": float(total_bonus_verses),
        },
        "prets": {
            "total": total_prets,
            "en_cours": prets_en_cours,
            "rembourses": prets_rembourses,
        },
        "paiements_recents": [p.to_dict() for p in paiements_recents],
        "cotisations_par_mois": [
            {"periode": r.periode, "total": float(r.total), "nombre": r.nombre}
            for r in cotisations_par_mois
        ],
    }), 200


# ─── LISTE DES MEMBRES ──────────────────────────────────────────────
@admin_bp.route("/membres", methods=["GET"])
@jwt_required()
def liste_membres():
    user_id = int(get_jwt_identity())
    if not verifier_admin(user_id):
        return jsonify({"erreur": "Accès refusé"}), 403

    page = request.args.get("page", 1, type=int)
    par_page = request.args.get("par_page", 20, type=int)
    recherche = request.args.get("q", "")

    query = User.query.filter_by(is_admin=False)
    if recherche:
        query = query.filter(
            db.or_(
                User.nom.ilike(f"%{recherche}%"),
                User.prenom.ilike(f"%{recherche}%"),
                User.telephone.ilike(f"%{recherche}%"),
            )
        )

    membres_page = query.order_by(User.created_at.desc()).paginate(page=page, per_page=par_page, error_out=False)

    return jsonify({
        "membres": [u.to_dict() for u in membres_page.items],
        "total": membres_page.total,
        "pages": membres_page.pages,
        "page_actuelle": page,
    }), 200


# ─── DÉTAIL D'UN MEMBRE ─────────────────────────────────────────────
@admin_bp.route("/membres/<int:membre_id>", methods=["GET"])
@jwt_required()
def detail_membre(membre_id):
    user_id = int(get_jwt_identity())
    if not verifier_admin(user_id):
        return jsonify({"erreur": "Accès refusé"}), 403

    user = User.query.get_or_404(membre_id)
    data = user.to_dict()

    data["groupes"] = [m.groupe.to_dict() for m in user.memberships if m.statut == "actif" and m.groupe]
    data["nb_paiements"] = Paiement.query.filter_by(user_id=membre_id, statut="confirmé").count()
    data["total_cotise"] = float(
        db.session.query(func.sum(Paiement.montant_brut)).filter_by(
            user_id=membre_id, statut="confirmé", type_paiement="cotisation"
        ).scalar() or 0
    )
    data["nb_filleuls"] = User.query.filter_by(parrain_id=membre_id).count()
    data["nb_prets"] = Pret.query.filter_by(emprunteur_id=membre_id).count()

    return jsonify(data), 200


# ─── ACTIVER / DÉSACTIVER UN MEMBRE ─────────────────────────────────
@admin_bp.route("/membres/<int:membre_id>/statut", methods=["PUT"])
@jwt_required()
def changer_statut_membre(membre_id):
    user_id = int(get_jwt_identity())
    if not verifier_admin(user_id):
        return jsonify({"erreur": "Accès refusé"}), 403

    user = User.query.get_or_404(membre_id)
    data = request.get_json()
    user.is_active = data.get("is_active", user.is_active)
    db.session.commit()

    statut = "activé" if user.is_active else "désactivé"
    return jsonify({"message": f"Compte {statut}", "is_active": user.is_active}), 200


# ─── TOUS LES PAIEMENTS ─────────────────────────────────────────────
@admin_bp.route("/paiements", methods=["GET"])
@jwt_required()
def tous_paiements():
    user_id = int(get_jwt_identity())
    if not verifier_admin(user_id):
        return jsonify({"erreur": "Accès refusé"}), 403

    page = request.args.get("page", 1, type=int)
    statut = request.args.get("statut")
    mode = request.args.get("mode")

    query = Paiement.query
    if statut:
        query = query.filter_by(statut=statut)
    if mode:
        query = query.filter_by(mode_paiement=mode)

    paiements_page = query.order_by(Paiement.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    return jsonify({
        "paiements": [p.to_dict() for p in paiements_page.items],
        "total": paiements_page.total,
        "pages": paiements_page.pages,
    }), 200


# ─── VERSER LES BONUS PARRAINAGE ────────────────────────────────────
@admin_bp.route("/bonus/verser", methods=["PUT"])
@jwt_required()
def verser_bonus():
    from datetime import datetime
    user_id = int(get_jwt_identity())
    if not verifier_admin(user_id):
        return jsonify({"erreur": "Accès refusé"}), 403

    bonus_en_attente = BonusParrainage.query.filter_by(statut="en_attente").all()
    for b in bonus_en_attente:
        b.statut = "versé"
        b.versé_at = datetime.utcnow()

        notif = Notification(
            user_id=b.parrain_id,
            titre="Bonus versé 💰",
            message=f"Votre bonus de {b.montant_bonus} FCFA a été versé.",
            type_notif="parrainage"
        )
        db.session.add(notif)

    db.session.commit()
    return jsonify({"message": f"{len(bonus_en_attente)} bonus versés avec succès"}), 200


# ─── EXPORT CSV MEMBRES ─────────────────────────────────────────────
@admin_bp.route("/export/membres", methods=["GET"])
@jwt_required()
def export_membres_csv():
    user_id = int(get_jwt_identity())
    if not verifier_admin(user_id):
        return jsonify({"erreur": "Accès refusé"}), 403

    membres = User.query.filter_by(is_admin=False).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Nom", "Prénom", "Téléphone", "Email", "Actif", "Code Parrainage", "Date Inscription"])
    for u in membres:
        writer.writerow([u.id, u.nom, u.prenom, u.telephone, u.email, u.is_active, u.code_parrainage, u.created_at.strftime("%Y-%m-%d")])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=membres_eepargne.csv"}
    )


# ─── EXPORT CSV PAIEMENTS ───────────────────────────────────────────
@admin_bp.route("/export/paiements", methods=["GET"])
@jwt_required()
def export_paiements_csv():
    user_id = int(get_jwt_identity())
    if not verifier_admin(user_id):
        return jsonify({"erreur": "Accès refusé"}), 403

    paiements = Paiement.query.filter_by(statut="confirmé").order_by(Paiement.confirmed_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Membre ID", "Groupe ID", "Montant Brut", "Commission", "Montant Net", "Mode", "Type", "Période", "Date"])
    for p in paiements:
        writer.writerow([
            p.id, p.user_id, p.groupe_id, p.montant_brut, p.commission,
            p.montant_net, p.mode_paiement, p.type_paiement, p.periode,
            p.confirmed_at.strftime("%Y-%m-%d %H:%M") if p.confirmed_at else ""
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=paiements_eepargne.csv"}
    )


# ─── NOTIFICATIONS ADMIN → TOUS LES MEMBRES ─────────────────────────
@admin_bp.route("/notifier-tous", methods=["POST"])
@jwt_required()
def notifier_tous():
    user_id = int(get_jwt_identity())
    if not verifier_admin(user_id):
        return jsonify({"erreur": "Accès refusé"}), 403

    data = request.get_json()
    titre = data.get("titre", "").strip()
    message = data.get("message", "").strip()
    type_notif = data.get("type_notif", "info")

    if not titre or not message:
        return jsonify({"erreur": "Titre et message obligatoires"}), 400

    membres = User.query.filter_by(is_active=True, is_admin=False).all()
    for u in membres:
        notif = Notification(user_id=u.id, titre=titre, message=message, type_notif=type_notif)
        db.session.add(notif)

    db.session.commit()
    return jsonify({"message": f"Notification envoyée à {len(membres)} membres"}), 200
