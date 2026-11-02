"""
    Test renter features: adding and removing renters.

    Tests that submit invalid input assert a 4xx status AND that no state changed.
"""
from datetime import date

import pytest

INVALID_DICT_VALUE = {"example": "no input categories accept a dictionary. this should fail all of them"}


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
