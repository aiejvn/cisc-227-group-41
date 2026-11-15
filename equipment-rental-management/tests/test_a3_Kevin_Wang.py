"""Success-path tests for the daily equipment return reminder.

send_notification is mocked where the app uses it (app.routes.rentals) so the
test can check the exact recipient, subject, and message. One test uses the
real simulator, clearing it before and after.
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
    """The client fixture resets the store. Isolates the real simulator."""
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


def test_real_simulator_records_reminder():
    add_well_formed_rental()
    assert send_due_reminders(TODAY) == [1]
    assert notification_service.get_notifications() == [{
        "recipient": EXPECTED_RECIPIENT,
        "subject": EXPECTED_SUBJECT,
        "message": EXPECTED_MESSAGE,
    }]
