# ============================================================
# EXAMPLE TESTS — READ THESE, THEN WRITE YOUR OWN
# ============================================================
# These two tests are provided as scaffolding to show you:
#   1. How to use the `client` fixture from conftest.py
#   2. Two common patterns: empty-list check and create-then-verify
#
# DO NOT count these toward your required test functions.
# Write your own tests in a separate file, e.g. tests/test_<yourname>.py
# ============================================================

"""
Testing renter features, rental features will come later

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
    assert reread.get_jason() == updated
    
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
def test_invalud_update_reneter(client, bad_update):
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
    
    response = client.put(f"/renters/{renter["id"]}", json = {"name": "Alice Updated"})
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

def test_get_noexistant_renter(client):
    """ Retrieving a renter ID that doesn't exist will return a
        404 with an error message.
    """
    
    create_renter(client)
    
    response = client.get("/renters/9999")
    assert response.status_code == 404
    assert "error" in response.get_json()
    
    for query in ["/renters/Null", "/renters/Null"]:
        assert client.get(query).status_code == 404
