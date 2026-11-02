"""
    Test assigned equipment and renter features.

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



# =========================== END OF EQUIPMENT TESTS ===========================


# ============================== DEPOSIT TESTS ================================


def test_needs_deposit_defaults_to_false(client):
    """
        New equipment doesn't need a deposit, and the flag is visible on both
        the create response and a follow-up GET.
    """
    data = create_equipment(client)
    assert data["needs_deposit"] is False
    assert client.get(f"/equipment/{data['id']}").get_json()["needs_deposit"] is False


def test_deposit_flag_lock_follows_rented_units():
    """
        The flag is locked exactly when some units are rented out, i.e. when
        available_units differs from total_units.
    """
    from app.models.equipment import Equipment

    item = Equipment(id=1, name="Canoe", category="Hiking", total_units=3, available_units=3)
    assert item.deposit_flag_locked() is False

    item.available_units = 2  # one unit rented
    assert item.deposit_flag_locked() is True

    item.available_units = 0  # all units rented
    assert item.deposit_flag_locked() is True

    item.available_units = 3  # everything returned
    assert item.deposit_flag_locked() is False


def create_flagged_equipment(client, **overrides):
    """Helper: create equipment and turn on needs_deposit through the API."""
    data = create_equipment(client, **overrides)
    response = client.patch(f"/equipment/{data['id']}/deposit", json={"needs_deposit": True})
    assert response.status_code == 200
    data["needs_deposit"] = True
    return data


def test_toggle_deposit_flag(client):
    """
        The flag can be turned on and off.
    """
    data = create_equipment(client)
    url = f"/equipment/{data['id']}/deposit"

    on = client.patch(url, json={"needs_deposit": True})
    assert on.status_code == 200
    assert on.get_json()["needs_deposit"] is True
    assert client.get(f"/equipment/{data['id']}").get_json()["needs_deposit"] is True

    off = client.patch(url, json={"needs_deposit": False})
    assert off.status_code == 200
    assert client.get(f"/equipment/{data['id']}").get_json()["needs_deposit"] is False


def test_toggle_deposit_flag_nonexistent_equipment(client):
    """
        Toggling a missing item returns 404 with an error message.
    """
    response = client.patch("/equipment/999/deposit", json={"needs_deposit": True})
    assert response.status_code == 404
    assert "error" in response.get_json()


@pytest.mark.parametrize("bad_payload", [
    {},
    {"needs_deposit": "yes"},
    {"needs_deposit": 1},
    {"needs_deposit": None},
    {"needs_deposit": INVALID_DICT_VALUE},
])
def test_toggle_deposit_flag_invalid_value(client, bad_payload):
    """
        Only true or false is accepted; anything else is a 400 and the flag is unchanged.
    """
    data = create_equipment(client)
    response = client.patch(f"/equipment/{data['id']}/deposit", json=bad_payload)
    assert response.status_code == 400
    assert client.get(f"/equipment/{data['id']}").get_json()["needs_deposit"] is False


@pytest.mark.parametrize("start_flagged", [False, True])
def test_toggle_deposit_flag_locked_while_rented(client, start_flagged):
    """
        While a unit is rented out the flag can't change in either direction
        (409, unchanged), and it becomes changeable again after the return.
    """
    data = create_flagged_equipment(client) if start_flagged else create_equipment(client)
    renter = create_renter(client)
    url = f"/equipment/{data['id']}/deposit"

    rental = client.post("/rentals", json={
        "equipment_id": data["id"],
        "renter_id": renter["id"],
        "deposit_amount": 10,
    })
    assert rental.status_code == 201

    response = client.patch(url, json={"needs_deposit": not start_flagged})
    assert response.status_code == 409
    assert "error" in response.get_json()
    assert client.get(f"/equipment/{data['id']}").get_json()["needs_deposit"] is start_flagged

    # Even setting the flag to its current value is refused while locked
    assert client.patch(url, json={"needs_deposit": start_flagged}).status_code == 409

    # Returning the unit unlocks it
    assert client.put(f"/rentals/{rental.get_json()['id']}/return").status_code == 200
    unlocked = client.patch(url, json={"needs_deposit": not start_flagged})
    assert unlocked.status_code == 200
    assert unlocked.get_json()["needs_deposit"] is (not start_flagged)


def flags_by_id(client):
    """Helper: map every equipment id to its needs_deposit flag."""
    return {e["id"]: e["needs_deposit"] for e in client.get("/equipment").get_json()}


def test_bulk_deposit_flag_applies_to_category(client):
    """
        Bulk apply flags every item whose category matches exactly, leaves other
        categories alone, and can be undone.
    """
    canoe = create_equipment(client, name="Canoe", category="Hiking")
    boots = create_equipment(client, name="Boots", category="Hiking")
    tent = create_equipment(client, name="Tent", category="Camping")

    response = client.post("/equipment/deposit/bulk", json={"category": "Hiking", "needs_deposit": True})
    assert response.status_code == 200
    assert response.get_json() == {"updated": [canoe["id"], boots["id"]], "skipped": []}
    assert flags_by_id(client) == {canoe["id"]: True, boots["id"]: True, tent["id"]: False}

    off = client.post("/equipment/deposit/bulk", json={"category": "Hiking", "needs_deposit": False})
    assert off.status_code == 200
    assert flags_by_id(client) == {canoe["id"]: False, boots["id"]: False, tent["id"]: False}


@pytest.mark.parametrize("typed_category", ["hiking", "HIKING", " Hiking", "Hiking "])
def test_bulk_deposit_flag_category_match_is_exact(client, typed_category):
    """
        Category matching is exact: different case or surrounding spaces is a
        different category, so nothing is changed.
    """
    item = create_equipment(client, category="Hiking")
    response = client.post("/equipment/deposit/bulk", json={"category": typed_category, "needs_deposit": True})
    assert response.status_code == 200
    assert response.get_json() == {"updated": [], "skipped": []}
    assert flags_by_id(client) == {item["id"]: False}


def test_bulk_deposit_flag_skips_locked_items(client):
    """
        An item with a unit rented out is skipped and reported; the rest of the
        category is still updated.
    """
    rented = create_equipment(client, name="Canoe", category="Hiking")
    free = create_equipment(client, name="Boots", category="Hiking")
    renter = create_renter(client)
    assert client.post("/rentals", json={
        "equipment_id": rented["id"], "renter_id": renter["id"],
    }).status_code == 201

    response = client.post("/equipment/deposit/bulk", json={"category": "Hiking", "needs_deposit": True})
    assert response.status_code == 200
    assert response.get_json() == {"updated": [free["id"]], "skipped": [rented["id"]]}
    assert flags_by_id(client) == {rented["id"]: False, free["id"]: True}


def test_bulk_deposit_flag_skips_locked_item_already_at_target(client):
    """
        The lock has no exception: a locked item is skipped even if it already
        has the requested value.
    """
    item = create_flagged_equipment(client)
    renter = create_renter(client)
    assert client.post("/rentals", json={
        "equipment_id": item["id"], "renter_id": renter["id"], "deposit_amount": 10,
    }).status_code == 201

    response = client.post("/equipment/deposit/bulk", json={"category": "Hiking", "needs_deposit": True})
    assert response.get_json() == {"updated": [], "skipped": [item["id"]]}


def test_bulk_deposit_flag_no_matching_category(client):
    """
        A category with no items is a valid request with an empty result.
    """
    create_equipment(client, category="Hiking")
    response = client.post("/equipment/deposit/bulk", json={"category": "Boating", "needs_deposit": True})
    assert response.status_code == 200
    assert response.get_json() == {"updated": [], "skipped": []}


@pytest.mark.parametrize("bad_payload", [
    {},
    {"needs_deposit": True},                                  # missing category
    {"category": "Hiking"},                                   # missing needs_deposit
    {"category": "", "needs_deposit": True},
    {"category": "   ", "needs_deposit": True},
    {"category": None, "needs_deposit": True},
    {"category": 5, "needs_deposit": True},
    {"category": INVALID_DICT_VALUE, "needs_deposit": True},
    {"category": "Hiking", "needs_deposit": "yes"},
    {"category": "Hiking", "needs_deposit": 1},
    {"category": "Hiking", "needs_deposit": None},
])
def test_bulk_deposit_flag_invalid_input(client, bad_payload):
    """
        Bad input is a 400 and no item is changed.
    """
    create_equipment(client, category="Hiking")
    response = client.post("/equipment/deposit/bulk", json=bad_payload)
    assert response.status_code == 400
    assert set(flags_by_id(client).values()) == {False}


def assert_no_rental_created(client, equipment):
    """Helper: a rejected checkout must leave units and rentals untouched."""
    assert client.get("/rentals").get_json() == []
    reread = client.get(f"/equipment/{equipment['id']}").get_json()
    assert reread["available_units"] == equipment["available_units"]


@pytest.mark.parametrize("bad_deposit", [
    "missing",
    0,
    0.0,
    -5,
    "abc",
    None,
    True,
    INVALID_DICT_VALUE,
])
def test_checkout_flagged_equipment_rejects_bad_deposit(client, bad_deposit):
    """
        Flagged equipment needs a deposit greater than 0. A missing, zero,
        negative, or non-numeric deposit is rejected with a 400 and changes nothing.
    """
    equipment = create_flagged_equipment(client)
    renter = create_renter(client)

    payload = {"equipment_id": equipment["id"], "renter_id": renter["id"]}
    if bad_deposit != "missing":
        payload["deposit_amount"] = bad_deposit

    response = client.post("/rentals", json=payload)
    assert response.status_code == 400
    assert "error" in response.get_json()
    assert_no_rental_created(client, equipment)


def test_checkout_flagged_equipment_accepts_deposit(client):
    """
        Flagged equipment can be checked out with a deposit above 0, and the
        amount is stored on the rental.
    """
    equipment = create_flagged_equipment(client)
    renter = create_renter(client)

    response = client.post("/rentals", json={
        "equipment_id": equipment["id"],
        "renter_id": renter["id"],
        "deposit_amount": 50.0,
    })
    assert response.status_code == 201
    assert response.get_json()["deposit_amount"] == 50.0
    reread = client.get(f"/equipment/{equipment['id']}").get_json()
    assert reread["available_units"] == equipment["available_units"] - 1


def test_checkout_flagged_equipment_deposit_int_ok_bool_rejected(client):
    """
        bool is a subclass of int in Python, so True looks like a deposit of 1.
        A real integer deposit is accepted; True is rejected.
    """
    equipment = create_flagged_equipment(client, total_units=2)
    renter = create_renter(client)
    payload = {"equipment_id": equipment["id"], "renter_id": renter["id"]}

    rejected = client.post("/rentals", json={**payload, "deposit_amount": True})
    assert rejected.status_code == 400

    accepted = client.post("/rentals", json={**payload, "deposit_amount": 1})
    assert accepted.status_code == 201
    assert accepted.get_json()["deposit_amount"] == 1


def test_checkout_unflagged_equipment_needs_no_deposit(client):
    """
        Equipment without the flag can still be checked out with no deposit,
        or with one.
    """
    equipment = create_equipment(client)
    renter = create_renter(client)

    without = client.post("/rentals", json={"equipment_id": equipment["id"], "renter_id": renter["id"]})
    assert without.status_code == 201
    assert without.get_json()["deposit_amount"] == 0.0

    with_deposit = client.post("/rentals", json={
        "equipment_id": equipment["id"],
        "renter_id": renter["id"],
        "deposit_amount": 20.0,
    })
    assert with_deposit.status_code == 201
    assert with_deposit.get_json()["deposit_amount"] == 20.0


@pytest.mark.parametrize("bad_deposit", ["", "0", "-5", "abc"])
def test_ui_checkout_flagged_equipment_rejects_bad_deposit(client, bad_deposit):
    """
        The HTML checkout form enforces the same rule as the API: a flagged
        item with a missing, zero, negative or non-numeric deposit is rejected
        with a 400, shows an error, and changes nothing.
    """
    equipment = create_flagged_equipment(client)
    renter = create_renter(client)

    response = client.post("/ui/rentals", data={
        "equipment_id": equipment["id"],
        "renter_id": renter["id"],
        "deposit_amount": bad_deposit,
    })
    assert response.status_code == 400
    assert b"requires a deposit" in response.data
    assert_no_rental_created(client, equipment)


def test_ui_checkout_stores_deposit(client):
    """
        The HTML checkout form accepts a valid deposit on flagged equipment and
        stores it, and unflagged equipment needs no deposit.
    """
    flagged = create_flagged_equipment(client)
    plain = create_equipment(client, name="Tent")
    renter = create_renter(client)

    ok = client.post("/ui/rentals", data={
        "equipment_id": flagged["id"], "renter_id": renter["id"], "deposit_amount": "75.50",
    })
    assert ok.status_code == 302

    no_deposit = client.post("/ui/rentals", data={
        "equipment_id": plain["id"], "renter_id": renter["id"], "deposit_amount": "",
    })
    assert no_deposit.status_code == 302

    amounts = {r["equipment_id"]: r["deposit_amount"] for r in client.get("/rentals").get_json()}
    assert amounts == {flagged["id"]: 75.5, plain["id"]: 0.0}


def rent_one_unit(client, equipment):
    """Helper: check out one unit of the equipment through the API."""
    renter = create_renter(client)
    response = client.post("/rentals", json={
        "equipment_id": equipment["id"], "renter_id": renter["id"], "deposit_amount": 10,
    })
    assert response.status_code == 201


def test_ui_toggle_deposit_flag(client):
    """
        The equipment page toggles the flag on and off, and the change is persisted.
    """
    item = create_equipment(client)
    url = f"/ui/equipment/{item['id']}/deposit"

    assert client.post(url, data={"needs_deposit": "true"}).status_code == 302
    assert client.get(f"/equipment/{item['id']}").get_json()["needs_deposit"] is True

    assert client.post(url, data={"needs_deposit": "false"}).status_code == 302
    assert client.get(f"/equipment/{item['id']}").get_json()["needs_deposit"] is False


def test_ui_toggle_deposit_flag_locked(client):
    """
        With a unit rented out the page refuses the change (409), shows why,
        and leaves the flag as it was.
    """
    item = create_equipment(client, name="Canoe")
    rent_one_unit(client, item)

    response = client.post(f"/ui/equipment/{item['id']}/deposit", data={"needs_deposit": "true"})
    assert response.status_code == 409
    # Jinja escapes the apostrophe in "can't", so match the text after it
    assert b"change while units are rented out" in response.data
    assert b"Canoe" in response.data
    assert client.get(f"/equipment/{item['id']}").get_json()["needs_deposit"] is False


def test_ui_toggle_deposit_flag_invalid(client):
    """
        A missing item redirects away without error; a bad value is a 400 and
        changes nothing.
    """
    assert client.post("/ui/equipment/999/deposit", data={"needs_deposit": "true"}).status_code == 302

    item = create_equipment(client)
    for bad in [{}, {"needs_deposit": "yes"}, {"needs_deposit": ""}]:
        response = client.post(f"/ui/equipment/{item['id']}/deposit", data=bad)
        assert response.status_code == 400
        assert client.get(f"/equipment/{item['id']}").get_json()["needs_deposit"] is False


def test_equipment_page_shows_deposit_state(client):
    """
        The page shows a checked box for flagged items, an unchecked box for
        others, and a disabled box with a note for items that are rented out.
    """
    create_flagged_equipment(client, name="Flagged")
    create_equipment(client, name="Plain")
    rented = create_equipment(client, name="Rented")
    rent_one_unit(client, rented)

    html = client.get("/ui/equipment").get_data(as_text=True)
    assert html.count("checked") == 1
    assert html.count("disabled") == 1
    assert "locked while rented out" in html


def test_ui_bulk_deposit_flag_reports_skipped(client):
    """
        Bulk apply from the page updates unlocked items in the category and the
        follow-up page names what was skipped.
    """
    rented = create_equipment(client, name="Canoe", category="Hiking")
    free = create_equipment(client, name="Boots", category="Hiking")
    other = create_equipment(client, name="Tent", category="Camping")
    rent_one_unit(client, rented)

    response = client.post("/ui/equipment/deposit/bulk", data={"category": "Hiking", "needs_deposit": "true"})
    assert response.status_code == 302
    assert flags_by_id(client) == {rented["id"]: False, free["id"]: True, other["id"]: False}

    html = client.get("/ui/equipment").get_data(as_text=True)
    assert "Updated 1 item(s) in Hiking." in html
    assert "Skipped 1 because units are rented out: Canoe." in html

    # The message is shown once, not on every later visit
    assert "Updated 1 item(s)" not in client.get("/ui/equipment").get_data(as_text=True)


def test_ui_bulk_deposit_flag_unknown_category_and_bad_input(client):
    """
        A category with no items reports that; missing fields are a 400 and change nothing.
    """
    item = create_equipment(client, category="Hiking")

    client.post("/ui/equipment/deposit/bulk", data={"category": "Boating", "needs_deposit": "true"})
    assert "No equipment found in category Boating" in client.get("/ui/equipment").get_data(as_text=True)

    for bad in [{}, {"category": "Hiking"}, {"needs_deposit": "true"}, {"category": "Hiking", "needs_deposit": "yes"}]:
        assert client.post("/ui/equipment/deposit/bulk", data=bad).status_code == 400
    assert flags_by_id(client) == {item["id"]: False}


# =========================== END OF DEPOSIT TESTS ===========================


# ============================== RENTER TESTS ================================


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
