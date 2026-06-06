# WebApp for Closed Loop Controlled Insulin Infusion Pump

Centralized monitoring + control web application for an insulin infusion pump ecosystem.

This project provides:
- Live telemetry monitoring (real-time charts)
- CGM streaming and visualization
- Remote device control (power/reset/basal/bolus)
- Meal detection (S** destabilization index) + optional auto-bolus delivery
- Historical querying and visualization

---

## Table of Contents

- Overview
- Architecture
- MQTT Topics
- Data Model and Storage
- Meal Detection and Auto-Bolus
- UI Pages
- Running the Stack
- Device/CGM Simulators
- Configuration
- Troubleshooting

---

## Overview

The system is built around a publish/subscribe workflow:

```
Device + Sensors  ->  MQTT Broker  ->  Backend Services  ->  Databases  ->  Streamlit Web UI
```

Key design decisions:
- MQTT is the real-time transport (low latency and simple routing by topic).
- PostgreSQL stores patient/device registry data.
- InfluxDB stores time-series telemetry (including CGM) for history views.
- Streamlit is used as the web UI with real-time fragments and Plotly charts.

---

## Architecture

### Components

- `app.py`
  - Streamlit frontend (Dashboard, Live Monitor, Patient Profile, Device Control, History, Settings)
  - Integrates meal detection and auto-bolus workflow
  - Stores user formulas and last bolus dose locally in JSON files

- `backend.py`
  - `DatabaseService`:
    - PostgreSQL: patient registry
    - InfluxDB: time-series storage and history queries
  - `MQTTService`:
    - Subscribes broadly and filters topics by suffix
    - Caches latest `/data` telemetry and latest `/cgm` payloads separately
    - Publishes host commands to `/host`

- `meal_detection_algo.py`
  - Implementation of the S** (S-star-star) destabilization index meal detector
  - Includes a streaming wrapper (`SStarStreamDetector`) so the algorithm can be used online

- `mealdetection.py`
  - Thin service layer used by `app.py`
  - Extracts glucose from incoming live payloads and drives the streaming detector

---


## Repository Layout (Files and Responsibilities)

This section explains what each key file does and which functions/classes matter most.

### Frontend

- `app.py`
  - Purpose:
    - Main Streamlit web application entrypoint.
    - Renders all UI pages and wires them to backend services.
  - Key responsibilities:
    - Device selection and routing between pages.
    - Live graphs (no-blink Plotly) and rolling windows.
    - Meal detection integration and auto-bolus flow.
    - History querying and signal selection.
    - UI theme (Dark/Light) and CSS overrides.
  - Important functions/sections:
    - `view_dashboard()`
    - `view_monitor()` and `render_live_monitor_fragment(target_id)` (live telemetry charts)
    - `view_patient_profile()` and `render_patient_profile_fragment(target_id)` (CGM view)
    - `view_control()` (commands + auto-bolus prompt)
    - `view_history()` (Influx history query + plotting)
    - `view_setup()` (device enrollment)
    - Local persistence helpers:
      - `saved_formulas.json` helpers (formula save/load)
      - `saved_doses.json` helpers (last bolus save/load)

### Backend / Services

- `backend.py`
  - Purpose:
    - Backend services used by the Streamlit UI.
    - Contains database and MQTT connectivity.
  - Key classes:
    - `DatabaseService`
      - `connect()` initializes PostgreSQL + InfluxDB clients.
      - `_init_pg_table()` ensures `patients` table exists.
      - `add_patient()` / `get_patients()` manage registry entries.
      - `save_telemetry(payload)` writes time-series fields into Influx.
      - `get_history(device_id, start_dt, end_dt)` queries Influx for history.
    - `MQTTService`
      - `start()` connects and subscribes to `medical/pump/#`.
      - `_on_message(...)` routes incoming topics:
        - `/data` -> `latest_data[device_id]`
        - `/cgm` -> `cgm_latest_data[device_id]` + `cgm_history[device_id]`
      - `send_command(device_id, payload)` publishes commands to `/host`.
  - Notes:
    - `/cgm` messages also write numeric-safe fields `cgm_glucose` and `cgm_trend` into Influx.

### Meal Detection {Needs Testing}

- `meal_detection_algo.py`
  - Purpose:
    - Core S** destabilization index algorithm implementation.
    - Includes a streaming wrapper so it can run online.
  - Key components:
    - `SStarConfig` (all algorithm timing parameters and threshold)
    - `compute_sstar_online(...)` (online S** computation)
    - `SStarStreamDetector` (rolling buffer + threshold-cross detection)

- `mealdetection.py`
  - Purpose:
    - Glue layer used by `app.py`.
    - Manages one streaming detector per device and extracts glucose values from payloads.
  - Key components:
    - `MealDetectionService.update(device_id, payload)` -> returns `{detected: bool, ...}`
    - Glucose key extraction supports common field names (`glucose`, `cgm`, `bg`, etc.).

### Simulators / Test Publishers

- `dummycgm.py`
  - Purpose:
    - Publishes dummy CGM samples to `medical/pump/{device_id}/cgm`.
    - Useful for testing Patient Profile and meal detection without real CGM hardware.

(Any pump simulator you use should publish pump telemetry to `/data` and subscribe to `/host`.)

### Local Storage Files

These files are created/updated by the webapp at runtime:
- `saved_formulas.json`
  - Stores user formulas per device and per parameter key (`basal_rate`, `bolus_dose`).
- `saved_doses.json`
  - Stores the last user-approved bolus dose per device for auto-bolus use.


## MQTT Topics

The backend subscribes to `medical/pump/#` and then routes messages based on the topic suffix.

### Telemetry Topics

- Device telemetry (pump sensors / general telemetry)

  ```
  medical/pump/{device_id}/data
  ```

- CGM telemetry (discrete glucose samples)

  ```
  medical/pump/{device_id}/cgm
  ```

Notes:
- The webapp treats `/cgm` as the authoritative CGM stream.
- The UI uses `/cgm` payloads for Patient Profile (CGM) and for meal detection input.

### Command Topic

- Host-to-device command channel

  ```
  medical/pump/{device_id}/host
  ```

Examples of command payload keys (depends on your device firmware):
- `power`: "ON" | "OFF"
- `reset_fault`: true
- `basal_rate`: float
- `bolus_dose`: float

---

## Data Model and Storage

### PostgreSQL (Registry)

Table: `patients`
- `device_id` (primary key)
- `patient_name`
- `device_name`
- `joined_at`

Used by:
- Settings page (register device)
- Device selection dropdowns across the UI

### InfluxDB (Time-series)

Measurement: `telemetry`

Tags:
- `device_id`
- `patient_name`

Fields:
- All numeric and non-numeric fields from incoming payloads (the backend casts non-numeric values to strings)

CGM reliability fields:
- When receiving `/cgm`, the backend additionally writes numeric-safe fields:
  - `cgm_glucose` (float)
  - `cgm_trend` (float)

This avoids InfluxDB field-type conflicts if `glucose`/`trend` arrive as mixed types in the past.

---

## Meal Detection and Auto-Bolus

### Meal Detection Pipeline

Meal detection is implemented using the S** destabilization index algorithm:
- A pure threshold on glucose is NOT used.
- The algorithm detects changes in the dynamical structure of the glucose signal.

Implementation:
- `meal_detection_algo.py` provides `SStarStreamDetector` (streaming wrapper).
- `mealdetection.py` provides `MealDetectionService`, which:
  - extracts glucose from the latest live payload
  - updates the streaming detector
  - returns a meal-detected event when the S** signal crosses the threshold

Sampling interval:
- `app.py` constructs the meal detector using a sampling interval that matches the CGM publish rate.
- If you change the CGM publish interval, update this value accordingly.

### UI Notification

When a meal is detected:
- The Live Monitor page shows a visible warning banner.
- A toast notification is attempted (if supported by your Streamlit version).

### Auto-Bolus Delivery

Behavior:
- If a meal is detected and the user has a previously saved `bolus_dose`, the webapp automatically publishes:

  ```json
  {"bolus_dose": <saved_value>}
  ```

- If no saved bolus exists, the Device Control page prompts the user to enter and save a bolus dose.

Saved user dose storage:
- `saved_doses.json` is used to persist the last user-approved bolus per device.

Important:
- Auto-bolus uses the last saved user dose (not a random value).

---

## UI Pages

### Dashboard

High-level overview widgets and device selection.

### Live Monitor

- Smooth rolling 2-minute chart window (old points slide out, new points slide in)
- Stable Plotly rendering (no blinking) using:
  - stable Streamlit chart keys
  - Plotly `uirevision`

Also handles:
- Meal detection input (prefers `/cgm` stream)
- Meal detected notices
- Auto-bolus triggering

### Patient Profile (CGM)

- Reads live `/cgm` payloads from the backend cache
- Displays numeric CGM payload fields as metric cards
- Discrete CGM chart (points + step-like lines)
- Rolling 5-minute window for clarity

### Device Control

- Power operations (ON/OFF), fault reset
- Basal and bolus calculation via formula editor
- Command payload builder with explicit "Transmit Command"
- If a meal was detected but no bolus is saved, prompts the user to enter and save/deliver bolus

Local formula storage:
- `saved_formulas.json` persists formula expressions per device and per parameter key.

### History

- Queries InfluxDB by date/time range
- Allows selecting which signals to plot via multiselect
- Persists the last fetched result in session state so UI interactions do not wipe the view

### Settings

- Device enrollment (register patient/device)
- Displays active registry table

---

## Running the Stack

### 1) Start MQTT Broker

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install mosquitto mosquitto-clients
mosquitto -v
```

Default port: `1883`

### 2) Setup PostgreSQL (Registry Database)

The application uses PostgreSQL only for the patient/device registry.

Current code expectation in `backend.py`:

```python
PG_CONFIG = {
    "dbname": "med_db",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5432"
}
```

You can either:
- keep these exact values and create PostgreSQL to match them, or
- change `PG_CONFIG` in `backend.py` to match your own PostgreSQL setup.

#### Install PostgreSQL (Ubuntu / WSL)

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

#### Start and enable PostgreSQL

```bash
sudo service postgresql start
sudo service postgresql status
```

If you want it to start automatically with your Linux environment:

```bash
sudo systemctl enable postgresql
```

#### Create the application database

Open the PostgreSQL shell as the `postgres` superuser:

```bash
sudo -u postgres psql
```

Inside `psql`, create the database:

```sql
CREATE DATABASE med_db;
```

If you want to use the default `postgres` user exactly as the code expects, set its password:

```sql
ALTER USER postgres WITH PASSWORD 'password';
```

Then exit:

```sql
\q
```

#### Verify login using the same values as the app

```bash
psql -h localhost -U postgres -d med_db -W
```

When prompted, enter:

```text
password
```

If login works, PostgreSQL is ready for the app.

#### What the app creates automatically

When the webapp starts, `DatabaseService.connect()` calls `_init_pg_table()` and creates this table automatically if it does not already exist:

```sql
CREATE TABLE IF NOT EXISTS patients (
    device_id TEXT PRIMARY KEY,
    patient_name TEXT,
    device_name TEXT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

So you do NOT need to create tables manually for the registry.

#### Common PostgreSQL issues

- `password authentication failed for user "postgres"`:
  - The password in PostgreSQL does not match `backend.py`.
- `database "med_db" does not exist`:
  - Create it with `CREATE DATABASE med_db;`
- connection refused on port `5432`:
  - PostgreSQL service is not running.

### 3) Setup InfluxDB v2 (Time-Series Database)

The application uses InfluxDB for all time-series telemetry and history queries.

Current code expectation in `backend.py`:

```python
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "<your token>"
INFLUX_ORG = "IIEST, Shibpur"
INFLUX_BUCKET = "NewHW"
```

You can either:
- create InfluxDB resources that match these values, or
- update `backend.py` to match your own InfluxDB org/bucket/token.

#### Install InfluxDB v2 (Ubuntu / WSL)

If InfluxDB is not already installed, use the official package instructions for your distro. On Ubuntu-based systems, the typical flow is:

```bash
wget -q https://repos.influxdata.com/influxdata-archive_compat.key
echo 'deb [signed-by=/etc/apt/keyrings/influxdata-archive_compat.gpg] https://repos.influxdata.com/ubuntu stable main' | sudo tee /etc/apt/sources.list.d/influxdb.list
sudo apt update
sudo apt install influxdb2 influxdb2-cli
```

If the keyring directory does not exist, create it first:

```bash
sudo mkdir -p /etc/apt/keyrings
```

#### Start and verify InfluxDB

```bash
sudo service influxdb start
sudo service influxdb status
```

You should then be able to open:

```text
http://localhost:8086
```

#### Initial InfluxDB UI setup

Open the InfluxDB web UI in your browser and complete the first-run setup.

You will be asked for:
- Username
- Password
- Organization
- Initial bucket

For easiest compatibility with the current code, use:
- Organization: `IIEST, Shibpur`
- Bucket: `NewHW`

If you choose different names, update:
- `INFLUX_ORG`
- `INFLUX_BUCKET`

in `backend.py`.

#### Create or copy an API token

After setup:
1. Open InfluxDB UI
2. Go to `Load Data` or `Data`
3. Open `API Tokens`
4. Create an `All Access Token` or a token with read/write access to your bucket
5. Copy that token

Then paste it into `backend.py`:

```python
INFLUX_TOKEN = "your_real_token_here"
```

#### Optional CLI verification

If the CLI is installed, set connection details:

```bash
influx config create \
  --config-name local \
  --host-url http://localhost:8086 \
  --org "IIEST, Shibpur" \
  --token "your_real_token_here" \
  --active
```

Verify buckets:

```bash
influx bucket list
```

You should see the bucket used by the app, for example:

```text
NewHW
```

#### What the app creates automatically

When `DatabaseService.connect()` runs:
- it connects to InfluxDB
- checks whether the configured bucket exists
- creates the bucket automatically if it is missing and the token has enough permissions

So in many cases, you only need:
- a running InfluxDB server
- a valid org
- a valid token

#### What the app stores in InfluxDB

Measurement:

```text
telemetry
```

Tags:
- `device_id`
- `patient_name`

Fields:
- all numeric telemetry fields
- all non-numeric telemetry fields as strings
- dedicated CGM-safe history fields:
  - `cgm_glucose`
  - `cgm_trend`

#### Common InfluxDB issues

- `InfluxDB Error: ... unauthorized`:
  - token is invalid or does not have access to the org/bucket
- `bucket not found`:
  - bucket name in `backend.py` does not match your actual bucket
- connection refused on `8086`:
  - InfluxDB service is not running
- history queries return no CGM values:
  - check that `/cgm` messages are being published and received
  - query a time range in which CGM was actually streaming
  - prefer `cgm_glucose` and `cgm_trend` in History because they are stored as guaranteed numeric fields

### 4) Check `backend.py` Configuration

Before running the app, confirm these values in `backend.py` match your actual local setup:

```python
PG_CONFIG = {
    "dbname": "med_db",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5432"
}

INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "your_real_token_here"
INFLUX_ORG = "IIEST, Shibpur"
INFLUX_BUCKET = "NewHW"
```

### 5) Install Python Dependencies

```bash
pip install streamlit pandas numpy plotly psycopg2-binary influxdb-client paho-mqtt
```

### 6) Run the Web App

```bash
streamlit run app.py
```

---

## Device/CGM Simulators

### Pump Telemetry Simulator (example contract)

Publish to:

```
medical/pump/{device_id}/data
```

Subscribe to:

```
medical/pump/{device_id}/host
```

Example `/data` payload:

```json
{
  "device_id": "CIIP003",
  "actual_rpm": 0,
  "position_deg": 180.58,
  "status": "stopped",
  "mode": "BASAL"
}
```

### Dummy CGM Publisher

Publish to:

```
medical/pump/{device_id}/cgm
```

Example `/cgm` payload:

```json
{
  "device_id": "CIIP003",
  "timestamp": "2026-05-21T13:02:52.256499",
  "glucose": 93.1,
  "trend": 2.3,
  "status": "OK"
}
```

---

## Configuration

Edit constants in `backend.py` as needed:
- `MQTT_BROKER`, `MQTT_PORT`
- `PG_CONFIG`
- `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET`

If you change your CGM publish rate:
- Update the `MealDetectionService(sampling_interval_min=...)` initialization in `app.py`.

---

## Troubleshooting / Current issues that needs to be fixed

### CGM not showing in Patient Profile

1) Confirm broker receives `/cgm`:

```bash
mosquitto_sub -h localhost -p 1883 -t 'medical/pump/+/cgm' -v
```

2) Confirm your payload includes `device_id` and numeric `glucose`.

3) Streamlit caching:
- Use the sidebar button `Reset Backend (MQTT)` to force Streamlit to recreate the cached backend services.

### Meal detection not triggering

- Ensure the detector sampling interval matches the CGM publish interval.
- Ensure CGM payloads contain a usable glucose field (`glucose` or `cgm`).
- The S** detector requires a warm-up history window before it can trigger.

### History does not show CGM signals

- Prefer selecting `cgm_glucose` / `cgm_trend` for CGM history, since they are guaranteed numeric fields.
- Ensure you query a time range where CGM messages were being published.

---

