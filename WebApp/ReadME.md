# WebApp for CLosed Loop Controlled Insulin Infusion Pump

The system provides centralized monitoring, live telemetry streaming, remote control, and historical data analysis.

---

## Features

* Real-time device telemetry monitoring
* Interactive time-series visualization
* Basal and Bolus rate calculation for pump
* Low-latency MQTT communication
* Hybrid database architecture (PostgreSQL + InfluxDB)
* Device registry and patient mapping
* Multi Sensor data accumulation
* Contol the insulin pump

---

## System Architecture

The application follows a decoupled architecture:

```
Device → MQTT Broker → Backend Services → Databases → Streamlit Frontend
```

### Core Technologies

| Layer          | Technology               |
| -------------- | ------------------------ |
| Frontend       | Streamlit (Python)       |
| Messaging      | MQTT                     |
| Relational DB  | PostgreSQL               |
| Time-Series DB | InfluxDB                 |

---

## Code Logic and Workflow

### 1. Communication Layer (MQTT Service)

* Maintains persistent connection to MQTT broker
* Subscribes to:

  ```
  medical/pump/+/data
  ```
* Publishes commands to:

  ```
  medical/pump/{device_id}/host
  ```



---

### 2. Storage Layer (Database Service)

#### PostgreSQL

* Stores:

  * Device ID (Primary Key)
  * Patient name
  * Device name


#### InfluxDB

* Stores telemetry as time-series data
* Uses:

  * Tags: device_id, patient_name
  * Fields: glucose, insulin_rate, etc.

---

### 3. Frontend Visualization (Streamlit)

* Real-time interface using Streamlit
* Optimized updates without full reload

 

---

## Infrastructure Setup Guide

### 1. MQTT Broker (mosquitto)

#### Installation

Ubuntu/Debian:

```bash
sudo apt install mosquitto mosquitto-clients
```

Windows:
Download from the official Eclipse Mosquitto website.

#### Run Broker

```bash
mosquitto -v
```

Default port: 1883

---

### 2. PostgreSQL Setup
* Install PostgreSQL for your operating system.

* Create database and user:

```sql
CREATE DATABASE telemetry_db;

CREATE USER db_admin WITH ENCRYPTED PASSWORD 'your_secure_password';

GRANT ALL PRIVILEGES ON DATABASE telemetry_db TO db_admin;
```

---

### 3. InfluxDB v2 Setup

* Install InfluxDB
* Open: http://localhost:8086
* Complete initial setup

Save:

* Organization Name
* Bucket Name
* API Token

Generate token from:

```
Data → API Tokens → All Access Token
```

---

### 4. Python Environment Setup

Requirements:

* Python 3.8 or higher

Install dependencies:

```bash
pip install streamlit pandas plotly psycopg2-binary influxdb-client paho-mqtt
```

---



## Run Application

```bash
streamlit run app.py
```

---

## Device Simulator Configuration

### Requirements

* Connect to the same MQTT broker
* Publish telemetry to:

  ```
  medical/pump/{device_id}/data
  ```
* Subscribe to:

  ```
  medical/pump/{device_id}/host
  ```

---

### Example Payload

```json
{
  "device_id": "CIIP001",
  "glucose": 120.5,
  "insulin_rate": 0.5,
  "battery_level": 95
}
```

---

### Steps

1. Start MQTT broker
2. Run device simulator
3. Register device in dashboard
4. View live data

---

## System Flow Summary

| Component | Topic | Action            |
| --------- | ----- | ----------------- |
| Device    | /data | Publish telemetry |
| Host      | /data | Subscribe         |
| Host      | /host | Send commands     |
| Device    | /host | Receive commands  |

---


## Currently on development stage.

## License

This project is for educational and research purposes.
