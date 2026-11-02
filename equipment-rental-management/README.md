\# Equipment Rental Management (ERM)

A small Flask REST API for tracking equipment, renters, and rentals. Data is
stored **in memory** (plain Python objects, no database) and is reset every
time the app restarts — this project is meant to run before you've covered
databases.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

The API runs at `http://127.0.0.1:5000`.

## Web UI

Open `http://127.0.0.1:5000/` in a browser for a basic HTML front end (plain
forms and tables, with one line of JavaScript for the deposit checkboxes) to
add/delete equipment and renters, set deposit requirements, and check
equipment in/out:

| Page | Path |
|---|---|
| Home | `/` |
| Equipment | `/ui/equipment` |
| Renters | `/ui/renters` |
| Rentals | `/ui/rentals` |

This UI is separate from the JSON API below — it's there so you can see the
app working without a REST client, and calls the same in-memory store.

## Deposits

Equipment can be marked as **needs deposit**. The marking decides what a
checkout must include:

- **Marked:** the deposit must be greater than 0, otherwise the checkout is
  rejected with a `400`. The employee enters the amount; there are no fixed
  amounts or store policy built in.
- **Not marked:** the deposit must be 0 (or left blank). Any other amount is
  rejected with a `400`.

How to set the marking:

- **Per item:** tick the "Needs deposit" checkbox on the Equipment page.
- **Per category:** use "Set Deposit for a Category" on the Equipment page. The
  category must match exactly (`Hiking` and `hiking` are different categories).
  Items that are currently rented out are skipped and listed in the result
  message.
- **Locked while rented out:** the marking can't be changed, on or off, while
  any unit of that item is rented out. Return all units first. The API
  responds with `409`.

## Entities

- **Equipment**: `id, name, category, total_units, available_units, is_available, needs_deposit`
- **Renter**: `id, name, email, membership_date`
- **Rental**: `id, equipment_id, renter_id, rental_date, due_date, return_date, deposit_amount, deposit_released`

## JSON API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/equipment` | List all equipment |
| POST | `/equipment` | Add an equipment item |
| GET | `/equipment/<id>` | Get one equipment item |
| PUT | `/equipment/<id>` | Update an equipment item |
| DELETE | `/equipment/<id>` | Delete an equipment item |
| GET | `/renters` | List all renters |
| POST | `/renters` | Create a renter |
| GET | `/renters/<id>` | Get one renter |
| PUT | `/renters/<id>` | Update a renter |
| DELETE | `/renters/<id>` | Delete a renter |
| PATCH | `/equipment/<id>/deposit` | Set whether the item needs a deposit (`{"needs_deposit": true}`); `409` if units are rented out |
| POST | `/equipment/deposit/bulk` | Set it for a whole category (`{"category": "Hiking", "needs_deposit": true}`); returns `{"updated": [ids], "skipped": [ids]}` |
| POST | `/rentals` | Check out equipment (`equipment_id`, `renter_id`, `deposit_amount`); the deposit must be > 0 if the item needs one and 0 if it doesn't |
| PUT | `/rentals/<id>/return` | Return rented equipment |
| GET | `/rentals?renter_id=&equipment_id=` | Look up rentals |

## Tests

```bash
pytest
```

Deposit tests are in `tests/test_Kevin_Wang.py`.

