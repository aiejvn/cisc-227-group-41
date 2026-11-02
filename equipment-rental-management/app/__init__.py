import os

from flask import Flask


def create_app():
    app = Flask(__name__)
    # Needed for flash messages. The fallback is for local development only.
    app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

    from app.routes.equipment import equipment_bp
    from app.routes.renters import renters_bp
    from app.routes.rentals import rentals_bp
    from app.routes.views import views_bp

    app.register_blueprint(equipment_bp)
    app.register_blueprint(renters_bp)
    app.register_blueprint(rentals_bp)
    app.register_blueprint(views_bp)

    return app
