""" 
Testing rental features.
"""

import pytest
from datetime import date, timedelta

INVALID_DICT_VALUE = {"example": "a dictionary is not a valid field value"}


# ======================== Helper Functions =========================

# Ported over from Kevin's Feature Tests to avoid merge conflicts
def create_equipment(client, **overrides):
    """Helper: create an equipment item and return its JSON body."""
    payload = {"name": "Canoe", "category": "Hiking", "total_units": 5}
    payload.update(overrides)
    response = client.post("/equipment", json=payload)
    assert response.status_code == 201
    return response.get_json()

# Ported over from Kevin's Feature Tests to avoid merge conflicts
def create_renter(client, **overrides):
    """Helper: create a renter and return its JSON body."""
    payload = {"name": "Alice Smith", "email": "alice@example.com"}
    payload.update(overrides)
    response = client.post("/renters", json=payload)
    assert response.status_code == 201
    return response.get_json()

def create_rental(client, equipment_id, renter_id, **overrides):
    """Helper: creates a rental and returns its JSON body."""
    payload = {"equipment_id": equipment_id, "renter_id": renter_id, "deposit_amount": 25.0}
    payload.update(overrides)
    response = client.post("/rentals", json=payload)
    assert response.status_code == 201
    return response.get_json()


# ====================== Feature 4: Adding a rental ======================
def test_add_rental(client):
    """
        Checking out equipment creates a rental with the expected renter,
        equipment, due date, and deposit information.
    """
    
    equipment = create_equipment(client)
    renter = create_renter(client)

    rental = create_rental(
        client,
        equipment_id=equipment["id"],
        renter_id=renter["id"],
        deposit_amount=40.0
    )

    assert rental["equipment_id"] == equipment["id"]
    assert rental["renter_id"] == renter["id"]
    assert rental["deposit_amount"] == 40.0
    assert rental["return_date"] is None
    assert rental["rental_date"] == date.today().isoformat()
    assert rental["due_date"] == (date.today() + timedelta(days=7)).isoformat()

    # The rental is persisted and visible through the list endpoint.
    listed = client.get("/rentals").get_json()
    assert rental in listed


def test_add_rental_decreases_available_units(client):
    """ Checking out one unit decreases available_units by one without
        changing total_units.
    """
    
    equipment = create_equipment(client, total_units=3)
    renter = create_renter(client)

    create_rental(client, equipment_id = equipment["id"], renter_id = renter["id"])

    reread = client.get(f"/equipment/{equipment['id']}").get_json()
    assert reread["total_units"] == 3
    assert reread["available_units"] == 2


def test_add_rental_nonexistent_equipment(client):
    """ Checking out nonexistent equipment will return a 404 and creates
        no rental.
    """
    renter = create_renter(client)

    response = client.post("/rentals", json = {"equipment_id": 9999, "renter_id": renter["id"]})
    assert response.status_code == 404
    assert "error" in response.get_json()
    assert client.get("/rentals").get_json() == []


def test_add_rental_nonexistent_renter(client):
    """ Checking out equipment for a renter that does not exist will be
        rejected without creating a rental or changing equipment availability.

        The current checkout process does not verify that a renter_id exists, 
        so this test should expose an existing defect in the system.
    """
    
    equipment = create_equipment(client)

    before = client.get(f"/equipment/{equipment['id']}").get_json()
    response = client.post("/rentals", json = {"equipment_id": equipment["id"], "renter_id": 9999})
    assert 400 <= response.status_code < 500
    assert client.get("/rentals").get_json() == []

    after = client.get(f"/equipment/{equipment['id']}").get_json()
    assert after == before


def test_add_rental_when_no_units_are_available(client):
    """ Equipment with no available units should not be checked out again.
        Also, a rejected checkout must not make available_units negative.

        The current checkout process does not check available_units, 
        so this test is should expose an existing defect in the system.
    """
    equipment = create_equipment(client, total_units=1)
    renter = create_renter(client)

    create_rental(client, equipment_id = equipment["id"], renter_id = renter["id"])

    equipment_before = client.get(f"/equipment/{equipment['id']}").get_json()
    rentals_before = client.get("/rentals").get_json()
    assert equipment_before["available_units"] == 0

    response = client.post("/rentals", json = {"equipment_id": equipment["id"], "renter_id": renter["id"]})
    assert 400 <= response.status_code < 500

    # Neither the rental list nor the equipment record should change
    assert client.get("/rentals").get_json() == rentals_before

    equipment_after = client.get(f"/equipment/{equipment['id']}").get_json()
    assert equipment_after == equipment_before

  
# ====================== Feature 5: Returning rented equipment ======================
def test_return_rented_equipment(client):
    """ Returning a rental will record today's date and restores one unit
        to the equipment's available-unit count.
    """
    
    equipment = create_equipment(client, total_units=3)
    renter = create_renter(client)

    rental = create_rental(client, equipment_id = equipment["id"], renter_id=renter["id"])

    before_return = client.get(f"/equipment/{equipment['id']}").get_json()
    assert before_return["available_units"] == 2

    response = client.put(f"/rentals/{rental['id']}/return")
    assert response.status_code == 200

    returned = response.get_json()
    assert returned["id"] == rental["id"]
    assert returned["return_date"] == date.today().isoformat()

    # The return date shall retain
    listed = client.get("/rentals").get_json()
    persisted = next(r for r in listed if r["id"] == rental["id"])
    assert persisted["return_date"] == date.today().isoformat()

    # Restore one unit of equipment
    after_return = client.get(f"/equipment/{equipment['id']}").get_json()
    assert after_return["available_units"] == 3
    assert after_return["total_units"] == 3


def test_return_rented_equipment_twice(client):
    """ Returning the same rental twice will get rejected and should not 
        increase available_units twice.
    """
    
    equipment = create_equipment(client, total_units=2)
    renter = create_renter(client)

    rental = create_rental(client, equipment_id = equipment["id"], renter_id = renter["id"])

    first_return = client.put(f"/rentals/{rental['id']}/return")
    assert first_return.status_code == 200

    after_first_return = client.get(f"/equipment/{equipment['id']}").get_json()
    second_return = client.put(f"/rentals/{rental['id']}/return")
    assert second_return.status_code == 400

    after_second_return = client.get(f"/equipment/{equipment['id']}").get_json()
    assert after_second_return == after_first_return
    assert after_second_return["available_units"] == 2


def test_return_nonexistent_rental(client):
    """ Returning a rental that doesn't exist returns a 404 and does not
        change an equipment's availability.
    """
    
    equipment = create_equipment(client)

    before = client.get(f"/equipment/{equipment['id']}").get_json()

    response = client.put("/rentals/999/return")
    assert response.status_code == 404
    assert "error" in response.get_json()

    after = client.get(f"/equipment/{equipment['id']}").get_json()
    assert after == before



# ====================== Feature 6: Looking up rentals ======================
# def test_look_up_rentals():


