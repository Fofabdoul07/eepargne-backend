from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from models import Groupe, Membership, Paiement, Notification, User

groups_bp = Blueprint("groups", __name__)


def verifier_admin_groupe(groupe, user_id):
    m = Membership.query.filter_by(groupe_id=groupe.id, user_id=user_id).first()
    return m and m.role in ["admin_groupe", "tresorier"] or groupe.createur_id == user_id


# ─── CRÉER UN GROUPE ────────────────────────────────────────────────
@groups_bp.route("/", methods=["POST"])
@jwt_required()
def creer_groupe():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    nom = data.get("nom", "").strip()
    type_groupe = data.get("type_groupe", "AVEC").upper()
    montant_part = data.get("montant_part")
    periodicite = data.get("periodicite", "mensuel")
    description = data.get("description", "")
    nombre_membres_max = data.get("nombre_membres_max", None)
    is_public = data.get("is_public", False)
    date_debut = data.get("date_debut", None)
    duree_cycles = data.get("duree_cycles", None)

    if not nom or not montant_part:
        return jsonify({"erreur": "Nom et montant de la part obligatoires"}), 400

    if type_groupe not in ["AVEC", "AUEC"]:
        return jsonify({"erreur": "Type de groupe invalide. Choisir AVEC ou AUEC"}), 400

    groupe = Groupe(
        nom=nom,
        type_groupe=type_groupe,
        montant_part=montant_part,
        periodicite=periodicite,
        description=description,
        nombre_membres_max=nombre_membres_max,
        is_public=is_public,
        duree_cycles=duree_cycles,
        createur_id=user_id,
        date_debut=date_debut,
    )
    db.session.add(groupe)
    db.session.flush()

    # Le créateur est automatiquement membre admin
    membership = Membership(
        user_id=user_id,
        groupe_id=groupe.id,
        role="admin_groupe",
        position_rotation=1,
    )
    db.session.add(membership)
    db.session.commit()

    return jsonify({"message": "Groupe créé", "groupe": groupe.to_dict()}), 201


# ─── MES GROUPES ────────────────────────────────────────────────────
@groups_bp.route("/mes-groupes", methods=["GET"])
@jwt_required()
def mes_groupes():
    user_id = int(get_jwt_identity())
    memberships = Membership.query.filter_by(user_id=user_id, statut="actif").all()
    groupes = [m.groupe.to_dict() for m in memberships if m.groupe]
    return jsonify(groupes), 200


# ─── GROUPES PUBLICS ────────────────────────────────────────────────
@groups_bp.route("/publics", methods=["GET"])
@jwt_required()
def groupes_publics():
    groupes = Groupe.query.filter_by(is_public=True, statut="actif").all()
    return jsonify([g.to_dict() for g in groupes]), 200


# ─── DÉTAIL D'UN GROUPE ─────────────────────────────────────────────
@groups_bp.route("/<int:groupe_id>", methods=["GET"])
@jwt_required()
def detail_groupe(groupe_id):
    user_id = int(get_jwt_identity())
    groupe = Groupe.query.get_or_404(groupe_id)

    # Vérifier que l'utilisateur est membre
    membership = Membership.query.filter_by(groupe_id=groupe_id, user_id=user_id, statut="actif").first()
    if not membership:
        return jsonify({"erreur": "Accès refusé. Vous n'êtes pas membre de ce groupe"}), 403

    data = groupe.to_dict()
    data["membres"] = [
        {
            **m.to_dict(),
            "nom": m.user.nom,
            "prenom": m.user.prenom,
            "telephone": m.user.telephone,
        }
        for m in groupe.membres if m.statut == "actif"
    ]

    # Cotisations du groupe
    cotisations = Paiement.query.filter_by(
        groupe_id=groupe_id, statut="confirmé", type_paiement="cotisation"
    ).all()
    data["total_cotisations"] = float(sum(p.montant_net for p in cotisations))
    data["nombre_cotisations"] = len(cotisations)

    return jsonify(data), 200


# ─── REJOINDRE UN GROUPE (par code) ─────────────────────────────────
@groups_bp.route("/rejoindre", methods=["POST"])
@jwt_required()
def rejoindre_groupe():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    code_groupe = data.get("code_groupe", "").strip().upper()

    groupe = Groupe.query.filter_by(code_groupe=code_groupe).first()
    if not groupe:
        return jsonify({"erreur": "Code de groupe invalide"}), 404

    if groupe.statut != "actif":
        return jsonify({"erreur": "Ce groupe n'accepte plus de nouveaux membres"}), 400

    # Vérifier si déjà membre
    deja_membre = Membership.query.filter_by(user_id=user_id, groupe_id=groupe.id).first()
    if deja_membre:
        return jsonify({"erreur": "Vous êtes déjà membre de ce groupe"}), 409

    # Vérifier limite membres
    if groupe.nombre_membres_max:
        nb_membres = Membership.query.filter_by(groupe_id=groupe.id, statut="actif").count()
        if nb_membres >= groupe.nombre_membres_max:
            return jsonify({"erreur": "Ce groupe a atteint sa capacité maximale"}), 400

    # Position dans la rotation AVEC
    position = Membership.query.filter_by(groupe_id=groupe.id).count() + 1

    membership = Membership(
        user_id=user_id,
        groupe_id=groupe.id,
        role="membre",
        position_rotation=position,
    )
    db.session.add(membership)

    # Notifier le créateur du groupe
    notif = Notification(
        user_id=groupe.createur_id,
        titre="Nouveau membre",
        message=f"Un nouveau membre a rejoint votre groupe '{groupe.nom}'",
        type_notif="info"
    )
    db.session.add(notif)
    db.session.commit()

    return jsonify({"message": f"Vous avez rejoint le groupe '{groupe.nom}'"}), 200


# ─── MODIFIER UN GROUPE ─────────────────────────────────────────────
@groups_bp.route("/<int:groupe_id>", methods=["PUT"])
@jwt_required()
def modifier_groupe(groupe_id):
    user_id = int(get_jwt_identity())
    groupe = Groupe.query.get_or_404(groupe_id)

    if not verifier_admin_groupe(groupe, user_id):
        return jsonify({"erreur": "Accès refusé. Admin groupe requis"}), 403

    data = request.get_json()
    for champ in ["nom", "description", "periodicite", "statut", "is_public", "nombre_membres_max"]:
        if champ in data:
            setattr(groupe, champ, data[champ])

    db.session.commit()
    return jsonify({"message": "Groupe mis à jour", "groupe": groupe.to_dict()}), 200


# ─── EXCLURE UN MEMBRE ──────────────────────────────────────────────
@groups_bp.route("/<int:groupe_id>/membres/<int:membre_id>/exclure", methods=["PUT"])
@jwt_required()
def exclure_membre(groupe_id, membre_id):
    user_id = int(get_jwt_identity())
    groupe = Groupe.query.get_or_404(groupe_id)

    if not verifier_admin_groupe(groupe, user_id):
        return jsonify({"erreur": "Accès refusé"}), 403

    membership = Membership.query.filter_by(groupe_id=groupe_id, user_id=membre_id).first()
    if not membership:
        return jsonify({"erreur": "Membre non trouvé"}), 404

    membership.statut = "sorti"
    db.session.commit()
    return jsonify({"message": "Membre exclu du groupe"}), 200


# ─── COTISATIONS DU GROUPE PAR PÉRIODE ──────────────────────────────
@groups_bp.route("/<int:groupe_id>/cotisations", methods=["GET"])
@jwt_required()
def cotisations_groupe(groupe_id):
    user_id = int(get_jwt_identity())
    membership = Membership.query.filter_by(groupe_id=groupe_id, user_id=user_id, statut="actif").first()
    if not membership:
        return jsonify({"erreur": "Accès refusé"}), 403

    periode = request.args.get("periode")  # ex: "2026-03"
    query = Paiement.query.filter_by(groupe_id=groupe_id, type_paiement="cotisation", statut="confirmé")
    if periode:
        query = query.filter_by(periode=periode)

    paiements = query.all()
    return jsonify([p.to_dict() for p in paiements]), 200
