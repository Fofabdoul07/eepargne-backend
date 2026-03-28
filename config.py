import os
from datetime import timedelta

class Config:
    # Base
    SECRET_KEY = os.environ.get("SECRET_KEY", "eepargne-secret-key-2026")
    DEBUG = os.environ.get("DEBUG", "False") == "True"

    # Base de données PostgreSQL
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:password@localhost:5432/eepargne_db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "eepargne-jwt-secret-2026")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # Commission (1% par défaut)
    COMMISSION_RATE = float(os.environ.get("COMMISSION_RATE", "0.01"))

    # Bonus parrainage (ex: 2% des parts cotisées par le filleul)
    PARRAINAGE_BONUS_RATE = float(os.environ.get("PARRAINAGE_BONUS_RATE", "0.02"))

    # Compte administrateur principal
    ADMIN_WAVE_NUMBER = os.environ.get("ADMIN_WAVE_NUMBER", "+2250700000001")
    ADMIN_ORANGE_NUMBER = os.environ.get("ADMIN_ORANGE_NUMBER", "+2250700000002")
    ADMIN_MTN_NUMBER = os.environ.get("ADMIN_MTN_NUMBER", "+2250700000003")

    # Mobile Money - Wave
    WAVE_API_KEY = os.environ.get("WAVE_API_KEY", "")
    WAVE_BASE_URL = os.environ.get("WAVE_BASE_URL", "https://api.wave.com/v1")

    # Mobile Money - Orange Money
    ORANGE_CLIENT_ID = os.environ.get("ORANGE_CLIENT_ID", "")
    ORANGE_CLIENT_SECRET = os.environ.get("ORANGE_CLIENT_SECRET", "")
    ORANGE_BASE_URL = os.environ.get("ORANGE_BASE_URL", "https://api.orange.com/orange-money-webpay/ci/v1")

    # Mobile Money - MTN MoMo
    MTN_API_USER = os.environ.get("MTN_API_USER", "")
    MTN_API_KEY = os.environ.get("MTN_API_KEY", "")
    MTN_SUBSCRIPTION_KEY = os.environ.get("MTN_SUBSCRIPTION_KEY", "")
    MTN_BASE_URL = os.environ.get("MTN_BASE_URL", "https://sandbox.momodeveloper.mtn.com")
    MTN_ENVIRONMENT = os.environ.get("MTN_ENVIRONMENT", "sandbox")  # ou "production"

    # Stripe
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

    # OTP (via SMS - ex: Twilio ou Africa's Talking)
    OTP_EXPIRY_MINUTES = 10
    AFRICAS_TALKING_API_KEY = os.environ.get("AFRICAS_TALKING_API_KEY", "")
    AFRICAS_TALKING_USERNAME = os.environ.get("AFRICAS_TALKING_USERNAME", "sandbox")
    SENDER_ID = os.environ.get("SENDER_ID", "E-Epargne")
