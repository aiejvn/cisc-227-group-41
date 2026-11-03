"""
Testing assigned renter and rental features.

Some tests are intended to expose defects in the current implementation.
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


# ====================== Feature 1: Updating a renter ======================
def test_update_renter(client):
    """ Updating a renter will change the name and email associated,
        the changes should persist with future renter retrievals.
    """
    
    renter = create_renter(client)
    update_payload = {"name": "Alice Jones", "email": "alicejones@example.com"}
    
    response = client.put(f"/renters/{renter['id']}", json = update_payload)

    assert response.status_code == 200
    updated = response.get_json()
    
    reread = client.get(f"renters/{renter['id']}")
    assert reread.status_code == 200
    assert reread.get_json() == updated
    
    assert updated["id"] == renter["id"]
    assert updated["membership_date"] == renter["membership_date"]


def test_update_renter_partial(client):
    """ A PUT containing only some fields to change and leaves
        the remaining renter information the same. 
    """
    
    renter = create_renter(client)
    
    response = client.put(f"/renters{renter['id']}", json = {"name": "Alice Mace"})
    assert response.status_code == 200
    
    reread = client.get(f"/renters/{renter['id']}").get_json()
    assert reread["name"] == "Alice Mace"
    assert reread["email"] == renter["email"]
    assert reread["membership_date"] == renter["membership_date"]


@pytest.mark.parametrize("bad_update", [
    {"name": None},
    {"name": ""},
    {"name": 123},
    {"name": INVALID_DICT_VALUE},
    {"name": None},
    {"name": ""},
    {"name": 123},
    {"name": INVALID_DICT_VALUE},
])
def test_invalid_update_renter(client, bad_update):
    """ An invalid update should return a 4xx response and leave the
        original renter information unchanged.
        
        The current update process doesn't validate renter values, so
        this test might expose an existing defect in the system.    
    """
    
    renter = create_renter(client)
    
    response = client.put(f"/renters/{renter['id']}", json = bad_update)
    assert 400 <= response.status_code < 500
    assert client.get(f"/renters/{renter['id']}").get_json() == renter


def test_update_nonexistant_renter(client):
    """ Updating an renter ID that doesn't exist returns a 404 and 
        does nothing.
    """
    
    response = client.put(f"/renters/9999", json = {"name": "Unknown Unknown"})    
    assert response.status_code == 404
    assert "error" in response.get_json()
    assert client.get("/renters").get_json() == []
    
    

# ====================== Feature 2: Listing all renters ======================
def test_list_all_renters(client):
    """ The list endpoint starts empty and reflects renters added 
        to the system later
    """
    
    assert client.get("/renters").get_json() == []
    
    first = create_renter(client, name = "Alice", email = "alice@example.com")
    second = create_renter(client, name = "Bob", email = "bob@example.com")
    
    response = client.get("/renters")
    assert response.status_code == 200
    
    listed = response.get_json()
    assert len(listed) == 2
    assert {r["id"] for r in listed} == {first["id"], second["id"]}
    assert {r["name"] for r in listed} == {"Alice", "Bob"}


def test_list_renters_reflects_updates(client):
    """ Changes made to a renter later also need to be reflected in
        the list endpoint.
    """
    
    renter = create_renter(client)
    
    response = client.put(f"/renters/{renter['id']}", json = {"name": "Alice Updated"})
    assert response.status_code == 200
    
    listed = client.get("/renters").get_json()
    assert len(listed) == 1
    assert listed[0]["id"] == renter["id"]
    assert listed[0]["name"] == "Alice Updated"



# ====================== Feature 3: Get one renter ======================

def test_get_one_renter(client):
    """ Retriving an existing renter will return the information 
        matching to the renter's record when first created. 
    """
    
    renter = create_renter(client)
    
    response = client.get(f"/renters/{renter['id']}")
    assert response.status_code == 200
    assert response.get_json() == renter
    data = response.get_json()
    
    assert data["id"] == renter["id"]
    assert data["name"] == "Alice Smith"
    assert data["email"] == "alice@example.com"
    assert data["membership_date"] == date.today().isoformat()

def test_get_nonexistent_renter(client):
    """ Retrieving a renter ID that doesn't exist will return a
        404 with an error message.
    """
    
    create_renter(client)
    
    response = client.get("/renters/9999")
    assert response.status_code == 404
    assert "error" in response.get_json()
    
    for query in ["/renters/Null", "/renters/Null"]:
        assert client.get(query).status_code == 404



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

    # The rental persists and is visible through the list endpoint
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



# ====================== Feature 6: List all rentals ======================
def test_list_rentals(client):
    """ The list of rentals starts empty and returns all rentals after 
        checkout.
    """
    
    assert client.get("/rentals").get_json() == []
    equipment = create_equipment(client)
    
    first_renter = create_renter(client, name = "Alice", email = "alice@example.com")
    second_renter = create_renter(client, name = "Bob", email = "bob@example.com")
    
    first = create_rental(client, equipment_id = equipment["id"], renter_id = first_renter["id"])
    second = create_rental(client, equipment_id = equipment["id"], renter_id = second_renter["id"])

    response = client.get("/rentals")
    assert response.status_code == 200

    listed = response.get_json()
    assert len(listed) == 2
    assert {r["id"] for r in listed} == {first["id"], second["id"]}


def test_filter_rentals_by_equipment_id(client):
    """ Supplying equipment_id will only return rentals associated with that
        equipment item.
    """
    
    first_equipment = create_equipment(client, name = "Canoe")
    second_equipment = create_equipment(client, name = "Tent", category = "Camping")

    renter = create_renter(client)
    first_rental = create_rental(client, equipment_id = first_equipment["id"], renter_id = renter["id"])
    second_rental = create_rental(client, equipment_id = second_equipment["id"], renter_id = renter["id"])

    response = client.get(f"/rentals?equipment_id = {first_equipment['id']}")
    assert response.status_code == 200

    listed = response.get_json()
    assert len(listed) == 1
    assert listed[0]["id"] == first_rental["id"]
    assert listed[0]["equipment_id"] == first_equipment["id"]
    assert second_rental["id"] not in {r["id"] for r in listed}


def test_filter_rentals_by_renter_id(client):
    """ Supplying renter_id only returns rentals belonging to that renter.

        The two IDs are purposefully different: renter_id = 2 and equipment_id = 1.
        This test might expose the current implementation's bug, which compares
        equipment_id with the renter_id query parameter.
    """
    
    equipment = create_equipment(client)
    first_renter = create_renter(client, name = "Alice", email = "alice@example.com")
    second_renter = create_renter(client, name = "Bob", email = "bob@example.com")

    # Created a rental with renter 2 and equipment 1
    target_rental = create_rental(client, equipment_id = equipment["id"], renter_id = second_renter["id"])
    assert second_renter["id"] != equipment["id"]

    # Created a rental that should not appear in these results
    other_rental = create_rental(client, equipment_id = equipment["id"], renter_id = first_renter["id"])

    response = client.get(f"/rentals?renter_id = {second_renter['id']}")
    assert response.status_code == 200

    listed = response.get_json()
    assert len(listed) == 1
    assert listed[0]["id"] == target_rental["id"]
    assert listed[0]["renter_id"] == second_renter["id"]
    assert other_rental["id"] not in {r["id"] for r in listed}


def test_filter_rentals_by_both_ids(client):
    """ When both query params are supplied, the results must satisfy
        both the equipment and renter filters.
    """
    
    first_equipment = create_equipment(client, name = "Canoe")
    second_equipment = create_equipment(client, name = "Tent", category = "Camping")

    first_renter = create_renter(client, name = "Alice", email = "alice@example.com")
    second_renter = create_renter(client, name = "Bob", email = "bob@example.com")

    target = create_rental(client, equipment_id = first_equipment["id"], renter_id = first_renter["id"])

    create_rental(client, equipment_id = first_equipment["id"], renter_id = second_renter["id"])
    create_rental(client, equipment_id = second_equipment["id"], renter_id = first_renter["id"])

    response = client.get(
        f"/rentals?equipment_id = {first_equipment['id']}"
        f"&renter_id = {first_renter['id']}"
    )
    assert response.status_code == 200

    listed = response.get_json()
    assert len(listed) == 1
    assert listed[0]["id"] == target["id"]



# ============ Feature Enhancement: Mark equipment as out of service ============
def test_equipment_defaults_to_in_service(client):
    """ Newly added equipment should be set to available for default rentals. 
    """
    
    equipment = create_equipment(client)
    assert equipment["is_available"] is True
    
    response = client.get(f"/equipment/{equipment['id']}")
    assert response.status_code == 200
    assert response.get_json()["is_available"] is True

    
def test_mark_equipment_out_of_service(client):
    """ An employee can mark/toggle a piece of equipment as out of service,
        and the change should persist.
    """
    
    equipment = create_equipment(client)
    url = f"/equipment/{equipment['id']}/status"
    
    response = client.patch(url, json = {"is_available": False})
    assert response.status_Code == 200
    assert response.get_json()["is_available"] is False
    
    # Check to see if the changed status persists
    get_response = client.get(f"/equipment/{equipment['id']}")
    assert get_response.status_code == 200
    assert get_response.get_json()["is_available"] is False
    
    # Restore equipment to the in-service status
    restored = client.patch(url, json = {"is_available": True})
    assert restored.status_code == 200
    assert restored.get_json()["is_available"] is True


def test_mark_nonexistent_equipment_out_of_serivce(client):
    """ Attempting to change the state of a nonexistent piece of 
        equipment will return a 404.
    """
    
    response = client.patch("/equipment/9999/status", json = {"is_available": False})
    assert response.status_code == 404
    assert "error" in response.get_json()


@pytest.mark.parametrize("bad_payload", [
    {},
    {"is_available": "false"},
    {"is_available": "yes"},
    {"is_available": 1},
    {"is_available": None},
    {"is_available": []},
    {"is_available": {}},
])
def test_equipment_status_invalid_value(client, bad_payload):
    """ Only Boolean true or false values are accepted. Invalid values return a 400 
    and do not change the status.
    """
    
    equipment = create_equipment(client)

    response = client.patch(f"/equipment/{equipment['id']}/status", json = bad_payload)
    assert response.status_code == 400

    get_response = client.get(f"/equipment/{equipment['id']}")
    assert get_response.get_json()["is_available"] is True


def test_checkout_out_of_service_equipment_rejected(client):
    """ Equipment thats get marked as out of service cannot be rented, 
        even when there are still units available.
    """
    
    equipment = create_equipment(client, total_units=3)
    renter = create_renter(client)

    status_response = client.patch(f"/equipment/{equipment['id']}/status", json = {"is_available": False})
    assert status_response.status_code == 200
    
    before_units = client.get(f"/equipment/{equipment['id']}/availablity").get_json()["available_units"]
    
    response = client.post("/rentals", json = {"equipment_id": equipment["id"], "renter_id": renter["id"],})
    assert response.status_code == 409
    assert "error" in response.get_json()

    # No rental should be created
    assert client.get("/rentals").get_json() == []
    
    after = client.get(f"/equipment/{['id']}/availability").get_json()
    assert after["available_units"] == before_units

    # Available quantity should remain unchanged
    equipment_response = client.get(f"/equipment/{equipment['id']}").get_json()
    assert equipment_response.get_json()["is_available"] is False

    
def test_checkout_restored_equipment_succeeds(client):
    """ After equipment has been restored to back in service, it can be
        rented and checked out like normal again.
    """
    
    equipment = create_equipment(client)
    renter = create_renter(client)

    out_of_service = client.patch(f"/equipment/{equipment['id']}/status", json = {"is_available": False})
    assert out_of_service.status_code == 200
    
    restored = client.patch(f"/equipment/{equipment['id']}/status", json = {"is_available": True})
    assert restored.status_code == 200

    response = client.post("/rentals", json = {"equipment_id": equipment["id"], "renter_id": renter["id"],})
    assert response.status_code == 201