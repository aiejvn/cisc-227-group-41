from datetime import date

from flask import Blueprint, redirect, render_template, request, url_for

from app import store
from app.models.equipment import Equipment
from app.models.renter import Renter
from app.models.rental import Rental

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
def home():
    return render_template("home.html")


@views_bp.route("/ui/equipment", methods=["GET", "POST"])
def equipment_page():
    if request.method == "POST":
        total_units = int(request.form["total_units"])
        equipment_id = store.next_id("equipment")
        item = Equipment(
            id=equipment_id,
            name=request.form["name"],
            category=request.form["category"],
            total_units=total_units,
            available_units=total_units,
        )
        store.equipment[equipment_id] = item
        return redirect(url_for("views.equipment_page"))
    return render_equipment_page()


def render_equipment_page(error=None, notice=None, status=200):
    categories = sorted({item.category for item in store.equipment.values()})
    return render_template(
        "equipment.html",
        equipment=store.equipment.values(),
        categories=categories,
        error=error,
        notice=notice,
    ), status


@views_bp.route("/ui/equipment/<int:equipment_id>/deposit", methods=["POST"])
def set_deposit_flag_page(equipment_id):
    item = store.equipment.get(equipment_id)
    if item is None:
        return redirect(url_for("views.equipment_page"))
    needs_deposit = request.form.get("needs_deposit")
    if needs_deposit not in ("true", "false"):
        return render_equipment_page(error="Choose whether a deposit is required", status=400)
    if not item.set_deposit_flag(needs_deposit == "true"):
        return render_equipment_page(
            error=f"The deposit requirement for {item.name} can't change while units are rented out",
            status=409,
        )
    return redirect(url_for("views.equipment_page"))


@views_bp.route("/ui/equipment/deposit/bulk", methods=["POST"])
def bulk_set_deposit_flag_page():
    category = request.form.get("category", "")
    needs_deposit = request.form.get("needs_deposit")
    if not category.strip() or needs_deposit not in ("true", "false"):
        return render_equipment_page(error="Choose a category and whether a deposit is required", status=400)

    updated, skipped = [], []
    for item in store.equipment.values():
        if item.category != category:
            continue
        if item.set_deposit_flag(needs_deposit == "true"):
            updated.append(item)
        else:
            skipped.append(item)

    if not updated and not skipped:
        notice = f"No equipment found in category {category}"
    else:
        notice = f"Updated {len(updated)} item(s) in {category}."
        if skipped:
            names = ", ".join(item.name for item in skipped)
            notice += f" Skipped {len(skipped)} because units are rented out: {names}."
    return render_equipment_page(notice=notice)

@views_bp.route("/ui/equipment/<int:equipment_id>/status", methods=["POST"])
def set_equipment_status_page(equipment_id):
    """ Toggle whether a piece of equipment is available or out of service.
    """

    item = store.equipment.get(equipment_id)

    if item is None:
        return redirect(url_for("views.equipment_page"))

    is_available = request.form.get("is_available")

    if is_available not in ("true", "false"):
        return render_equipment_page(error = "Choose whether the equipment is in service", status = 400,)

    item.is_available = (is_available == "true")
    return redirect(url_for("views.equipment_page"))

@views_bp.route("/ui/equipment/<int:equipment_id>/delete", methods=["POST"])
def delete_equipment_page(equipment_id):
    store.equipment.pop(equipment_id, None)
    return redirect(url_for("views.equipment_page"))


@views_bp.route("/ui/renters", methods=["GET", "POST"])
def renters_page():
    if request.method == "POST":
        renter_id = store.next_id("renter")
        renter = Renter(id=renter_id, name=request.form["name"], email=request.form["email"])
        store.renters[renter_id] = renter
        return redirect(url_for("views.renters_page"))
    return render_template("renters.html", renters=store.renters.values())


@views_bp.route("/ui/renters/<int:renter_id>/delete", methods=["POST"])
def delete_renter_page(renter_id):
    store.renters.pop(renter_id, None)
    return redirect(url_for("views.renters_page"))


@views_bp.route("/ui/rentals", methods=["GET", "POST"])
def rentals_page():
    if request.method == "POST":
        equipment_id = int(request.form["equipment_id"])
        renter_id = int(request.form["renter_id"])
        item = store.equipment.get(equipment_id)
        if item is not None:
            # Prevent checkout of equipment that is out of service
            if not item.is_available:
                return render_template(
                    "rentals.html", 
                    rentals = store.rentals.values(),
                    error = "This equipment is out of service and cannot be rented",
                ), 409
            try:
                deposit_amount = float(request.form.get("deposit_amount") or 0.0)
            except ValueError:
                deposit_amount = None  # not a number; flagged items will reject it
            problem = item.deposit_problem(deposit_amount)
            if problem is not None:
                return render_template("rentals.html", rentals=store.rentals.values(), error=problem), 400
            item.available_units -= 1
            rental_id = store.next_id("rental")
            rental = Rental(
                id=rental_id,
                equipment_id=equipment_id,
                renter_id=renter_id,
                due_date=Rental.default_due_date(),
                deposit_amount=deposit_amount if deposit_amount is not None else 0.0,
            )
            store.rentals[rental_id] = rental
        return redirect(url_for("views.rentals_page"))
    return render_template("rentals.html", rentals=store.rentals.values())


@views_bp.route("/ui/rentals/<int:rental_id>/return", methods=["POST"])
def return_rental_page(rental_id):
    rental = store.rentals.get(rental_id)
    if rental is not None and rental.return_date is None:
        rental.return_date = date.today()
        item = store.equipment.get(rental.equipment_id)
        if item is not None:
            item.available_units += 1
    return redirect(url_for("views.rentals_page"))
