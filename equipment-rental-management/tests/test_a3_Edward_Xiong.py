""""Member B work allocations:

Part 1 - Notification tests (failure and non-trigger paths) for the daily equipment return reminder 
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
    
# ================== Part 1: Reminder helpers (store setup) ==================

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


# ===================== Part 1: Failed notification =====================

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
    assert caplog.records   # logged failure


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


# ============== Part 1: Non-trigger paths (no call is made) ==============

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


# ====== Part 1: Rentals that cannot get a reminder (reminder_problem) ======

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
    # Rental 1 is flagged
    unmakable_rental("blank_email")
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


# ============ Part 1: Warning on the Rentals page and dismiss ============

def dismiss_url(rental_id):
    return f"/ui/rentals/warnings/{rental_id}/dismiss"


def test_rentals_page_shows_warning_with_dismiss_control(client):
    unmakable_rental("blank_email")
    with patch(SEND):
        send_due_reminders(TODAY)

    response = client.get("/ui/rentals")

    assert response.status_code == 200
    assert dismiss_url(1) in response.get_data(as_text=True)


def test_rentals_page_has_no_dismiss_control_without_warning(client):
    add_reminder_rental()
    response = client.get("/ui/rentals")

    assert response.status_code == 200
    assert "/warnings/" not in response.get_data(as_text=True)


def test_dismiss_warning_removes_it_from_store_and_page(client):
    unmakable_rental("missing_renter")
    with patch(SEND):
        send_due_reminders(TODAY)
    assert 1 in store.reminder_warnings

    response = client.post(dismiss_url(1))

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/ui/rentals")
    assert store.reminder_warnings == {}
    assert dismiss_url(1) not in client.get("/ui/rentals").get_data(as_text=True)


def test_dismiss_only_removes_the_chosen_warning(client):
    unmakable_rental("blank_email")
    add_reminder_rental(rental_id=2, with_renter=False)
    with patch(SEND):
        send_due_reminders(TODAY)
    assert sorted(store.reminder_warnings) == [1, 2]

    response = client.post(dismiss_url(1))

    assert response.status_code == 302
    assert list(store.reminder_warnings) == [2]


def test_dismiss_unknown_warning_is_harmless(client):
    unmakable_rental("blank_email")
    with patch(SEND):
        send_due_reminders(TODAY)

    response = client.post(dismiss_url(999))

    assert response.status_code == 302
    assert list(store.reminder_warnings) == [1]


# ============== Part 2: Helpers for the rentals.py routes ==============

def make_equipment(client, **overrides):
    payload = {"name": "Canoe", "category": "Hiking", "total_units": 3}
    payload.update(overrides)
    response = client.post("/equipment", json=payload)
    assert response.status_code == 201
    return response.get_json()


def make_renter(client, **overrides):
    payload = {"name": "Alice Smith", "email": "alice@example.com"}
    payload.update(overrides)
    response = client.post("/renters", json=payload)
    assert response.status_code == 201
    return response.get_json()


def make_rental(client, equipment_id, renter_id):
    """Check out one unit. Equipment is not flagged for a deposit, so the
    deposit must be 0 (a non-zero deposit is rejected with a 400)."""
    response = client.post(
        "/rentals",
        json={"equipment_id": equipment_id, "renter_id": renter_id, "deposit_amount": 0.0},
    )
    assert response.status_code == 201
    return response.get_json()


def make_returned_rental(client):
    """Create a rental, return it, and give back (equipment, rental)."""
    equipment = make_equipment(client)
    renter = make_renter(client)
    rental = make_rental(client, equipment["id"], renter["id"])
    assert client.put(f"/rentals/{rental['id']}/return").status_code == 200
    return equipment, rental


# ====================== list_rentals: filters ======================

def test_filter_rentals_by_equipment_id_returns_only_matching(client):
    """Only rentals for the requested equipment are returned."""
    canoe = make_equipment(client, name="Canoe")
    tent = make_equipment(client, name="Tent", category="Camping")
    renter = make_renter(client)
    canoe_rental = make_rental(client, canoe["id"], renter["id"])
    make_rental(client, tent["id"], renter["id"])

    response = client.get(f"/rentals?equipment_id={canoe['id']}")

    assert response.status_code == 200
    listed = response.get_json()
    assert [r["id"] for r in listed] == [canoe_rental["id"]]
    assert listed[0]["equipment_id"] == canoe["id"]


def test_filter_rentals_with_no_match_returns_empty_list(client):
    """Boundary: a filter that matches nothing gives 200 and an empty list."""
    equipment = make_equipment(client)
    renter = make_renter(client)
    make_rental(client, equipment["id"], renter["id"])

    response = client.get("/rentals?equipment_id=9999")

    assert response.status_code == 200
    assert response.get_json() == []


@pytest.mark.xfail(
    reason="Known defect: list_rentals compares rental.equipment_id (not "
           "renter_id) with the renter_id query parameter, so filtering by "
           "renter returns the wrong rentals.",
)
def test_filter_rentals_by_renter_id_returns_only_that_renters_rentals(client):
    """Renter id 2 and equipment id 1 are deliberately different so the
    wrong-field comparison cannot pass by coincidence."""
    equipment = make_equipment(client)
    first_renter = make_renter(client, name="Alice", email="alice@example.com")
    second_renter = make_renter(client, name="Bob", email="bob@example.com")
    make_rental(client, equipment["id"], first_renter["id"])
    target = make_rental(client, equipment["id"], second_renter["id"])
    assert second_renter["id"] != equipment["id"]

    response = client.get(f"/rentals?renter_id={second_renter['id']}")

    assert response.status_code == 200
    listed = response.get_json()
    assert [r["id"] for r in listed] == [target["id"]]
    assert listed[0]["renter_id"] == second_renter["id"]


# ================= return_equipment: already returned =================

def test_return_rental_twice_is_rejected_and_units_unchanged(client):
    """A second return gives 400 and must not add another unit back."""
    equipment, rental = make_returned_rental(client)
    units_after_first_return = client.get(f"/equipment/{equipment['id']}").get_json()[
        "available_units"
    ]

    response = client.put(f"/rentals/{rental['id']}/return")

    assert response.status_code == 400
    assert "error" in response.get_json()
    reread = client.get(f"/equipment/{equipment['id']}").get_json()
    assert reread["available_units"] == units_after_first_return
    assert reread["available_units"] <= reread["total_units"]


# ========================= extend_rental =========================

def test_extend_rental_defaults_to_one_day(client):
    """With no 'days' value, the due date moves back by exactly one day."""
    equipment = make_equipment(client)
    renter = make_renter(client)
    rental = make_rental(client, equipment["id"], renter["id"])
    original_due = date.fromisoformat(rental["due_date"])

    response = client.put(f"/rentals/{rental['id']}/extend", json={})

    assert response.status_code == 200
    body = response.get_json()
    assert body["id"] == rental["id"]
    assert body["due_date"] == (original_due + timedelta(days=1)).isoformat()


def test_extend_rental_by_custom_days_is_persisted(client):
    """A custom extension is applied and visible in later rental listings."""
    equipment = make_equipment(client)
    renter = make_renter(client)
    rental = make_rental(client, equipment["id"], renter["id"])
    original_due = date.fromisoformat(rental["due_date"])

    response = client.put(f"/rentals/{rental['id']}/extend", json={"days": 5})

    assert response.status_code == 200
    expected_due = (original_due + timedelta(days=5)).isoformat()
    assert response.get_json()["due_date"] == expected_due
    listed = client.get("/rentals").get_json()
    assert [r["due_date"] for r in listed if r["id"] == rental["id"]] == [expected_due]


def test_extend_rental_can_be_repeated(client):
    """Two extensions add up."""
    equipment = make_equipment(client)
    renter = make_renter(client)
    rental = make_rental(client, equipment["id"], renter["id"])
    original_due = date.fromisoformat(rental["due_date"])

    client.put(f"/rentals/{rental['id']}/extend", json={"days": 2})
    response = client.put(f"/rentals/{rental['id']}/extend", json={"days": 3})

    assert response.status_code == 200
    assert response.get_json()["due_date"] == (original_due + timedelta(days=5)).isoformat()


def test_extend_nonexistent_rental_returns_404(client):
    response = client.put("/rentals/9999/extend", json={"days": 2})

    assert response.status_code == 404
    assert "error" in response.get_json()
    assert client.get("/rentals").get_json() == []


def test_extend_returned_rental_is_rejected_and_due_date_unchanged(client):
    """A rental that is already returned cannot be extended."""
    _, rental = make_returned_rental(client)

    response = client.put(f"/rentals/{rental['id']}/extend", json={"days": 3})

    assert response.status_code == 400
    assert "error" in response.get_json()
    listed = client.get("/rentals").get_json()
    assert [r["due_date"] for r in listed if r["id"] == rental["id"]] == [rental["due_date"]]


@pytest.mark.xfail(
    reason="Known defect: extend_rental does not validate 'days'. A "
           "non-numeric value raises an unhandled TypeError (HTTP 500) "
           "instead of a 4xx response.",
)
def test_extend_rental_with_non_numeric_days_is_rejected(client):
    equipment = make_equipment(client)
    renter = make_renter(client)
    rental = make_rental(client, equipment["id"], renter["id"])

    response = client.put(f"/rentals/{rental['id']}/extend", json={"days": "abc"})

    assert 400 <= response.status_code < 500
    listed = client.get("/rentals").get_json()
    assert [r["due_date"] for r in listed if r["id"] == rental["id"]] == [rental["due_date"]]


# ======================== release_deposit ========================

def test_release_deposit_nonexistent_rental_returns_404(client):
    response = client.put("/rentals/9999/deposit/release")

    assert response.status_code == 404
    assert "error" in response.get_json()


def test_release_deposit_before_return_is_rejected(client):
    """The deposit can't be released while the equipment is still out."""
    equipment = make_equipment(client)
    renter = make_renter(client)
    rental = make_rental(client, equipment["id"], renter["id"])

    response = client.put(f"/rentals/{rental['id']}/deposit/release")

    assert response.status_code == 400
    assert "error" in response.get_json()
    listed = client.get("/rentals").get_json()
    assert [r["deposit_released"] for r in listed if r["id"] == rental["id"]] == [False]


def test_release_deposit_for_returned_rental_reports_released(client):
    """The response for a returned rental says the deposit was released."""
    _, rental = make_returned_rental(client)

    response = client.put(f"/rentals/{rental['id']}/deposit/release")

    assert response.status_code == 200
    assert response.get_json() == {"rental_id": rental["id"], "deposit_released": True}


@pytest.mark.xfail(
    reason="Known defect (documented in rentals.py): release_deposit returns "
           "deposit_released=true but never sets rental.deposit_released, so "
           "the change is not persisted.",
)
def test_release_deposit_is_persisted(client):
    _, rental = make_returned_rental(client)

    response = client.put(f"/rentals/{rental['id']}/deposit/release")
    assert response.status_code == 200

    listed = client.get("/rentals").get_json()
    assert [r["deposit_released"] for r in listed if r["id"] == rental["id"]] == [True]