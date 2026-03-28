from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app import db
from models import Paiement, Groupe, Membership, BonusParrainage, Notification, User
from config import Config
import requests
import stripe
import uuid

payments_bp = Blueprint("payments", __name__)

stripe.api_key = Config.STRIPE_SECRET_KEY

COMMISSION_RATE = Config.COMMISSION_RATE
PARRAINAGE_BONUS_RATE = Config.PARRAINAGE_BONUS_RATE


def calculer_commission(montant_brut):
    commission = round(float(montant_brut) * COMMISSION_RATE, 2)
    montant_net = round(float(montant_brut) - commission, 2)
    return commission, montant_net


def crediter_bonus_parrainage(user_id, paiement_id, montant_brut):
    """Calcule et enregistre le bonus du parrain après un paiement"""
    user = User.query.get(user_id)
    if user and user.parrain_id:
        montant_bonus = round(float(montant_brut) * PARRAINAGE_BONUS_RATE, 2)
        bonus = BonusParrainage(
            parrain_id=user.parrain_id,
            filleul_id=user_id,
            paiement_id=paiement_id,
            montant_bonus=montant_bonus,
            statut="en_attente"
        )
        db.session.add(bonus)

        notif = Notification(
            user_id=user.parrain_id,
            titre="Bonus parrainage 🎁",
            message=f"Vous avez gagné {montant_bonus} FCFA de bonus grâce à votre filleul.",
            type_notif="parrainage"
        )
        db.session.add(notif)


# ──────────────────────────────────────────────────────────────────────────────
# WAVE
# ──────────────────────────────────────────────────────────────────────────────
def initier_paiement_wave(numero, montant, description):
    """Initie un paiement Wave Checkout"""
    headers = {
        "Authorization": f"Bearer {Config.WAVE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "amount": str(int(montant)),
        "currency": "XOF",
        "error_url": "https://e-epargne.com/paiement/erreur",
        "success_url": "https://e-epargne.com/paiement/succes",
        "client_reference": str(uuid.uuid4()),
    }
    try:
        resp = requests.post(f"{Config.WAVE_BASE_URL}/checkout/sessions", json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[WAVE ERROR] {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# ORANGE MONEY
# ──────────────────────────────────────────────────────────────────────────────
def get_orange_token():
    import base64
    credentials = base64.b64encode(
        f"{Config.ORANGE_CLIENT_ID}:{Config.ORANGE_CLIENT_SECRET}".encode()
    ).decode()
    headers = {"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = requests.post(
            "https://api.orange.com/oauth/v3/token",
            data={"grant_type": "client_credentials"},
            headers=headers, timeout=15
        )
        return resp.json().get("access_token")
    except Exception as e:
        print(f"[ORANGE TOKEN ERROR] {e}")
        return None


def initier_paiement_orange(numero, montant, description):
    token = get_orange_token()
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "merchant_key": Config.ORANGE_CLIENT_ID,
        "currency": "OUV",
        "order_id": str(uuid.uuid4()),
        "amount": int(montant),
        "return_url": "https://e-epargne.com/paiement/succes",
        "cancel_url": "https://e-epargne.com/paiement/erreur",
        "notif_url": "https://e-epargne.com/api/payments/webhook/orange",
        "lang": "fr",
        "reference": description,
    }
    try:
        resp = requests.post(f"{Config.ORANGE_BASE_URL}/webpayment", json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[ORANGE ERROR] {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# MTN MOMO
# ──────────────────────────────────────────────────────────────────────────────
def initier_paiement_mtn(numero, montant, description):
    reference_id = str(uuid.uuid4())
    headers = {
        "Authorization": f"Basic {Config.MTN_API_KEY}",
        "X-Reference-Id": reference_id,
        "X-Target-Environment": Config.MTN_ENVIRONMENT,
        "Ocp-Apim-Subscription-Key": Config.MTN_SUBSCRIPTION_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "amount": str(int(montant)),
        "currency": "XOF",
        "externalId": str(uuid.uuid4()),
        "payer": {"partyIdType": "MSISDN", "partyId": numero.replace("+", "").replace(" ", "")},
        "payerMessage": description,
        "payeeNote": "E-épargne cotisation",
    }
    try:
        resp = requests.post(
            f"{Config.MTN_BASE_URL}/collection/v1_0/requesttopay",
            json=payload, headers=headers, timeout=15
        )
        if resp.status_code == 202:
            return {"reference_id": reference_id, "status": "en_cours"}
        return None
    except Exception as e:
        print(f"[MTN ERROR] {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# STRIPE
# ──────────────────────────────────────────────────────────────────────────────
def initier_paiement_stripe(montant, description, email=None):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "xof",
                    "product_data": {"name": description},
                    "unit_amount": int(montant * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url="https://e-epargne.com/paiement/succes?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://e-epargne.com/paiement/erreur",
            customer_email=email,
        )
        return {"url": session.url, "session_id": session.id}
    except Exception as e:
        print(f"[STRIPE ERROR] {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# ROUTE PRINCIPALE : INITIER UN PAIEMENT
# ──────────────────────────────────────────────────────────────────────────────
@payments_bp.route("/cotisation", methods=["POST"])
@jwt_required()
def payer_cotisation():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    data = request.get_json()

    groupe_id = data.get("groupe_id")
    mode_paiement = data.get("mode_paiement", "").lower()  # wave, orange_money, mtn_momo, stripe
    numero_paiement = data.get("numero_paiement", "")
    cycle = data.get("cycle", None)
    periode = data.get("periode", datetime.utcnow().strftime("%Y-%m"))

    if mode_paiement not in ["wave", "orange_money", "mtn_momo", "stripe"]:
        return jsonify({"erreur": "Mode de paiement invalide"}), 400

    groupe = Groupe.query.get_or_404(groupe_id)
    membership = Membership.query.filter_by(groupe_id=groupe_id, user_id=user_id, statut="actif").first()
    if not membership:
        return jsonify({"erreur": "Vous n'êtes pas membre de ce groupe"}), 403

    montant_brut = float(groupe.montant_part)
    commission, montant_net = calculer_commission(montant_brut)

    # Créer le paiement en attente
    paiement = Paiement(
        user_id=user_id,
        groupe_id=groupe_id,
        montant_brut=montant_brut,
        commission=commission,
        montant_net=montant_net,
        mode_paiement=mode_paiement,
        numero_paiement=numero_paiement,
        statut="en_attente",
        type_paiement="cotisation",
        cycle=cycle,
        periode=periode,
    )
    db.session.add(paiement)
    db.session.flush()

    # Redirection vers l'opérateur
    description = f"Cotisation E-épargne - {groupe.nom} - Cycle {cycle or 'N/A'}"
    response_op = None

    if mode_paiement == "wave":
        response_op = initier_paiement_wave(numero_paiement, montant_brut, description)
    elif mode_paiement == "orange_money":
        response_op = initier_paiement_orange(numero_paiement, montant_brut, description)
    elif mode_paiement == "mtn_momo":
        response_op = initier_paiement_mtn(numero_paiement, montant_brut, description)
    elif mode_paiement == "stripe":
        response_op = initier_paiement_stripe(montant_brut, description, user.email)

    if response_op:
        paiement.transaction_id = response_op.get("reference_id") or response_op.get("session_id") or response_op.get("wave_launch_url", "")[:100]

    db.session.commit()

    return jsonify({
        "message": "Paiement initié",
        "paiement_id": paiement.id,
        "montant_brut": montant_brut,
        "commission": commission,
        "montant_net": montant_net,
        "statut": "en_attente",
        "details_operateur": response_op,
    }), 201


# ──────────────────────────────────────────────────────────────────────────────
# WEBHOOK - Confirmation de paiement (appelé par les opérateurs)
# ──────────────────────────────────────────────────────────────────────────────
@payments_bp.route("/webhook/<operateur>", methods=["POST"])
def webhook_paiement(operateur):
    data = request.get_json() or request.form.to_dict()
    transaction_id = data.get("reference_id") or data.get("transaction_id") or data.get("id")

    paiement = Paiement.query.filter_by(transaction_id=transaction_id).first()
    if not paiement:
        return jsonify({"erreur": "Paiement non trouvé"}), 404

    statut_operateur = data.get("status", "").lower()
    if statut_operateur in ["successful", "success", "completed", "paid"]:
        paiement.statut = "confirmé"
        paiement.confirmed_at = datetime.utcnow()

        # Calculer bonus parrainage
        crediter_bonus_parrainage(paiement.user_id, paiement.id, paiement.montant_brut)

        # Notification membre
        notif = Notification(
            user_id=paiement.user_id,
            titre="Paiement confirmé ✅",
            message=f"Votre cotisation de {paiement.montant_brut} FCFA a été confirmée.",
            type_notif="paiement"
        )
        db.session.add(notif)
        db.session.commit()

    elif statut_operateur in ["failed", "error", "cancelled"]:
        paiement.statut = "échoué"
        db.session.commit()

    return jsonify({"message": "Webhook reçu"}), 200


# ──────────────────────────────────────────────────────────────────────────────
# WEBHOOK STRIPE SPÉCIFIQUE
# ──────────────────────────────────────────────────────────────────────────────
@payments_bp.route("/webhook/stripe", methods=["POST"])
def webhook_stripe():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    endpoint_secret = Config.STRIPE_SECRET_KEY  # mettre le vrai webhook secret ici

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception:
        return jsonify({"erreur": "Signature invalide"}), 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        paiement = Paiement.query.filter_by(transaction_id=session["id"]).first()
        if paiement:
            paiement.statut = "confirmé"
            paiement.confirmed_at = datetime.utcnow()
            crediter_bonus_parrainage(paiement.user_id, paiement.id, paiement.montant_brut)
            db.session.commit()

    return jsonify({"status": "ok"}), 200


# ──────────────────────────────────────────────────────────────────────────────
# HISTORIQUE DES PAIEMENTS
# ──────────────────────────────────────────────────────────────────────────────
@payments_bp.route("/historique", methods=["GET"])
@jwt_required()
def historique_paiements():
    user_id = int(get_jwt_identity())
    paiements = Paiement.query.filter_by(user_id=user_id).order_by(Paiement.created_at.desc()).all()
    return jsonify([p.to_dict() for p in paiements]), 200


# ──────────────────────────────────────────────────────────────────────────────
# CONFIRMER MANUELLEMENT (admin uniquement, pour les tests)
# ──────────────────────────────────────────────────────────────────────────────
@payments_bp.route("/<int:paiement_id>/confirmer", methods=["PUT"])
@jwt_required()
def confirmer_paiement_manuel(paiement_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user.is_admin:
        return jsonify({"erreur": "Accès admin requis"}), 403

    paiement = Paiement.query.get_or_404(paiement_id)
    paiement.statut = "confirmé"
    paiement.confirmed_at = datetime.utcnow()
    crediter_bonus_parrainage(paiement.user_id, paiement.id, paiement.montant_brut)
    db.session.commit()

    return jsonify({"message": "Paiement confirmé manuellement", "paiement": paiement.to_dict()}), 200
