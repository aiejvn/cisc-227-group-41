"""
    Test equipment features.

    Tests that submit invalid input assert a 4xx status AND that no state changed.
"""
import pytest

INVALID_DICT_VALUE = {"example": "no input categories accept a dictionary. this should fail all of them"}


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
        assert client.get(query).status_code == 404


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
