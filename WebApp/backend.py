import time
import json
import queue
import threading
from collections import deque
import psycopg2
import pandas as pd
from psycopg2.extras import RealDictCursor
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import paho.mqtt.client as mqtt
from datetime import datetime, timezone, timedelta

# --- LOCAL CONFIGURATION ---
MQTT_BROKER = "localhost" # Reverted to localhost for better WSL bridging
MQTT_PORT = 1883
MQTT_TOPIC = "medical/pump/#" # Subscribe broadly, filter carefully in _on_message

# PostgreSQL Config
PG_CONFIG = {
    "dbname": "med_db",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5432"
}

# InfluxDB Config
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "etcFwGBgL0rewRzKeVtVoSIE6v4mYwnKRypKMc5RiLSK-YmdHek1g_d0oUS7QqJ-AT_OSEXKvvNFLOVJf-9Fdw==" 
INFLUX_ORG = "IIEST, Shibpur"
INFLUX_BUCKET = "NewHW"

class DatabaseService:
    def __init__(self):
        self.pg_conn = None
        self.influx_client = None
        self.influx_write = None
        self.influx_query = None

    def connect(self):
        try:
            self.pg_conn = psycopg2.connect(**PG_CONFIG)
            self._init_pg_table()
            print(" PostgreSQL Connected")
        except Exception as e:
            print(f" PostgreSQL Error: {e}")

        try:
            self.influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            self._init_influx_bucket()
            self.influx_write = self.influx_client.write_api(write_options=SYNCHRONOUS)
            self.influx_query = self.influx_client.query_api()
            print(" InfluxDB Connected")
        except Exception as e:
            print(f" InfluxDB Error: {e}")

    def _init_pg_table(self):
        if not self.pg_conn: return
        with self.pg_conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS patients (
                    device_id TEXT PRIMARY KEY,
                    patient_name TEXT,
                    device_name TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            self.pg_conn.commit()

    def _init_influx_bucket(self):
        try:
            buckets_api = self.influx_client.buckets_api()
            bucket = buckets_api.find_bucket_by_name(INFLUX_BUCKET)
            if bucket is None:
                org_api = self.influx_client.organizations_api()
                orgs = org_api.find_organizations(org=INFLUX_ORG)
                if orgs:
                    buckets_api.create_bucket(bucket_name=INFLUX_BUCKET, org_id=orgs[0].id)
        except Exception as e:
            print(f" Influx bucket init failed: {e}")

    def add_patient(self, device_id, name, device_name):
        if not self.pg_conn: return False, "DB Not Connected"
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO patients (device_id, patient_name, device_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (device_id) DO UPDATE SET patient_name = EXCLUDED.patient_name;
                """, (device_id, name, device_name))
                self.pg_conn.commit()
            return True, "Registered Successfully"
        except Exception as e:
            return False, str(e)

    def get_patients(self):
        if not self.pg_conn: return []
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM patients")
                return cur.fetchall()
        except:
            return []

    def save_telemetry(self, data):
        if not self.influx_write: return
        try:
            p = Point("telemetry").tag("device_id", data.get("device_id")).tag("patient_name", data.get("patient_name", "Unknown"))
            for key, value in data.items():
                if key not in ["device_id", "patient_name", "timestamp", "device_name", "patient_id"]:
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        p = p.field(key, float(value))
                    else:
                        # Cast all non-numeric values (like strings, booleans, statuses) to strings
                        p = p.field(key, str(value))
            self.influx_write.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=p)
        except Exception as e:
            print(f"Influx Write Error: {e}")

    def get_history(self, device_id, start_dt, end_dt):
        if not self.influx_query: return pd.DataFrame()
        
        try:
            # Handle naive datetimes robustly by assuming they represent system local time
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
                
            # Add a buffer to the end time to mitigate clock drift and exclusive Flux boundaries
            end_dt = end_dt + timedelta(minutes=5)
            
            start_str = start_dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            end_str = end_dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            
            query = f'from(bucket: "{INFLUX_BUCKET}") |> range(start: {start_str}, stop: {end_str}) |> filter(fn: (r) => r["_measurement"] == "telemetry") |> filter(fn: (r) => r["device_id"] == "{device_id}") |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")'
            
            df_result = self.influx_query.query_data_frame(query)
            
            # InfluxDB separates string and float fields into a list of multiple dataframes.
            # We must merge them horizontally on the _time column to flatten the history logic.
            if isinstance(df_result, list):
                if not df_result:
                    return pd.DataFrame()
                
                merged_df = df_result[0]
                for i in range(1, len(df_result)):
                    # Drop duplicate metadata to prevent Pandas suffix collision (_x, _y)
                    drop_cols = [c for c in ['result', 'table', '_start', '_stop', '_measurement', 'device_id', 'patient_name'] if c in df_result[i].columns]
                    temp_df = df_result[i].drop(columns=drop_cols)
                    merged_df = pd.merge(merged_df, temp_df, on='_time', how='outer')
                return merged_df
                
            return df_result if df_result is not None else pd.DataFrame()
        except Exception as e:
            print(f"Influx Query Error: {e}")
            return pd.DataFrame()

class MQTTService:
    def __init__(self, db_service):
        # Handle API deprecations in newer paho-mqtt versions seamlessly
        try:
            from paho.mqtt.enums import CallbackAPIVersion
            self.client = mqtt.Client(CallbackAPIVersion.VERSION1)
        except ImportError:
            self.client = mqtt.Client()
            
        self.data_queue = queue.Queue()
        self.db = db_service
        self.device_heartbeats = {}
        self.latest_data = {} # Stores last known telemetry per device
        self.cgm_latest_data = {} # Stores last known CGM payload per device (topics ending with /cgm)
        self.cgm_history = {}  # device_id -> deque of recent /cgm payloads
        self.cgm_msg_count = {}  # device_id -> count
        self.cgm_last_seen = {}  # device_id -> epoch seconds
        self.last_valid_rpm = {} # Tracks the last valid actual_rpm per device
    def start(self):
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
            print(f" MQTT Service Started on {MQTT_BROKER}:{MQTT_PORT}")
        except Exception as e:
            print(f" MQTT Connection Error: {e}")

    def _on_connect(self, client, userdata, flags, rc, *args):
        if rc == 0:
            print(" MQTT Broker Connected Successfully!")
            client.subscribe(MQTT_TOPIC)
        else:
            print(f" MQTT Connection Failed with code: {rc}")

    def send_command(self, device_id, payload):
        """Publishes control commands to the device."""
        topic = f"medical/pump/{device_id}/host" # Host publishes strictly here
        try:
            info = self.client.publish(topic, json.dumps(payload))
            return info.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            print(f"MQTT Publish Error: {e}")
            return False

    def _on_message(self, client, userdata, msg):
        try:
            topic = msg.topic            # Strict filtering: accept device telemetry on /data and CGM payloads on /cgm
            topic_l = str(topic).lower()
            is_data = topic_l.endswith('/data')
            is_cgm = topic_l.endswith('/cgm') or topic_l.endswith('cgm')
            if (not is_data) and (not is_cgm):
                return
            payload = json.loads(msg.payload.decode())
            dev_id = payload.get("device_id")
            # Fallback: derive device_id from topic when payload omits it
            if not dev_id:
                try:
                    parts = str(topic).split('/')
                    # Expect: medical/pump/<device_id>/cgm or /data
                    if len(parts) >= 4 and parts[0] == 'medical' and parts[1] == 'pump':
                        dev_id = parts[2]
                        payload['device_id'] = dev_id
                except Exception:
                    dev_id = None
            
            payload['timestamp'] = datetime.now().strftime("%H:%M:%S")

            # Ensure caches exist (in case an older cached instance is running)
            if not hasattr(self, 'cgm_latest_data'):
                self.cgm_latest_data = {}
            if not hasattr(self, 'latest_data'):
                self.latest_data = {}
            if not hasattr(self, 'device_heartbeats'):
                self.device_heartbeats = {}
            
            if dev_id:
                # CGM payloads: store and skip /data-specific filters
                if is_cgm:
                    if not hasattr(self, 'cgm_latest_data'):
                        self.cgm_latest_data = {}
                    self.device_heartbeats[dev_id] = time.time()
                    self.cgm_latest_data[dev_id] = payload
                    if dev_id not in self.cgm_history:
                        self.cgm_history[dev_id] = deque(maxlen=360)  # ~30 min at 5s
                    self.cgm_history[dev_id].append(payload)
                    # Still persist to Influx for history views
                    # Use dedicated numeric fields to avoid Influx field-type conflicts on 'glucose'/'trend'.
                    payload_db = dict(payload)
                    try:
                        if 'glucose' in payload_db:
                            payload_db['cgm_glucose'] = float(payload_db.get('glucose'))
                    except Exception:
                        pass
                    try:
                        if 'trend' in payload_db:
                            payload_db['cgm_trend'] = float(payload_db.get('trend'))
                    except Exception:
                        pass
                    self.db.save_telemetry(payload_db)
                    return

                # --- FILTER LAYER: actual_rpm ---
                if "actual_rpm" in payload:
                    try:
                        rpm_val = float(payload["actual_rpm"])
                        if abs(rpm_val) > 50:  
                            # Spiked value detected: substitute or drop
                            if dev_id in self.last_valid_rpm:
                                payload["actual_rpm"] = self.last_valid_rpm[dev_id]
                            else:
                                del payload["actual_rpm"]
                        else:
                            # Clean value: safely record to memory
                            self.last_valid_rpm[dev_id] = rpm_val
                            payload["actual_rpm"] = rpm_val
                    except (ValueError, TypeError):
                        # Catches unparseable garbage strings
                        if dev_id in self.last_valid_rpm:
                            payload["actual_rpm"] = self.last_valid_rpm[dev_id]
                        else:
                            del payload["actual_rpm"]

                self.device_heartbeats[dev_id] = time.time()
                if is_cgm:
                    self.cgm_latest_data[dev_id] = payload
                    if dev_id not in self.cgm_history:
                        self.cgm_history[dev_id] = deque(maxlen=360)  # ~30 min at 5s
                    self.cgm_history[dev_id].append(payload)
                    self.cgm_msg_count[dev_id] = int(self.cgm_msg_count.get(dev_id, 0)) + 1
                    self.cgm_last_seen[dev_id] = time.time()
                else:
                    self.latest_data[dev_id] = payload # Update cache for formula calculations

            self.db.save_telemetry(payload)
            self.data_queue.put(payload)
            if self.data_queue.qsize() > 500: self.data_queue.get() 
        except Exception as e:
            pass
