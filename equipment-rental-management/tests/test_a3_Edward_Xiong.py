""""Member B work allocations:

Part 1 - Notification tests (failure and non-trigger paths) for the daily equiment return reminder 
in app/routes/rentals.py and the warning dismiss route in app/routes/views.py:
    - send_notification is stubbed to return False, or the real simulator is
    put into an outage, and the app's response and state are checked
    - send_notification is mocked (assert_not_called) when the reminder
    conditions are not met
    - send_notification is patched where the app uses it, following the
    same target as Member A's tests.

Part 2 - Coverage-directed tests for app/routes/rentals.py:
    list_rentals()      - renter_id / equipment_id filters
    return_equipment()  - "already returned" branch
    extend_rental()     - default and custom extension, 404, 400
    release_deposit()   - 404, 400 and success branches

Tests marked 'xfail' document real defects in the application (explained in the
reason string and in the report). They are kept, not deleted, so the defect
stays visible and CI can still pass.
"""

import logging
from datetime import date, timedelta
from unittest.mock import patch

import pytest

import notification_service
from app import store
from app.models.equipment import Equipment
from app.models.rental import Rental
from app.models.renter import Renter
from app.routes.rentals import reminder_problem, send_due_reminders

SEND = "app.routes.rentals.notification_service.send_notification"
TODAY = date(2026, 11, 15)


@pytest.fixture(autouse=True)
def clean_notifications(client):
    """The client fixture resets the store; also isolate the real simulator."""
    notification_service.clear_notifications()
    yield
    notification_service.clear_notifications()
    
# ================== Part 1: reminder helpers (store setup) ==================

def add_reminder_rental(rental_id=1, due_date=TODAY, return_date=None,
                        renter_name="Alice", email="alice@example.com",
                        with_renter=True, with_equipment=True):
    """Add one unreturned rental (and, optionally, its renter and equipment)
    directly to the store. ids are shared so rental #n uses renter #n and
    equipment #n."""
    if with_renter:
        store.renters[rental_id] = Renter(id=rental_id, name=renter_name, email=email)
    if with_equipment:
        store.equipment[rental_id] = Equipment(
            id=rental_id, name="Canoe", category="Tools", total_units=3, available_units=2
        )
    store.rentals[rental_id] = Rental(
        id=rental_id, equipment_id=rental_id, renter_id=rental_id, due_date=due_date,
        rental_date=due_date - timedelta(days=7), return_date=return_date,
    )
    return store.rentals[rental_id]


# ===================== Part 1: failed notification =====================

def test_failed_send_is_not_reported_and_rental_is_unchanged():
    """Stub: send_notification fails. The rental is not reported as reminded
    and the rental and equipment records are left untouched."""
    rental = add_reminder_rental()
    with patch(SEND, return_value=False) as stub:
        result = send_due_reminders(TODAY)

    assert result == []
    stub.assert_called_once()
    assert rental.return_date is None
    assert store.rentals[1] is rental
    assert store.equipment[1].available_units == 2


def test_failed_send_is_logged(caplog):
    """A failed send is logged and does not raise."""
    add_reminder_rental()
    caplog.set_level(logging.INFO)
    with patch(SEND, return_value=False):
        result = send_due_reminders(TODAY)

    assert result == []
    assert caplog.records  # the failure was logged


def test_failed_send_does_not_stop_later_rentals():
    """The first reminder fails and the second succeeds: the second rental is
    still reminded and only it is reported."""
    add_reminder_rental(rental_id=1, email="alice@example.com", renter_name="Alice")
    add_reminder_rental(rental_id=2, email="bob@example.com", renter_name="Bob")
    with patch(SEND, side_effect=[False, True]) as mock_send:
        result = send_due_reminders(TODAY)

    assert result == [2]
    assert mock_send.call_count == 2
    assert mock_send.call_args_list[0].args[0] == "alice@example.com"
    assert mock_send.call_args_list[1].args[0] == "bob@example.com"


def test_service_outage_records_nothing_and_reports_no_reminders():
    """Real simulator with is_service_available stubbed to False: nothing is
    recorded and no rental is reported as reminded."""
    add_reminder_rental()
    with patch("notification_service.is_service_available", return_value=False):
        result = send_due_reminders(TODAY)

    assert result == []
    assert notification_service.get_notifications() == []


# ============== Part 1: non-trigger paths (no call is made) ==============

def test_no_reminder_for_returned_rental():
    add_reminder_rental(return_date=TODAY - timedelta(days=1))
    with patch(SEND) as mock_send:
        result = send_due_reminders(TODAY)

    assert result == []
    mock_send.assert_not_called()
    assert store.reminder_warnings == {}


@pytest.mark.parametrize("offset_days", [1, -1], ids=["due_tomorrow", "due_yesterday"])
def test_no_reminder_when_rental_not_due_today(offset_days):
    """Boundary: only rentals due exactly on the check date are reminded."""
    add_reminder_rental(due_date=TODAY + timedelta(days=offset_days))
    with patch(SEND) as mock_send:
        result = send_due_reminders(TODAY)

    assert result == []
    mock_send.assert_not_called()
    assert store.reminder_warnings == {}


def test_no_reminder_when_there_are_no_rentals():
    with patch(SEND) as mock_send:
        result = send_due_reminders(TODAY)

    assert result == []
    mock_send.assert_not_called()


def test_only_due_rental_is_reminded_among_several():
    """Due today, due tomorrow and returned: exactly one call, for the due one."""
    add_reminder_rental(rental_id=1, due_date=TODAY, renter_name="Alice",
                        email="alice@example.com")
    add_reminder_rental(rental_id=2, due_date=TODAY + timedelta(days=1))
    add_reminder_rental(rental_id=3, due_date=TODAY, return_date=TODAY)
    with patch(SEND, return_value=True) as mock_send:
        result = send_due_reminders(TODAY)

    assert result == [1]
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "alice@example.com"


# ====== Part 1: rentals that cannot get a reminder (reminder_problem) ======

def unmakable_rental(kind):
    """Build a rental that cannot get a reminder, for the given cause."""
    if kind == "missing_renter":
        return add_reminder_rental(with_renter=False)
    if kind == "blank_email":
        return add_reminder_rental(email="   ")
    if kind == "missing_equipment":
        return add_reminder_rental(with_equipment=False)
    raise AssertionError(kind)


PROBLEM_KINDS = ["missing_renter", "blank_email", "missing_equipment"]


@pytest.mark.parametrize("kind", PROBLEM_KINDS)
def test_reminder_problem_reports_each_cause(kind):
    rental = unmakable_rental(kind)
    assert reminder_problem(rental) is not None


@pytest.mark.parametrize("kind", PROBLEM_KINDS)
def test_flagged_rental_sends_nothing_and_stores_warning(kind):
    """No call is made for a rental that cannot get a reminder, and a warning
    is stored for it."""
    unmakable_rental(kind)
    with patch(SEND) as mock_send:
        result = send_due_reminders(TODAY)

    assert result == []
    mock_send.assert_not_called()
    assert list(store.reminder_warnings) == [1]


def test_flagged_rental_does_not_block_valid_rental():
    unmakable_rental("blank_email")                       # rental #1 is flagged
    add_reminder_rental(rental_id=2, renter_name="Bob", email="bob@example.com")
    with patch(SEND, return_value=True) as mock_send:
        result = send_due_reminders(TODAY)

    assert result == [2]
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "bob@example.com"
    assert list(store.reminder_warnings) == [1]


def test_flagged_rental_is_warned_once_when_check_repeats():
    """The warnings are keyed by rental, so a second check doesn't add another."""
    unmakable_rental("missing_renter")
    with patch(SEND):
        send_due_reminders(TODAY)
        send_due_reminders(TODAY)

    assert list(store.reminder_warnings) == [1]


def test_flagged_rental_is_logged(caplog):
    unmakable_rental("missing_equipment")
    caplog.set_level(logging.INFO)
    with patch(SEND):
        send_due_reminders(TODAY)

    assert caplog.records