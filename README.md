# NetMap

A local, single-user network inventory and topology app. It records what is on the network, where it sits, how it is cabled, and what changed — without scanning anything.

NetMap is deliberately manual. Every device, port, cable and address is entered or imported by a person, which makes it useful for documenting a real network without giving a tool permission to touch it.

## What it does

- **Live topology map** built with Cytoscape.js: device shapes by type, dashed Unknown far ends, outage hatching, search and filters, saved positions, multiple layouts and a client-side PNG export.
- **Spreadsheet-style ledgers** for devices, IP addresses, ports and cables: sort, filter, search, click-to-edit cells, and paste rows straight from Excel.
- **Subnet pages** with an address grid, usage counts and a next-free-address endpoint.
- **Rack elevations** grouped by site, building, room and rack, including unpositioned-device trays and over-occupied-unit warnings.
- **Device dossiers** with hardware identity, ports, addresses, cables, outage history and a field-by-field change trail.
- **Incident timeline** combining inventory changes and outages, with open incidents pinned in the margin and one-click close actions.
- **Spreadsheet import** from `.xlsx` or `.csv` with sheet choice, arbitrary column mapping, preview, cleanup, range expansion, placeholder creation and whole-batch undo.
- **Exports** to a formatted XLSX workbook, an A4 PDF inventory docket, and a topology PNG from the map.
- **Automatic change log** for locations, subnets, devices, IPs, ports, cables and outages, including the signed-in user where one exists.

## Stack

- Django 5.2 with PostgreSQL
- Django templates and HTMX 2.0.4
- Cytoscape.js 3.30.4
- `openpyxl` for XLSX import/export
- ReportLab for the PDF docket
- Local Bricolage Grotesque and IBM Plex Mono fonts

HTMX, Cytoscape and the fonts are vendored in `static/`, so the app runs without a CDN or an internet connection.

## Run it locally

### 1. Start PostgreSQL

The included Compose file runs PostgreSQL 16 on port **5433** so it does not collide with an existing local PostgreSQL service:

```bash
docker compose up -d
```

If you already have PostgreSQL, create a database and user matching `.env` instead.

### 2. Create the Python environment

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### 3. Configure the environment

```bash
cp .env.example .env
```

Generate a secret key and put it in `DJANGO_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

The defaults in `.env.example` match `compose.yaml`. Keep `DJANGO_DEBUG=1` for local development and leave `DJANGO_ALLOWED_HOSTS` limited to `127.0.0.1,localhost`.

### 4. Create the database schema and a login

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 5. Optional: load the fictional demo network

```bash
python manage.py seed_demo
```

This creates a small Riverside/Hilltop network with 7 devices, 4 subnets, 53 ports, 6 cables, 11 addresses and 2 outages. It is idempotent, so it is safe to run again. To wipe inventory records and reload the demo from scratch:

```bash
python manage.py seed_demo --reset
```

`--reset` deletes inventory and import records, but **does not delete auth users**.

### 6. Run the app

```bash
python manage.py runserver 127.0.0.1:8000
```

Open <http://127.0.0.1:8000/>. The server binds to loopback only.

## Importing a workbook

1. Open **Import** and choose an `.xlsx` or `.csv` file.
2. Choose a sheet and the target record type: devices, ports or connections.
3. Map each source column to a field. Headers are treated as hints, never trusted.
4. Review the preview. Each row is marked new, update or error before anything is written.
5. Commit the batch. If the result is wrong, use **Undo batch** to roll back that import only.

Cleanup rules:

- Whitespace is trimmed and blank cells, `NIL`, `n/a` and `N/A` become empty.
- Date-damaged cells and serial-number cells in text fields are flagged rather than guessed at.
- Port ranges such as `LAN2-7`, `19,20` and `4,5,7-12` expand into individual ports.
- Devices and ports are matched by serial number, asset ID, name or label where possible.
- Free-text references that cannot be matched become `UNNAMED-001`-style placeholder devices and ports, flagged for a later walk.

Only `.xlsx` and `.csv` files up to 10 MB are accepted. Macros, `.xls` and executable content are rejected. Uploaded files are stored under `media/imports/` and are never executed.

## Exports

- **XLSX** contains Summary, Devices, Ports, Cables, Subnets, IP addresses, Locations, Outages, Change log and Imports sheets. Text beginning with `=`, `+`, `-`, `@`, tab or carriage return is prefixed with `'` so a spreadsheet cannot execute inventory text as a formula.
- **PDF** produces an A4 inventory docket with a summary, device register, subnet register, address ledger and cable list.
- **Topology PNG** is rendered from the current map in the browser, so it reflects the active filters and layout.

## Tests

```bash
python manage.py test inventory -v 1
```

The suite covers model validation, subnet/IP rules, table editing, import cleanup and mapping, range expansion, placeholder matching, batch undo, change logging, topology filters and positions, device and rack views, timelines, outage management and the demo seed command.

## Project layout

```text
inventory/
  management/commands/seed_demo.py   fictional demo network
  migrations/                        schema history
  services/                          topology, racks, import, export, paste helpers
  tests/                             model and view test suites
  views/                             map, ledgers, subnets, racks, timeline, import/export
  forms.py                           model forms and inline editors
  imports.py                         workbook parsing and mapping engine
  models.py                          inventory models
  signals.py                         automatic change log
  tables.py                          declarative table definitions
  urls.py                            route registry
netmap/                              Django project and settings
static/                              CSS, JS, vendored HTMX/Cytoscape, local fonts
templates/                           base shell and inventory screens
compose.yaml                         local PostgreSQL 16 on port 5433
```

## Security and boundaries

- Local single-user app: log in, then work. All state-changing views require authentication and POST requests are CSRF-protected.
- Secrets come from `.env`, which is ignored by git. `.env.example` documents the required values.
- Uploads are size-limited, extension-checked and parsed with `openpyxl`/`csv`; they are never executed.
- There is no scanning, probing, credential collection or network discovery in this build. The `source` field has a reserved `Future discovery` value so a later read-only discovery phase can fit without changing the model.
- XLSX output is formula-injection-safe. PDF and XLSX exports are generated on demand from the local database and never uploaded anywhere.
- The server should be run on `127.0.0.1`. This is not a multi-tenant or internet-facing deployment.

## Current limits

- One local user account model; no teams, sharing or remote sync.
- Discovery is not implemented. All data is manual or imported.
- Rack elevation is a front view; no rear view or cable-management routing.
- The demo data is fictional and safe to commit.
