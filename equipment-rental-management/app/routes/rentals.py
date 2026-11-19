import logging
import threading
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

import notification_service
from app import store
from app.models.rental import Rental

logger = logging.getLogger(__name__)

rentals_bp = Blueprint("rentals", __name__, url_prefix="/rentals")

REMINDER_INTERVAL_SECONDS = 24 * 60 * 60


def build_return_reminder(rental):
    """Return (recipient, subject, message) for a well-formed rental."""
    renter = store.renters[rental.renter_id]
    item = store.equipment[rental.equipment_id]
    subject = f"Reminder: please return {item.name} today"
    message = (
        f"Hi {renter.name}, this is a friendly reminder that your rental of "
        f"{item.name} (rental #{rental.id}) is due back today, "
        f"{rental.due_date.isoformat()}. Thank you!"
    )
    return renter.email, subject, message


def reminder_problem(rental):
    """Return why a rental can't get a reminder, or None if it is well formed."""
    renter = store.renters.get(rental.renter_id)
    if renter is None:
        return f"Renter #{rental.renter_id} does not exist"
    
    if not isinstance(renter.email, str) or not renter.email.strip():
        return f"Renter #{renter.id} ({renter.name}) has no email address"
    
    if store.equipment.get(rental.equipment_id) is None:
        return f"Equipment #{rental.equipment_id} does not exist"
    
    return None


def send_due_reminders(today=None):
    """Send a return reminder for every unreturned rental due today.

    Returned rentals are skipped. A malformed rental is logged and posted to
    store.reminder_warnings for the rentals page. A failed send is logged and
    the loop continues. 
    
    Returns the ids of rentals that were reminded.
    """
    today = today or date.today()
    reminded = []
    for rental in list(store.rentals.values()):
        if rental.return_date is not None or rental.due_date != today:
            continue

        problem = reminder_problem(rental)
        if problem is not None:
            warning = f"Rental #{rental.id} could not be reminded: {problem}"
            logger.warning(warning)
            store.reminder_warnings[rental.id] = warning
            continue

        if notification_service.send_notification(*build_return_reminder(rental)):
            reminded.append(rental.id)
        else:
            logger.error("Return reminder for rental #%s failed to send", rental.id)
    return reminded


def start_reminder_timer():
    """Run the reminder check now, then every 24 hours, on a daemon thread.

    Called once from the entry point (run.py), never on import, so tests and
    other importers don't start a timer.
    """
    send_due_reminders()
    timer = threading.Timer(REMINDER_INTERVAL_SECONDS, start_reminder_timer)
    timer.daemon = True
    timer.start()
    return timer


@rentals_bp.route("", methods=["GET"])
def list_rentals():
    results = list(store.rentals.values())
    renter_id = request.args.get("renter_id", type=int)
    equipment_id = request.args.get("equipment_id", type=int)
    if renter_id is not None:
        results = [r for r in results if r.equipment_id == renter_id]
    if equipment_id is not None:
        results = [r for r in results if r.equipment_id == equipment_id]
    return jsonify([r.to_dict() for r in results])


@rentals_bp.route("", methods=["POST"])
def checkout_equipment():
    data = request.get_json()
    item = store.equipment.get(data["equipment_id"])
    
    if item is None:
        return jsonify({"error": "Equipment not found"}), 404

    # Prevent equipment checkout if it is out of service
    if not item.is_available:
        return jsonify({"error": "Equipment is out of service and cannot be rented"}), 409
    
    deposit_amount = data.get("deposit_amount", 0.0)
    
    # Must run before available_units changes so a rejected checkout leaves no trace
    problem = item.deposit_problem(deposit_amount)
    if problem is not None:
        return jsonify({"error": problem}), 400
    
    item.available_units -= 1

    rental_id = store.next_id("rental")
    rental = Rental(
        id=rental_id,
        equipment_id=data["equipment_id"],
        renter_id=data["renter_id"],
        due_date=Rental.default_due_date(),
        deposit_amount=deposit_amount,
    )
    
    store.rentals[rental_id] = rental
    return jsonify(rental.to_dict()), 201


@rentals_bp.route("/<int:rental_id>/return", methods=["PUT"])
def return_equipment(rental_id):
    rental = store.rentals.get(rental_id)
    if rental is None:
        return jsonify({"error": "Rental not found"}), 404
    if rental.return_date is not None:
        return jsonify({"error": "Rental already returned"}), 400

    rental.return_date = date.today()
    item = store.equipment.get(rental.equipment_id)
    if item is not None:
        item.available_units += 1

    return jsonify(rental.to_dict())


@rentals_bp.route("/<int:rental_id>/extend", methods=["PUT"])
def extend_rental(rental_id):
    """Extend a rental's due date by the given number of days."""
    rental = store.rentals.get(rental_id)
    if rental is None:
        return jsonify({"error": "Rental not found"}), 404
    if rental.return_date is not None:
        return jsonify({"error": "Rental already returned"}), 400

    data = request.get_json()
    days = data.get("days", 1)
    rental.due_date = rental.due_date + timedelta(days=days)
    return jsonify(rental.to_dict())


@rentals_bp.route("/<int:rental_id>/deposit/release", methods=["PUT"])
def release_deposit(rental_id):
    """Release the damage deposit hold for a returned rental.

    BUG: this endpoint returns {"deposit_released": true} in the response
    but does NOT persist the change on the rental object. A subsequent GET
    on the rental will still show deposit_released as false. The missing line
    is:
        rental.deposit_released = True
    """
    rental = store.rentals.get(rental_id)
    if rental is None:
        return jsonify({"error": "Rental not found"}), 404
    if rental.return_date is None:
        return jsonify({"error": "Equipment has not been returned yet"}), 400

    # BUG: rental.deposit_released is never set to True here — state is not persisted.
    return jsonify({"rental_id": rental_id, "deposit_released": True})
