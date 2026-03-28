from app import db
from datetime import datetime
import uuid
import random
import string


def generate_code(prefix="EP", length=8):
    """Génère un code unique (ex: pour parrainage ou groupe)"""
    chars = string.ascii_uppercase + string.digits
    return prefix + "".join(random.choices(chars, k=length))


# ─────────────────────────────────────────────
# UTILISATEUR
# ─────────────────────────────────────────────
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    telephone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # Statut et rôle
    is_active = db.Column(db.Boolean, default=False)   # activé après OTP
    is_admin = db.Column(db.Boolean, default=False)
    telephone_verifie = db.Column(db.Boolean, default=False)

    # Parrainage
    code_parrainage = db.Column(db.String(20), unique=True, default=lambda: generate_code("PAR", 6))
    parrain_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Dates
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    groupes_crees = db.relationship("Groupe", back_populates="createur", foreign_keys="Groupe.createur_id")
    memberships = db.relationship("Membership", back_populates="user")
    paiements = db.relationship("Paiement", back_populates="user")
    prets_demandes = db.relationship("Pret", back_populates="emprunteur", foreign_keys="Pret.emprunteur_id")
    bonus_parrainage = db.relationship("BonusParrainage", back_populates="parrain", foreign_keys="BonusParrainage.parrain_id")
    filleuls = db.relationship("User", foreign_keys=[parrain_id])

    def to_dict(self):
        return {
            "id": self.id,
            "uuid": self.uuid,
            "nom": self.nom,
            "prenom": self.prenom,
            "telephone": self.telephone,
            "email": self.email,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "code_parrainage": self.code_parrainage,
            "parrain_id": self.parrain_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ─────────────────────────────────────────────
# OTP
# ─────────────────────────────────────────────
class OTP(db.Model):
    __tablename__ = "otps"

    id = db.Column(db.Integer, primary_key=True)
    telephone = db.Column(db.String(20), nullable=False)
    code = db.Column(db.String(6), nullable=False)
    expire_at = db.Column(db.DateTime, nullable=False)
    utilise = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# GROUPE (AVEC / AUEC)
# ─────────────────────────────────────────────
class Groupe(db.Model):
    __tablename__ = "groupes"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    nom = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    type_groupe = db.Column(db.String(10), nullable=False)  # "AVEC" ou "AUEC"
    code_groupe = db.Column(db.String(20), unique=True, default=lambda: generate_code("GRP", 6))

    # Configuration financière
    montant_part = db.Column(db.Numeric(12, 2), nullable=False)   # montant d'une part en FCFA
    nombre_membres_max = db.Column(db.Integer, nullable=True)
    periodicite = db.Column(db.String(20), default="mensuel")     # mensuel, hebdomadaire, quotidien
    duree_cycles = db.Column(db.Integer, nullable=True)           # nombre de cycles prévus

    # Statut
    statut = db.Column(db.String(20), default="actif")  # actif, pause, terminé
    is_public = db.Column(db.Boolean, default=False)

    # Dates
    date_debut = db.Column(db.Date, nullable=True)
    date_fin = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Créateur / admin du groupe
    createur_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    createur = db.relationship("User", back_populates="groupes_crees", foreign_keys=[createur_id])

    # Relations
    membres = db.relationship("Membership", back_populates="groupe")
    paiements = db.relationship("Paiement", back_populates="groupe")
    prets = db.relationship("Pret", back_populates="groupe")

    def to_dict(self):
        return {
            "id": self.id,
            "uuid": self.uuid,
            "nom": self.nom,
            "description": self.description,
            "type_groupe": self.type_groupe,
            "code_groupe": self.code_groupe,
            "montant_part": float(self.montant_part),
            "periodicite": self.periodicite,
            "statut": self.statut,
            "nombre_membres": len(self.membres),
            "date_debut": self.date_debut.isoformat() if self.date_debut else None,
            "created_at": self.created_at.isoformat(),
        }


# ─────────────────────────────────────────────
# MEMBERSHIP (Appartenance à un groupe)
# ─────────────────────────────────────────────
class Membership(db.Model):
    __tablename__ = "memberships"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    groupe_id = db.Column(db.Integer, db.ForeignKey("groupes.id"), nullable=False)
    role = db.Column(db.String(20), default="membre")  # membre, admin_groupe, tresorier
    statut = db.Column(db.String(20), default="actif")  # actif, suspendu, sorti
    position_rotation = db.Column(db.Integer, nullable=True)  # position dans la rotation AVEC
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="memberships")
    groupe = db.relationship("Groupe", back_populates="membres")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "groupe_id": self.groupe_id,
            "role": self.role,
            "statut": self.statut,
            "position_rotation": self.position_rotation,
            "joined_at": self.joined_at.isoformat(),
        }


# ─────────────────────────────────────────────
# PAIEMENT / COTISATION
# ─────────────────────────────────────────────
class Paiement(db.Model):
    __tablename__ = "paiements"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    groupe_id = db.Column(db.Integer, db.ForeignKey("groupes.id"), nullable=True)

    # Montants
    montant_brut = db.Column(db.Numeric(12, 2), nullable=False)   # montant avant commission
    commission = db.Column(db.Numeric(12, 2), nullable=False)     # frais prélevés
    montant_net = db.Column(db.Numeric(12, 2), nullable=False)    # montant_brut - commission

    # Mode de paiement
    mode_paiement = db.Column(db.String(30), nullable=False)  # wave, orange_money, mtn_momo, stripe
    numero_paiement = db.Column(db.String(20), nullable=True) # numéro Mobile Money utilisé
    transaction_id = db.Column(db.String(100), nullable=True) # ID retourné par l'opérateur
    statut = db.Column(db.String(20), default="en_attente")   # en_attente, confirmé, échoué, remboursé

    # Type de paiement
    type_paiement = db.Column(db.String(30), default="cotisation")  # cotisation, remboursement_pret, frais

    # Cycle de cotisation
    cycle = db.Column(db.Integer, nullable=True)
    periode = db.Column(db.String(20), nullable=True)  # ex: "2026-03"

    # Dates
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", back_populates="paiements")
    groupe = db.relationship("Groupe", back_populates="paiements")

    def to_dict(self):
        return {
            "id": self.id,
            "uuid": self.uuid,
            "user_id": self.user_id,
            "groupe_id": self.groupe_id,
            "montant_brut": float(self.montant_brut),
            "commission": float(self.commission),
            "montant_net": float(self.montant_net),
            "mode_paiement": self.mode_paiement,
            "numero_paiement": self.numero_paiement,
            "transaction_id": self.transaction_id,
            "statut": self.statut,
            "type_paiement": self.type_paiement,
            "cycle": self.cycle,
            "periode": self.periode,
            "created_at": self.created_at.isoformat(),
        }


# ─────────────────────────────────────────────
# PRÊT
# ─────────────────────────────────────────────
class Pret(db.Model):
    __tablename__ = "prets"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    groupe_id = db.Column(db.Integer, db.ForeignKey("groupes.id"), nullable=False)
    emprunteur_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    valideur_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    montant = db.Column(db.Numeric(12, 2), nullable=False)
    taux_interet = db.Column(db.Numeric(5, 2), default=5.00)     # en pourcentage
    montant_a_rembourser = db.Column(db.Numeric(12, 2), nullable=True)
    montant_rembourse = db.Column(db.Numeric(12, 2), default=0)

    statut = db.Column(db.String(20), default="demande")  # demande, approuvé, refusé, remboursé, en_cours
    motif = db.Column(db.Text, nullable=True)
    date_echeance = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)

    groupe = db.relationship("Groupe", back_populates="prets")
    emprunteur = db.relationship("User", back_populates="prets_demandes", foreign_keys=[emprunteur_id])

    def to_dict(self):
        return {
            "id": self.id,
            "uuid": self.uuid,
            "groupe_id": self.groupe_id,
            "emprunteur_id": self.emprunteur_id,
            "montant": float(self.montant),
            "taux_interet": float(self.taux_interet),
            "montant_a_rembourser": float(self.montant_a_rembourser) if self.montant_a_rembourser else None,
            "montant_rembourse": float(self.montant_rembourse),
            "statut": self.statut,
            "motif": self.motif,
            "date_echeance": self.date_echeance.isoformat() if self.date_echeance else None,
            "created_at": self.created_at.isoformat(),
        }


# ─────────────────────────────────────────────
# BONUS PARRAINAGE
# ─────────────────────────────────────────────
class BonusParrainage(db.Model):
    __tablename__ = "bonus_parrainage"

    id = db.Column(db.Integer, primary_key=True)
    parrain_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    filleul_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    paiement_id = db.Column(db.Integer, db.ForeignKey("paiements.id"), nullable=True)

    montant_bonus = db.Column(db.Numeric(12, 2), nullable=False)
    statut = db.Column(db.String(20), default="en_attente")  # en_attente, versé
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    versé_at = db.Column(db.DateTime, nullable=True)

    parrain = db.relationship("User", back_populates="bonus_parrainage", foreign_keys=[parrain_id])

    def to_dict(self):
        return {
            "id": self.id,
            "parrain_id": self.parrain_id,
            "filleul_id": self.filleul_id,
            "montant_bonus": float(self.montant_bonus),
            "statut": self.statut,
            "created_at": self.created_at.isoformat(),
        }


# ─────────────────────────────────────────────
# NOTIFICATION
# ─────────────────────────────────────────────
class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    titre = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type_notif = db.Column(db.String(30), default="info")  # info, paiement, pret, parrainage, alerte
    lu = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "titre": self.titre,
            "message": self.message,
            "type_notif": self.type_notif,
            "lu": self.lu,
            "created_at": self.created_at.isoformat(),
        }
