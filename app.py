from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from config import Config

db = SQLAlchemy()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    jwt.init_app(app)
    CORS(app, origins=["*"])

    from auth import auth_bp
    from groups import groups_bp
    from payments import payments_bp
    from loans import loans_bp
    from parrainage import parrainage_bp
    from admin import admin_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(groups_bp, url_prefix="/api/groups")
    app.register_blueprint(payments_bp, url_prefix="/api/payments")
    app.register_blueprint(loans_bp, url_prefix="/api/loans")
    app.register_blueprint(parrainage_bp, url_prefix="/api/parrainage")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    with app.app_context():
        db.create_all()

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
