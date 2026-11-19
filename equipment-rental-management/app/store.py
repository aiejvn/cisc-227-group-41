"""In-memory data store.

Each "table" is just a dict mapping id -> object, kept in memory for the
lifetime of the running app. Data is lost when the app restarts. This keeps
the project approachable before students cover databases later in the
program, while still separating storage from the route/model code.
"""

equipment = {}
renters = {}
rentals = {}

_next_ids = {"equipment": 1, "renter": 1, "rental": 1}


def next_id(kind):
    id_ = _next_ids[kind]
    _next_ids[kind] += 1
    return id_


def reset():
    """Clear all data. Handy for resetting state between tests."""
    equipment.clear()
    renters.clear()
    rentals.clear()
    _next_ids.update(equipment=1, renter=1, rental=1)
