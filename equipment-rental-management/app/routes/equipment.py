from flask import Blueprint, jsonify, request

from app import store
from app.models.equipment import Equipment

equipment_bp = Blueprint("equipment", __name__, url_prefix="/equipment")


@equipment_bp.route("", methods=["GET"])
def list_equipment():
    return jsonify([e.to_dict() for e in store.equipment.values()])


@equipment_bp.route("", methods=["POST"])
def create_equipment():
    data = request.get_json()
    equipment_id = store.next_id("equipment")
    item = Equipment(
        id=equipment_id,
        name=data["name"],
        category=data["category"],
        total_units=data.get("total_units", 1),
        available_units=data.get("total_units", 1),
        is_available=data.get("is_available", True),
    )
    store.equipment[equipment_id] = item
    return jsonify(item.to_dict()), 201


@equipment_bp.route("/<int:equipment_id>", methods=["GET"])
def get_equipment(equipment_id):
    item = store.equipment.get(equipment_id)
    if item is None:
        return jsonify({"error": "Equipment not found"}), 404
    return jsonify(item.to_dict())


@equipment_bp.route("/<int:equipment_id>", methods=["PUT"])
def update_equipment(equipment_id):
    item = store.equipment.get(equipment_id)
    if item is None:
        return jsonify({"error": "Equipment not found"}), 404
    data = request.get_json()
    item.name = data.get("name", item.name)
    item.category = data.get("category", item.category)
    item.total_units = data.get("total_units", item.total_units)
    item.available_units = data.get("available_units", item.available_units)
    item.is_available = data.get("is_available", item.is_available)
    return jsonify(item.to_dict())


@equipment_bp.route("/<int:equipment_id>", methods=["DELETE"])
def delete_equipment(equipment_id):
    item = store.equipment.pop(equipment_id, None)
    if item is None:
        return jsonify({"error": "Equipment not found"}), 404
    return "", 204


@equipment_bp.route("/<int:equipment_id>/status", methods=["PATCH"])
def set_equipment_status(equipment_id):
    """Mark equipment as available or out-of-service (e.g. under repair).

    Set is_available=false to take a piece of equipment out of service.

    NOTE (intentional bug): checkout_equipment() in rentals.py does NOT check
    this flag. Out-of-service equipment can still be checked out — a test that
    marks equipment unavailable and then attempts a checkout will reveal this.
    """
    
    item = store.equipment.get(equipment_id)
    if item is None:
        return jsonify({"error": "Equipment not found"}), 404
    
    data = request.get_json(silent = True)
    
    # Only accepts Boolean values
    if not isinstance(data, dict) or not isinstance(data.get("is_avialable"), bool):
        return jsonify({"error": "is_available must be True or False"}), 400
    
    item.is_available = data["is_available"]
    return jsonify(item.to_dict()), 200


@equipment_bp.route("/<int:equipment_id>/deposit", methods=["PATCH"])
def set_equipment_deposit_flag(equipment_id):
    """Set whether renting this equipment requires a deposit.

    Rejected with 409 while any unit is rented out, so a rental in progress
    never changes whether it needed a deposit.
    """
    item = store.equipment.get(equipment_id)
    if item is None:
        return jsonify({"error": "Equipment not found"}), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("needs_deposit"), bool):
        return jsonify({"error": "needs_deposit must be true or false"}), 400
    if not item.set_deposit_flag(data["needs_deposit"]):
        return jsonify({"error": "Deposit requirement can't change while units are rented out"}), 409
    return jsonify(item.to_dict())


@equipment_bp.route("/deposit/bulk", methods=["POST"])
def bulk_set_deposit_flag():
    """Set the deposit requirement on every item in a category.

    Items with units rented out are locked: they are skipped, not changed, and
    their ids are returned in "skipped" so the caller can tell the user.
    """
    data = request.get_json(silent=True)
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("category"), str)
        or not data["category"].strip()
        or not isinstance(data.get("needs_deposit"), bool)
    ):
        return jsonify({"error": "category must be a non-empty string and needs_deposit must be true or false"}), 400

    updated, skipped = [], []
    for item in store.equipment.values():
        if item.category != data["category"]:
            continue
        if item.set_deposit_flag(data["needs_deposit"]):
            updated.append(item.id)
        else:
            skipped.append(item.id)
    return jsonify({"updated": updated, "skipped": skipped})


@equipment_bp.route("/<int:equipment_id>/availability", methods=["GET"])
def get_availability(equipment_id):
    """Return availability summary for a single piece of equipment."""
    item = store.equipment.get(equipment_id)
    if item is None:
        return jsonify({"error": "Equipment not found"}), 404
    return jsonify({
        "equipment_id": item.id,
        "is_available": item.is_available,
        "available_units": item.available_units,
        "total_units": item.total_units,
    })
