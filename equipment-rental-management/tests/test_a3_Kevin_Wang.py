"""Member A work allocaiton:
    - Happy-path tests for the daily equipment return reminder
    - Additional tests for app/ to achieve >= 90% line coverage

send_notification is mocked where the app uses it (app.routes.rentals) so the
test can check the exact recipient, subject, and message. test_notification_storage
sends a mock notification through the real notification service and checks that
get_notifications() stores it, clearing it before and after.
"""
from datetime import date, timedelta
from unittest.mock import patch

import pytest

import notification_service
from app import store
from app.models.equipment import Equipment
from app.models.rental import Rental
from app.models.renter import Renter
from app.routes import rentals as rentals_module
from app.routes.rentals import (
    build_return_reminder,
    reminder_problem,
    send_due_reminders,
    start_reminder_timer,
)

TODAY = date(2026, 11, 15)
SEND = "app.routes.rentals.notification_service.send_notification"

EXPECTED_RECIPIENT = "alice@example.com"
EXPECTED_SUBJECT = "Reminder: please return Canoe today"
EXPECTED_MESSAGE = (
    "Hi Alice, this is a friendly reminder that your rental of Canoe "
    "(rental #1) is due back today, 2026-11-15. Thank you!"
)


def add_well_formed_rental(due_date=TODAY):
    """Add renter #1 (Alice), equipment #1 (Canoe), and unreturned rental #1."""
    store.renters[1] = Renter(id=1, name="Alice", email=EXPECTED_RECIPIENT)
    store.equipment[1] = Equipment(id=1, name="Canoe", category="Tools",
                                   total_units=3, available_units=2)
    store.rentals[1] = Rental(id=1, equipment_id=1, renter_id=1, due_date=due_date,
                              rental_date=due_date - timedelta(days=7))


@pytest.fixture(autouse=True)
def clean_state(client):
    """The client fixture resets the store. Isolates the real notification service."""
    notification_service.clear_notifications()
    yield
    notification_service.clear_notifications()


def test_build_return_reminder_content():
    add_well_formed_rental()
    assert build_return_reminder(store.rentals[1]) == (
        EXPECTED_RECIPIENT, EXPECTED_SUBJECT, EXPECTED_MESSAGE,
    )


def test_reminder_problem_none_for_well_formed_rental():
    add_well_formed_rental()
    assert reminder_problem(store.rentals[1]) is None


def test_start_reminder_timer_runs_now_and_schedules_daemon():
    with patch.object(rentals_module, "send_due_reminders") as mock_check, \
         patch.object(rentals_module.threading, "Timer") as mock_timer:
        start_reminder_timer()
    mock_check.assert_called_once_with()
    mock_timer.assert_called_once_with(24 * 60 * 60, start_reminder_timer)
    assert mock_timer.return_value.daemon is True
    mock_timer.return_value.start.assert_called_once_with()


def test_sends_reminder_to_renter_with_expected_fields():
    add_well_formed_rental()
    with patch(SEND, return_value=True) as mock_send:
        assert send_due_reminders(TODAY) == [1]
    mock_send.assert_called_once_with(EXPECTED_RECIPIENT, EXPECTED_SUBJECT, EXPECTED_MESSAGE)
    assert store.reminder_warnings == {}


def test_defaults_to_todays_date():
    add_well_formed_rental(due_date=date.today())
    with patch(SEND, return_value=True) as mock_send:
        assert send_due_reminders() == [1]
    mock_send.assert_called_once()


def test_notification_storage():
    test_notification = {
        "recipient": "bob@example.com",
        "subject": "Test subject",
        "message": "Test message",
    }
    assert notification_service.send_notification(**test_notification) is True
    assert notification_service.get_notifications() == [test_notification]


# ============= Web UI routes (app/routes/views.py) =============
# Tested using white-box decision coverage. 
# Each test name states which decision it tests and to which outcome (T/F).


def add_equipment(id=1, total_units=2, available_units=2, is_available=True, needs_deposit=False):
    store.equipment[id] = Equipment(id=id, name="Canoe", category="Boating",
                                    total_units=total_units, available_units=available_units,
                                    is_available=is_available, needs_deposit=needs_deposit)
    return store.equipment[id]


def add_renter(id=1):
    store.renters[id] = Renter(id=id, name="Alice", email=EXPECTED_RECIPIENT)
    return store.renters[id]


def add_rental(id=1, equipment_id=1, return_date=None):
    store.rentals[id] = Rental(id=id, equipment_id=equipment_id, renter_id=1,
                               due_date=date.today() + timedelta(days=7), return_date=return_date)
    return store.rentals[id]


# ---- equipment_page decision: `request.method == "POST"` (views.py:20) ----

def test_equipment_page_post_true_creates_equipment(client):
    response = client.post("/ui/equipment",
                           data={"name": "Kayak", "category": "Boating", "total_units": "4"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/ui/equipment")
    assert len(store.equipment) == 1
    item = next(iter(store.equipment.values()))
    assert (item.name, item.category, item.total_units, item.available_units) == ("Kayak", "Boating", 4, 4)


def test_equipment_page_post_false_renders_list(client):
    add_equipment()
    response = client.get("/ui/equipment")
    assert response.status_code == 200
    assert b"Canoe" in response.data


# ---- set_equipment_status_page decisions: `item is None` (views.py:94), `is_available not in (...)` (views.py:99) ----

def test_set_status_item_none_true_redirects(client):
    response = client.post("/ui/equipment/999/status", data={"is_available": "false"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/ui/equipment")
    assert store.equipment == {}


@pytest.mark.parametrize("form", [{"is_available": "maybe"}, {}])
def test_set_status_invalid_value_true_returns_400(client, form):
    item = add_equipment()
    response = client.post("/ui/equipment/1/status", data=form)
    assert response.status_code == 400
    assert b"Choose whether the equipment is in service" in response.data
    assert item.is_available is True


def test_set_status_invalid_value_false_toggles_flag(client):
    item = add_equipment()
    response = client.post("/ui/equipment/1/status", data={"is_available": "false"})
    assert response.status_code == 302
    assert item.is_available is False
    response = client.post("/ui/equipment/1/status", data={"is_available": "true"})
    assert response.status_code == 302
    assert item.is_available is True


# ---- delete_equipment_page - no decisions ----

def test_delete_equipment_removes_item(client):
    add_equipment(id=1)
    add_equipment(id=2)
    response = client.post("/ui/equipment/1/delete")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/ui/equipment")
    assert list(store.equipment) == [2]


def test_delete_equipment_missing_id_is_noop(client):
    add_equipment(id=1)
    response = client.post("/ui/equipment/999/delete")
    assert response.status_code == 302
    assert list(store.equipment) == [1]


# ---- delete_renter_page - no decisions ----

def test_delete_renter_removes_renter(client):
    add_renter(id=1)
    add_renter(id=2)
    response = client.post("/ui/renters/1/delete")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/ui/renters")
    assert list(store.renters) == [2]


def test_delete_renter_missing_id_is_noop(client):
    add_renter(id=1)
    response = client.post("/ui/renters/999/delete")
    assert response.status_code == 302
    assert list(store.renters) == [1]


# ---- rentals_page decisions: `POST` (views.py:129), `item is not None` (views.py:133), `not item.is_available` (views.py:135), float() ValueError (views.py:143-144), `problem is not None` (views.py:147), `deposit_amount is not None` (views.py:159) ----
# The `deposit_amount is not None` ternary can only be True: a None deposit is always
# rejected by deposit_problem() before that line, so its False branch is unreachable.

def checkout(client, deposit=""):
    return client.post("/ui/rentals", data={"equipment_id": "1", "renter_id": "1",
                                            "deposit_amount": deposit})


def test_rentals_page_post_false_renders_page(client):
    response = client.get("/ui/rentals")
    assert response.status_code == 200


def test_rentals_page_item_exists_false_redirects_without_rental(client):
    add_renter()
    response = checkout(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/ui/rentals")
    assert store.rentals == {}


def test_rentals_page_out_of_service_true_returns_409(client):
    add_renter()
    item = add_equipment(is_available=False)
    response = checkout(client)
    assert response.status_code == 409
    assert b"out of service" in response.data
    assert store.rentals == {}
    assert item.available_units == 2


def test_rentals_page_deposit_not_a_number_raises_value_error(client):
    add_renter()
    item = add_equipment(needs_deposit=True)
    response = checkout(client, deposit="abc")
    assert response.status_code == 400
    assert b"requires a deposit greater than 0" in response.data
    assert store.rentals == {}
    assert item.available_units == 2


def test_rentals_page_deposit_problem_true_returns_400(client):
    add_renter()
    item = add_equipment(needs_deposit=False)
    response = checkout(client, deposit="25")
    assert response.status_code == 400
    assert b"take a deposit" in response.data
    assert store.rentals == {}
    assert item.available_units == 2


def test_rentals_page_valid_checkout_creates_rental(client):
    # in service (F), float() succeeds (no ValueError), problem is None (F), ternary True
    add_renter()
    item = add_equipment(needs_deposit=True)
    response = checkout(client, deposit="25.5")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/ui/rentals")
    assert item.available_units == 1
    [rental] = store.rentals.values()
    assert (rental.equipment_id, rental.renter_id, rental.deposit_amount) == (1, 1, 25.5)
    assert rental.return_date is None
    assert rental.due_date == Rental.default_due_date()


# ---- return_rental_page decisions: `rental is not None and rental.return_date is None` (views.py:171), `item is not None` (views.py:174) ----

def test_return_rental_true_with_item_marks_returned(client):
    item = add_equipment(available_units=1)
    rental = add_rental()
    response = client.post("/ui/rentals/1/return")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/ui/rentals")
    assert rental.return_date == date.today()
    assert item.available_units == 2


def test_return_rental_false_unknown_rental(client):
    item = add_equipment(available_units=1)
    response = client.post("/ui/rentals/999/return")
    assert response.status_code == 302
    assert item.available_units == 1


def test_return_rental_false_already_returned(client):
    item = add_equipment(available_units=2)
    earlier = date.today() - timedelta(days=1)
    rental = add_rental(return_date=earlier)
    response = client.post("/ui/rentals/1/return")
    assert response.status_code == 302
    assert rental.return_date == earlier
    assert item.available_units == 2


def test_return_rental_item_missing_still_returns(client):
    rental = add_rental(equipment_id=999)
    response = client.post("/ui/rentals/1/return")
    assert response.status_code == 302
    assert rental.return_date == date.today()
