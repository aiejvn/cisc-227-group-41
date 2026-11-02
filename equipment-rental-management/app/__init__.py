from flask import Flask


def create_app():
    app = Flask(__name__)

    from app.routes.equipment import equipment_bp
    from app.routes.renters import renters_bp
    from app.routes.rentals import rentals_bp
    from app.routes.views import views_bp

    app.register_blueprint(equipment_bp)
    app.register_blueprint(renters_bp)
    app.register_blueprint(rentals_bp)
    app.register_blueprint(views_bp)

    return app
