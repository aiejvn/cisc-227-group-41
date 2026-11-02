"""
    Test assigned equipment and renter features.

    Tests that submit invalid input assert a 4xx status AND that no state changed.
"""
import pytest
from datetime import datetime as date

INVALID_DICT_VALUE = {"example": "no input categories accept a dictionary. this should fail all of them"}

REPEATS = 5  # how many times each action is repeated in the "repeat" tests


def create_equipment(client, **overrides):
    """Helper: create an equipment item and return its JSON body."""
    payload = {"name": "Canoe", "category": "Hiking", "total_units": 5}
    payload.update(overrides)
    response = client.post("/equipment", json=payload)
    assert response.status_code == 201
    return response.get_json()


def test_crud_equipment(client):
    """
        Test we can create, read, update, and delete equipment, and that
        every change is persisted (visible on a follow-up GET).
    """
    # We can create equipment
    create_response = client.post("/equipment", json={
        "name": "Canoe",
        "category": "Hiking",
        "total_units": 5
    })
    assert create_response.status_code == 201
    data = create_response.get_json()
    equipment_id = data["id"]
    assert data["name"] == "Canoe"
    assert data["category"] == "Hiking"
    assert data["total_units"] == 5

    # We can read equipment, and it matches what create returned
    read_response = client.get(f"/equipment/{equipment_id}")
    assert read_response.status_code == 200
    assert read_response.get_json() == data

    # We can update equipment
    update_payload = {
        "name": "Kayak",
        "category": "Rafting",
        "total_units": 10
    }
    update_response = client.put(f"/equipment/{equipment_id}", json=update_payload)
    assert update_response.status_code == 200
    update_data = update_response.get_json()
    for json_key in update_payload:
        assert update_data[json_key] == update_payload[json_key]

    # The update is persisted, not just echoed back
    reread = client.get(f"/equipment/{equipment_id}").get_json()
    for json_key in update_payload:
        assert reread[json_key] == update_payload[json_key]
    assert reread["id"] == equipment_id

    # We can delete equipment
    delete_response = client.delete(f"/equipment/{equipment_id}")
    assert delete_response.status_code == 204
    assert client.get(f"/equipment/{equipment_id}").status_code == 404


def test_create_equipment_defaults(client):
    """
        Omitted optional fields get defaults: total_units=1, available_units
        equal to total_units, is_available=True.
    """
    data = create_equipment(client)
    assert data["available_units"] == data["total_units"] == 5

    response = client.post("/equipment", json={"name": "Tent", "category": "Camping"})
    assert response.status_code == 201
    item = response.get_json()
    assert item["total_units"] == 1
    assert item["available_units"] == 1
    assert item["is_available"] is True

    # Defaults are persisted
    assert client.get(f"/equipment/{item['id']}").get_json() == item


def test_list_equipment(client):
    """
        The list endpoint reflects creates and deletes.
    """
    assert client.get("/equipment").get_json() == []

    first = create_equipment(client, name="Canoe")
    second = create_equipment(client, name="Tent", category="Camping")

    listed = client.get("/equipment").get_json()
    assert len(listed) == 2
    assert {e["name"] for e in listed} == {"Canoe", "Tent"}
    assert first["id"] != second["id"]

    # Deleting one leaves only the other
    assert client.delete(f"/equipment/{first['id']}").status_code == 204
    listed = client.get("/equipment").get_json()
    assert [e["id"] for e in listed] == [second["id"]]


def test_update_equipment_partial(client):
    """
        A PUT containing only some fields changes those and leaves the rest alone.
    """
    data = create_equipment(client)

    response = client.put(f"/equipment/{data['id']}", json={"name": "Raft"})
    assert response.status_code == 200

    reread = client.get(f"/equipment/{data['id']}").get_json()
    assert reread["name"] == "Raft"
    assert reread["category"] == data["category"]
    assert reread["total_units"] == data["total_units"]
    assert reread["available_units"] == data["available_units"]
    assert reread["is_available"] == data["is_available"]


def test_equipment_ids_are_not_reused(client):
    """
        A deleted equipment's id must not be handed to a new item, otherwise
        old references (e.g. rentals) would point at the wrong equipment.
    """
    first = create_equipment(client)
    assert client.delete(f"/equipment/{first['id']}").status_code == 204
    second = create_equipment(client, name="Tent")
    assert second["id"] != first["id"]


def test_set_equipment_status_workflow(client):
    """
        Taking equipment out of service is visible from every read path, and
        it can be put back in service.
    """
    data = create_equipment(client)
    equipment_id = data["id"]

    # Take it out of service
    patch_response = client.patch(f"/equipment/{equipment_id}/status", json={"is_available": False})
    assert patch_response.status_code == 200
    assert patch_response.get_json()["is_available"] is False

    # Persisted: both GET and the availability summary agree
    assert client.get(f"/equipment/{equipment_id}").get_json()["is_available"] is False
    availability = client.get(f"/equipment/{equipment_id}/availability").get_json()
    assert availability["is_available"] is False
    # Out of service does not change unit counts
    assert availability["available_units"] == data["available_units"]
    assert availability["total_units"] == data["total_units"]

    # Put it back in service
    assert client.patch(f"/equipment/{equipment_id}/status", json={"is_available": True}).status_code == 200
    assert client.get(f"/equipment/{equipment_id}/availability").get_json()["is_available"] is True


@pytest.mark.parametrize("bad_payload", [
    {},
    {"category": "Hiking"},                                   # missing name
    {"name": "Canoe"},                                        # missing category
    {"name": None, "category": "Hiking"},
    {"name": "Canoe", "category": None},
    {"name": INVALID_DICT_VALUE, "category": "Hiking"},
    {"name": "Canoe", "category": INVALID_DICT_VALUE},
    {"name": "Canoe", "category": "Hiking", "total_units": 0},
    {"name": "Canoe", "category": "Hiking", "total_units": -1},
    {"name": "Canoe", "category": "Hiking", "total_units": None},
    {"name": "Canoe", "category": "Hiking", "total_units": "abc"},
    {"name": "Canoe", "category": "Hiking", "total_units": INVALID_DICT_VALUE},
    {"name": "Canoe", "category": "Hiking", "is_available": INVALID_DICT_VALUE},
])
def test_invalid_create_equipment(client, bad_payload):
    """
        Missing, null, wrong-typed, or non-positive values must be rejected with
        a 4xx, and no partial record may be stored.
    """
    response = client.post("/equipment", json=bad_payload)
    assert 400 <= response.status_code < 500
    assert client.get("/equipment").get_json() == []


def test_invalid_read_equipment(client):
    """
        Reading an id that doesn't exist returns 404 with an error message.
    """
    create_equipment(client)

    response = client.get("/equipment/1234567890")
    assert response.status_code == 404
    assert "error" in response.get_json()

    # Non-integer ids never match the <int:> route, so they 404 in routing
    for query in ["/equipment/Null", "/equipment/-1", "/equipment/Blabla"]:
        response = client.get(query)
        assert response.status_code == 404
        assert "error" in response.get_json()


@pytest.mark.parametrize("bad_update", [
    {"name": None},
    {"name": INVALID_DICT_VALUE},
    {"category": None},
    {"category": INVALID_DICT_VALUE},
    {"total_units": -1},
    {"total_units": None},
    {"total_units": "abc"},
    {"is_available": INVALID_DICT_VALUE},
])
def test_invalid_update_equipment(client, bad_update):
    """
        An invalid update is rejected with a 4xx and leaves the stored item unchanged.
    """
    data = create_equipment(client)

    response = client.put(f"/equipment/{data['id']}", json=bad_update)
    assert 400 <= response.status_code < 500
    assert client.get(f"/equipment/{data['id']}").get_json() == data


def test_update_nonexistent_equipment(client):
    """
        Updating an id that doesn't exist returns 404 and creates nothing.
    """
    response = client.put("/equipment/999", json={"name": "Ghost"})
    assert response.status_code == 404
    assert client.get("/equipment").get_json() == []


def test_invalid_delete_equipment(client):
    """
        Deleting a nonexistent id returns 404, and deleting twice is an error
        the second time.
    """
    assert client.delete("/equipment/999").status_code == 404

    data = create_equipment(client)
    other = create_equipment(client, name="Tent")
    assert client.delete(f"/equipment/{data['id']}").status_code == 204
    assert client.delete(f"/equipment/{data['id']}").status_code == 404

    # The failed repeat delete didn't touch other items
    assert client.get(f"/equipment/{other['id']}").status_code == 200


def test_invalid_status_update(client):
    """
        Status changes on a missing item return 404; invalid values are rejected
        and leave the item's status unchanged.
    """
    assert client.patch("/equipment/999/status", json={"is_available": False}).status_code == 404

    data = create_equipment(client)
    for bad_payload in [{}, {"is_available": "yes"}, {"is_available": None}]:
        response = client.patch(f"/equipment/{data['id']}/status", json=bad_payload)
        assert 400 <= response.status_code < 500
        assert client.get(f"/equipment/{data['id']}").get_json()["is_available"] is True


def test_availability_nonexistent_equipment(client):
    """
        The availability summary of a missing item is a 404 with an error message.
    """
    response = client.get("/equipment/999/availability")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_update_available_units_over_total(client):
    """
        Boundary: available_units can never exceed total_units. A PUT that
        would break this must be rejected and not stored.
    """
    data = create_equipment(client, total_units=2)

    response = client.put(f"/equipment/{data['id']}", json={"available_units": 5})
    assert 400 <= response.status_code < 500

    reread = client.get(f"/equipment/{data['id']}").get_json()
    assert reread["available_units"] <= reread["total_units"]


def test_repeat_add_equipment(client):
    """
        Adding the identical equipment repeatedly is allowed: each request
        creates a separate record with its own id.
    """
    created = [create_equipment(client) for _ in range(REPEATS)]

    ids = [item["id"] for item in created]
    assert len(set(ids)) == REPEATS

    listed = client.get("/equipment").get_json()
    assert len(listed) == REPEATS
    for item in created:
        assert client.get(f"/equipment/{item['id']}").get_json() == item


def test_repeat_get_equipment(client):
    """
        Reading the same item repeatedly returns the same body every time and
        never changes the stored data.
    """
    data = create_equipment(client)
    create_equipment(client, name="Tent")

    for _ in range(REPEATS):
        response = client.get(f"/equipment/{data['id']}")
        assert response.status_code == 200
        assert response.get_json() == data

    assert len(client.get("/equipment").get_json()) == 2


def test_repeat_list_equipment(client):
    """
        Listing repeatedly returns identical results and never changes the data.
    """
    create_equipment(client, name="Canoe")
    create_equipment(client, name="Tent", category="Camping")

    first_listing = client.get("/equipment").get_json()
    assert len(first_listing) == 2
    for _ in range(REPEATS):
        assert client.get("/equipment").get_json() == first_listing


def test_repeat_update_equipment_same_payload(client):
    """
        Applying the same update repeatedly gives the same result each time
        and never changes the id.
    """
    data = create_equipment(client)
    payload = {"name": "Kayak", "category": "Rafting", "total_units": 10}

    for _ in range(REPEATS):
        response = client.put(f"/equipment/{data['id']}", json=payload)
        assert response.status_code == 200

        reread = client.get(f"/equipment/{data['id']}").get_json()
        assert reread["id"] == data["id"]
        for json_key in payload:
            assert reread[json_key] == payload[json_key]

    assert len(client.get("/equipment").get_json()) == 1


def test_repeat_update_equipment_different_payloads(client):
    """
        Repeated updates with different values each overwrite the previous one
        (the last update wins) and leave other items untouched.
    """
    data = create_equipment(client)
    other = create_equipment(client, name="Tent")

    for i in range(REPEATS):
        new_name = f"Canoe v{i}"
        assert client.put(f"/equipment/{data['id']}", json={"name": new_name}).status_code == 200
        assert client.get(f"/equipment/{data['id']}").get_json()["name"] == new_name

    assert client.get(f"/equipment/{other['id']}").get_json() == other


def test_repeat_delete_equipment(client):
    """
        Only the first delete of an item succeeds; every repeat is a 404 and
        leaves the other items untouched.
    """
    data = create_equipment(client)
    other = create_equipment(client, name="Tent")

    assert client.delete(f"/equipment/{data['id']}").status_code == 204
    for _ in range(REPEATS - 1):
        assert client.delete(f"/equipment/{data['id']}").status_code == 404

    assert [e["id"] for e in client.get("/equipment").get_json()] == [other["id"]]


def test_repeat_add_remove_equipment_cycle(client):
    """
        Repeatedly adding and removing equipment never reuses an id and leaves
        the list empty at the end.
    """
    seen_ids = []
    for _ in range(REPEATS):
        data = create_equipment(client)
        assert data["id"] not in seen_ids
        seen_ids.append(data["id"])
        assert client.delete(f"/equipment/{data['id']}").status_code == 204

    assert seen_ids == sorted(seen_ids)
    assert client.get("/equipment").get_json() == []


# =========================== END OF EQUIPMENT TESTS ===========================


def create_renter(client, **overrides):
    """Helper: create a renter and return its JSON body."""
    payload = {"name": "Alice Smith", "email": "alice@example.com"}
    payload.update(overrides)
    response = client.post("/renters", json=payload)
    assert response.status_code == 201
    return response.get_json()


def test_create_renter(client):
    """
        A created renter is returned with its fields, gets a membership date of
        today, and is persisted (visible on GET and in the list).
    """
    create_response = client.post("/renters", json={
        "name": "Alice Smith",
        "email": "alice@example.com"
    })
    assert create_response.status_code == 201
    data = create_response.get_json()
    assert data["name"] == "Alice Smith"
    assert data["email"] == "alice@example.com"
    assert data["membership_date"] == date.today().isoformat()

    # Persisted: GET returns the same body
    read_response = client.get(f"/renters/{data['id']}")
    assert read_response.status_code == 200
    assert read_response.get_json() == data

    # And the list contains exactly this renter
    assert client.get("/renters").get_json() == [data]


def test_create_multiple_renters(client):
    """
        Renters get distinct ids and are kept separate (no overwriting).
    """
    assert client.get("/renters").get_json() == []

    first = create_renter(client, name="Alice", email="alice@example.com")
    second = create_renter(client, name="Bob", email="bob@example.com")
    assert first["id"] != second["id"]

    assert client.get(f"/renters/{first['id']}").get_json()["name"] == "Alice"
    assert client.get(f"/renters/{second['id']}").get_json()["name"] == "Bob"
    assert len(client.get("/renters").get_json()) == 2


@pytest.mark.parametrize("bad_payload", [
    {},
    {"email": "alice@example.com"},                           # missing name
    {"name": "Alice"},                                        # missing email
    {"name": None, "email": "alice@example.com"},
    {"name": "Alice", "email": None},
    {"name": "", "email": "alice@example.com"},
    {"name": "Alice", "email": ""},
    {"name": 123, "email": "alice@example.com"},
    {"name": "Alice", "email": 123},
    {"name": INVALID_DICT_VALUE, "email": "alice@example.com"},
    {"name": "Alice", "email": INVALID_DICT_VALUE},
    {"name": "Alice", "email": "not-an-email"},
])
def test_invalid_create_renter(client, bad_payload):
    """
        Missing, null, empty, wrong-typed, or malformed values must be rejected
        with a 4xx, and no partial record may be stored.
    """
    response = client.post("/renters", json=bad_payload)
    assert 400 <= response.status_code < 500
    assert client.get("/renters").get_json() == []


def test_delete_renter(client):
    """
        Deleting a renter removes only that renter, and the removal is persisted.
    """
    keep = create_renter(client, name="Bob", email="bob@example.com")
    remove = create_renter(client, name="Alice", email="alice@example.com")

    delete_response = client.delete(f"/renters/{remove['id']}")
    assert delete_response.status_code == 204

    # Removed renter is gone from GET and from the list
    assert client.get(f"/renters/{remove['id']}").status_code == 404
    assert [r["id"] for r in client.get("/renters").get_json()] == [keep["id"]]

    # The other renter is untouched
    assert client.get(f"/renters/{keep['id']}").get_json() == keep


def test_renter_ids_are_not_reused(client):
    """
        A deleted renter's id must not be handed to a new renter, otherwise old
        rentals referencing that id would point at the wrong person.
    """
    first = create_renter(client)
    assert client.delete(f"/renters/{first['id']}").status_code == 204
    second = create_renter(client, name="Bob", email="bob@example.com")
    assert second["id"] != first["id"]


def test_invalid_delete_renter(client):
    """
        Deleting a nonexistent id returns 404 with an error message, and
        deleting the same renter twice fails the second time.
    """
    missing = client.delete("/renters/999")
    assert missing.status_code == 404
    assert "error" in missing.get_json()

    renter = create_renter(client)
    other = create_renter(client, name="Bob", email="bob@example.com")
    assert client.delete(f"/renters/{renter['id']}").status_code == 204
    assert client.delete(f"/renters/{renter['id']}").status_code == 404

    # The failed deletes didn't touch other renters
    assert client.get(f"/renters/{other['id']}").status_code == 200

    # Non-integer ids never match the <int:> route, so they 404 in routing
    for query in ["/renters/Null", "/renters/-1", "/renters/Blabla"]:
        assert client.delete(query).status_code == 404


def test_repeat_add_renter(client):
    """
        Adding the identical renter repeatedly is allowed: each request creates
        a separate renter with its own id and today's membership date.
    """
    created = [create_renter(client) for _ in range(REPEATS)]

    assert len({renter["id"] for renter in created}) == REPEATS
    assert all(renter["membership_date"] == date.today().isoformat() for renter in created)
    assert len(client.get("/renters").get_json()) == REPEATS


def test_repeat_delete_renter(client):
    """
        Only the first delete of a renter succeeds; every repeat is a 404 and
        leaves the other renters untouched.
    """
    renter = create_renter(client)
    other = create_renter(client, name="Bob", email="bob@example.com")

    assert client.delete(f"/renters/{renter['id']}").status_code == 204
    for _ in range(REPEATS - 1):
        assert client.delete(f"/renters/{renter['id']}").status_code == 404

    assert [r["id"] for r in client.get("/renters").get_json()] == [other["id"]]


def test_repeat_add_remove_renter_cycle(client):
    """
        Repeatedly adding and removing renters never reuses an id and leaves
        the list empty at the end.
    """
    seen_ids = []
    for _ in range(REPEATS):
        renter = create_renter(client)
        assert renter["id"] not in seen_ids
        seen_ids.append(renter["id"])
        assert client.delete(f"/renters/{renter['id']}").status_code == 204

    assert seen_ids == sorted(seen_ids)
    assert client.get("/renters").get_json() == []
