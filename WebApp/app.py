import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime, timedelta, timezone
import json
import re
import os
from backend import DatabaseService, MQTTService

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="InsulinPump OS", 
    page_icon="🩸", 
    layout="wide",
    initial_sidebar_state="expanded"
)


st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Background & Main Container */
    .main {
        background: linear-gradient(135deg, #0f111a 0%, #171926 100%);
    }

    /* Custom Scrollbar */
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: #0f111a; }
    ::-webkit-scrollbar-thumb { background: #2e303e; border-radius: 10px; }

    /* Glassmorphism Cards */
    .st-emotion-cache-12w0qpk { background-color: transparent !important; } 
    
    .card {
        background: rgba(30, 33, 48, 0.6);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        transition: all 0.3s ease;
    }
    
    .card:hover {
        border-color: rgba(0, 204, 150, 0.3);
        transform: translateY(-2px);
    }

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #0c0e14;
        border-right: 1px solid rgba(255,255,255,0.05);
    }
    
    .sidebar-brand {
        font-size: 22px;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: -0.5px;
        padding: 20px 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    /* Animation */
    @keyframes slideUp {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .animate-up { animation: slideUp 0.5s ease-out; }
    
    /* Control Section Custom Styling */
    .metric-value {
        font-family: monospace;
        color: #00cc96;
        font-size: 1.1em;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- BACKEND INITIALIZATION ---
@st.cache_resource
def get_backend():
    db = DatabaseService()
    db.connect()
    mqtt = MQTTService(db)
    mqtt.start()
    return db, mqtt

try:
    db, mqtt_service = get_backend()
except Exception as e:
    st.error(f"Failed to load system: {e}")
    st.stop()

# --- GLOBAL SESSION STATE ---
if 'global_device_id' not in st.session_state:
    st.session_state.global_device_id = None

# Unified function to handle device dropdowns and preserve state across sections
def get_selected_device(pts, key_prefix):
    if not pts: return None
    opts = {f"{p['patient_name']} - {p['device_name']} ({p['device_id']})": p['device_id'] for p in pts}
    options_list = list(opts.keys())
    
    # Pre-select based on global session memory
    default_index = 0
    if st.session_state.global_device_id in opts.values():
        default_index = list(opts.values()).index(st.session_state.global_device_id)
        
    selected_label = st.selectbox(
        "Select Target Device", 
        options_list, 
        index=default_index, 
        key=f"dev_sel_{key_prefix}",
        label_visibility="collapsed" if key_prefix != "hist" else "visible"
    )
    
    selected_id = opts[selected_label]
    st.session_state.global_device_id = selected_id
    return selected_id

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.markdown('<div class="sidebar-brand">🩸 InsulinPump OS</div>', unsafe_allow_html=True)
    
    nav = st.radio(
        "NAVIGATION", 
        ["Dashboard", "Live Monitor", "Device Control", "History", "Settings"],
        index=0,
        label_visibility="collapsed"
    )
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.caption("CORE STATUS")
    
    db_ok = db.pg_conn and db.influx_client
    mqtt_ok = mqtt_service.client.is_connected()
    
    st.markdown(f"""
        <div style="background: rgba(255,255,255,0.03); padding: 12px; border-radius: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 12px; color: #888;">Databases</span>
                <span style="color: {'#00cc96' if db_ok else '#ef553b'}; font-size: 12px; font-weight: 600;">{'ACTIVE' if db_ok else 'ERROR'}</span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 12px; color: #888;">MQTT Broker</span>
                <span style="color: {'#00cc96' if mqtt_ok else '#ef553b'}; font-size: 12px; font-weight: 600;">{'CONNECTED' if mqtt_ok else 'OFFLINE'}</span>
            </div>
        </div>
    """, unsafe_allow_html=True)


# --- VIEWS ---
def view_dashboard():
    st.markdown('<h1 class="animate-up">Fleet Command</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color: #888;">System-wide overview of all registered infusion pumps.</p>', unsafe_allow_html=True)
    
    pts = db.get_patients()
    now = time.time()
    active_count = 0
    status_map = {}
    
    for p in pts:
        did = p['device_id']
        last_seen = getattr(mqtt_service, 'device_heartbeats', {}).get(did, 0)
        is_online = (now - last_seen) < 30
        if is_online: active_count += 1
        status_map[did] = is_online

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""
            <div class="card" style="border-left: 4px solid #636efa;">
                <div style="color: #888; font-size: 12px; font-weight: 600; text-transform: uppercase;">Total Units</div>
                <div style="font-size: 32px; font-weight: 800; color: #fff;">{len(pts)}</div>
            </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
            <div class="card" style="border-left: 4px solid #00cc96;">
                <div style="color: #888; font-size: 12px; font-weight: 600; text-transform: uppercase;">Active Signals</div>
                <div style="font-size: 32px; font-weight: 800; color: #fff;">{active_count}</div>
            </div>
        """, unsafe_allow_html=True)
    with k3:
        offline = len(pts) - active_count
        st.markdown(f"""
            <div class="card" style="border-left: 4px solid #ef553b;">
                <div style="color: #888; font-size: 12px; font-weight: 600; text-transform: uppercase;">Disconnected</div>
                <div style="font-size: 32px; font-weight: 800; color: #fff;">{offline}</div>
            </div>
        """, unsafe_allow_html=True)
    with k4:
        st.markdown(f"""
            <div class="card" style="border-left: 4px solid #ab63fa;">
                <div style="color: #888; font-size: 12px; font-weight: 600; text-transform: uppercase;">Storage</div>
                <div style="font-size: 20px; font-weight: 800; color: #fff; margin-top: 10px;">TS: InfluxDB</div>
            </div>
        """, unsafe_allow_html=True)

    st.subheader("Device Registry")
    if not pts:
        st.info("No devices registered in the system.")
        return

    cols = st.columns(3)
    for i, p in enumerate(pts):
        is_on = status_map[p['device_id']]
        color = "#00cc96" if is_on else "#ef553b"
        shadow = "rgba(0, 204, 150, 0.1)" if is_on else "rgba(239, 85, 59, 0.05)"
        
        with cols[i % 3]:
            st.markdown(f"""
                <div style="background: rgba(30,33,48,0.4); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 20px; margin-bottom: 15px; box-shadow: 0 10px 30px {shadow};">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div>
                            <div style="color: #fff; font-weight: 600; font-size: 18px;">{p['patient_name']}</div>
                            <div style="color: #666; font-size: 12px;">{p['device_id']}</div>
                        </div>
                        <div style="background: {color}22; color: {color}; padding: 4px 8px; border-radius: 6px; font-size: 10px; font-weight: 800;">
                            {'ONLINE' if is_on else 'OFFLINE'}
                        </div>
                    </div>
                    <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid rgba(255,255,255,0.05); display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 12px; color: #888;">Hardware:</span>
                        <span style="font-size: 12px; color: #fff; font-weight: 500;">{p['device_name']}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)


@st.fragment(run_every=1)
def render_live_monitor_fragment(target_id):
    # Clear the buffer if the target device has changed
    if st.session_state.get('monitor_target') != target_id:
        st.session_state.monitor_target = target_id
        st.session_state.live_buffer = []
        st.session_state.focused_metric = None

    if 'focused_metric' not in st.session_state: st.session_state.focused_metric = None
    if 'live_buffer' not in st.session_state: st.session_state.live_buffer = []
    
    while hasattr(mqtt_service, 'data_queue') and not mqtt_service.data_queue.empty():
        msg = mqtt_service.data_queue.get()
        if msg.get('device_id') == target_id:
            st.session_state.live_buffer.append(msg)
            if len(st.session_state.live_buffer) > 100: 
                st.session_state.live_buffer.pop(0)

    data = st.session_state.live_buffer
    latest = data[-1] if data else {}

    # Removed 'status' and 'patient' from ignore so they can show up as non-numeric tags
    ignore = ['device_id', 'patient_name', 'device_name', 'timestamp', 'patient_id']
    
    num_keys = [k for k in latest.keys() if k not in ignore and isinstance(latest[k], (int, float))]
    num_keys.sort()
    
    non_num_keys = [k for k in latest.keys() if k not in ignore and not isinstance(latest[k], (int, float))]
    non_num_keys.sort()

    if not data:
        st.markdown("""
            <div style="text-align: center; padding: 100px 0;">
                <div style="color: #4e506e; font-size: 48px; margin-bottom: 20px;">📡</div>
                <div style="color: #888; font-size: 18px;">Listening for data from device...</div>
            </div>
        """, unsafe_allow_html=True)
    else:
        # Display Non-Numeric Status Variables gracefully
        if non_num_keys:
            with st.expander("Status Parameters", expanded=False):
                bullet_list = "".join([f"<li style='margin-bottom: 8px;'><span style='color: #aaa; font-size: 14px;'>{k.replace('_', ' ').upper()}:</span> <span style='color: #00cc96; font-weight: 600; font-size: 15px;'>{str(latest[k]).upper()}</span></li>" for k in non_num_keys])
                st.markdown(f"<ul style='padding-left: 20px;'>{bullet_list}</ul>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

        # Display Numeric Graphs / Selectors
        if num_keys:
            cols = st.columns(len(num_keys))
            for idx, key in enumerate(num_keys):
                val = latest[key]
                is_focused = (st.session_state.focused_metric == key)
                
                accent = "#4e506e"
                if "glucose" in key.lower(): accent = "#00cc96"
                elif "insulin" in key.lower(): accent = "#636efa"
                elif "battery" in key.lower(): accent = "#ffa15a"
                
                with cols[idx]:
                    btn_label = f"{key.replace('_', ' ').upper()}\n{val}"
                    if st.button(btn_label, key=f"btn_{key}", width="stretch"):
                        st.session_state.focused_metric = None if is_focused else key
                        st.rerun()

        show_keys = [st.session_state.focused_metric] if st.session_state.focused_metric else num_keys
        
        if show_keys:
            df = pd.DataFrame(data)
            fig = make_subplots(
                rows=len(show_keys), 
                cols=1, 
                shared_xaxes=True,
                vertical_spacing=0.1,
                subplot_titles=[k.replace('_', ' ').title() for k in show_keys]
            )
            
            for i, key in enumerate(show_keys):
                color = "#00cc96" if "glucose" in key.lower() else "#636efa"
                if "battery" in key.lower(): color = "#ffa15a"
                
                fig.add_trace(go.Scatter(
                    y=df[key],
                    mode='lines',
                    line=dict(width=4, color=color, shape='spline'),
                    fill='tozeroy',
                    fillcolor=f'rgba({",".join(map(str, [0, 204, 150] if "glucose" in key.lower() else [99, 110, 250]))}, 0.1)',
                    name=key
                ), row=i+1, col=1)

            fig.update_layout(
                height=300 * len(show_keys) if len(show_keys) > 1 else 500,
                margin=dict(l=20, r=20, t=60, b=20),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                showlegend=False,
                font=dict(color="#888", size=10)
            )
            fig.update_yaxes(showgrid=True, gridcolor='rgba(255,255,255,0.05)', zeroline=False)
            fig.update_xaxes(showgrid=False, visible=False)
            
            st.plotly_chart(fig, width="stretch", config={'displayModeBar': False})


def view_monitor():
    st.markdown('<h1 class="animate-up">Live Telemetry</h1>', unsafe_allow_html=True)
    
    pts = db.get_patients()
    if not pts:
        st.warning("No patients registered. Go to Settings to add a device.")
        return

    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        # Utilize the helper to remember selected device
        target_id = get_selected_device(pts, "monitor")
    
    last = getattr(mqtt_service, 'device_heartbeats', {}).get(target_id, 0)
    is_online = (time.time() - last) < 30
    
    with c2:
        st.markdown(f"""
            <div style="padding: 8px 15px; background: { '#00cc96' if is_online else '#ef553b'}15; 
            border: 1px solid {'#00cc96' if is_online else '#ef553b'}44; border-radius: 8px; 
            text-align: center; color: {'#00cc96' if is_online else '#ef553b'}; font-weight: 800; font-size: 14px;">
                {'● ONLINE' if is_online else '○ OFFLINE'}
            </div>
        """, unsafe_allow_html=True)
        
    with c3:
        active = st.toggle("Active Feed", value=True)

    st.markdown("<hr style='border: 0.5px solid rgba(255,255,255,0.05);'>", unsafe_allow_html=True)

    if active:
        render_live_monitor_fragment(target_id)
    else:
        st.info("Telemetry stream paused.")


# --- FORMULA STORAGE HELPERS ---
FORMULA_FILE = "saved_formulas.json"

def load_formulas():
    if os.path.exists(FORMULA_FILE):
        try:
            with open(FORMULA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_formula(device_id, formula_type, formula):
    formulas = load_formulas()
    if device_id not in formulas:
        formulas[device_id] = {}
    formulas[device_id][formula_type] = formula
    with open(FORMULA_FILE, "w") as f:
        json.dump(formulas, f)


def render_dynamic_calculator(calc_title, payload_key, live_data, target_id):
    st.markdown(f"#### {calc_title}")
    
    saved_formulas = load_formulas()
    saved_formula = saved_formulas.get(target_id, {}).get(payload_key, "")
    
    state_key = f"form_{target_id}_{payload_key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = saved_formula
        
    with st.expander("Add / Edit Formula", expanded=not bool(saved_formula)):
        formula = st.text_input("Formula Expression", placeholder="e.g., (glucose - 100) / 40 + carbs / 10", key=state_key)
        
        if st.button("💾 Save Formula", key=f"save_btn_{target_id}_{payload_key}", width="stretch"):
            save_formula(target_id, payload_key, formula)
            st.success("Formula saved securely! It will automatically load next time.")
            time.sleep(1)
            st.rerun()
    
    if formula.strip():
        var_names = set(re.findall(r'\b[a-zA-Z_]\w*\b', formula))
        built_ins = {'round', 'max', 'min', 'abs'}
        var_names = var_names - built_ins
        
        user_vars = {}
        if var_names:
            st.markdown("<div style='margin-top: 10px; color:#888; font-size:14px; margin-bottom:5px;'>Provide Variable Values:</div>", unsafe_allow_html=True)
            var_cols = st.columns(min(len(var_names), 4))
            for idx, var in enumerate(sorted(list(var_names))):
                default_val = float(live_data.get(var, 0.0))
                with var_cols[idx % 4]:
                    user_vars[var] = st.number_input(var, value=default_val, format="%.2f", step=0.1, key=f"in_{target_id}_{payload_key}_{var}")
        
        try:
            safe_env = {"__builtins__": None, "round": round, "max": max, "min": min, "abs": abs}
            safe_env.update(user_vars)
            
            result = eval(formula, safe_env)
            result = round(float(result), 3)
            
            st.markdown(f"""
                <div style="background: rgba(0,204,150,0.1); border: 1px solid rgba(0,204,150,0.3); border-radius: 8px; padding: 15px; margin-top: 15px; display: flex; justify-content: space-between; align-items: center;">
                    <div><span style="color:#00cc96; font-size: 14px;">Calculated {calc_title}:</span><br><span style="font-size: 24px; font-weight: 800; color: white;">{result} Units</span></div>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(f"Add to Command Payload", key=f"btn_add_{target_id}_{payload_key}", width="stretch"):
                st.session_state.payload_queue[payload_key] = result
                st.rerun()
                
        except ZeroDivisionError:
            st.error("Error: Division by zero detected in formula.")
        except Exception as e:
            st.error("Waiting for a valid mathematical formula... (check your syntax)")


@st.fragment(run_every=1)
def render_control_telemetry_fragment(target_id):
    """Real-time updating module specifically for the side panel of Control page."""
    mqtt_latest_data = getattr(mqtt_service, 'latest_data', {})
    live_data = mqtt_latest_data.get(target_id, {})
    
    with st.container(border=True):
        if live_data:
            ignored = ['device_id', 'patient_name', 'device_name', 'timestamp', 'patient_id'] # Removed status
            valid_vars = {k: v for k, v in live_data.items() if k not in ignored}
            
            if valid_vars:
                for k, v in valid_vars.items():
                    val_str = f"{v:.2f}" if isinstance(v, float) else str(v)
                    st.markdown(f"<div><span style='color:#888;'>{k}:</span> <span class='metric-value'>{val_str}</span></div>", unsafe_allow_html=True)
            else:
                st.info("No numerical variables yet.")
        else:
            st.warning("No data stream received yet.")


def view_control():
    st.markdown('<h1 class="animate-up">Device Command Center</h1>', unsafe_allow_html=True)
    
    pts = db.get_patients()
    if not pts:
        st.warning("No patients registered. Connect a device first.")
        return
        
    if 'payload_queue' not in st.session_state:
        st.session_state.payload_queue = {}
    if 'power_confirm' not in st.session_state:
        st.session_state.power_confirm = None
        
    # --- 1. DEVICE SELECTION & HEADER ---
    c1, c2 = st.columns([2, 1])
    with c1:
        # Utilize the helper to remember selected device
        target_id = get_selected_device(pts, "control")
        
    # Get a STATIC snapshot for calculator autocompletion
    mqtt_latest_data = getattr(mqtt_service, 'latest_data', {})
    live_data_static = mqtt_latest_data.get(target_id, {})
    
    mqtt_heartbeats = getattr(mqtt_service, 'device_heartbeats', {})
    is_online = (time.time() - mqtt_heartbeats.get(target_id, 0)) < 30
    
    if not is_online:
        st.error(f"**{target_id} is currently OFFLINE.** Transmission is disabled to ensure patient safety.")
    
    st.markdown("<hr style='border: 1px solid rgba(255,255,255,0.05); margin: 10px 0 30px 0;'>", unsafe_allow_html=True)
    
    # --- 2. MAIN LAYOUT ---
    left_col, right_col = st.columns([2.5, 1], gap="large")
    
    with left_col:
        st.markdown("### Power Operations")
        
        with st.container(border=True):
            p1, p2 = st.columns(2)
            with p1:
                if st.button("POWER ON", width="stretch", disabled=not is_online):
                    st.session_state.power_confirm = "ON"
            with p2:
                if st.button("POWER OFF", width="stretch", disabled=not is_online):
                    st.session_state.power_confirm = "OFF"
                    
            if st.session_state.power_confirm:
                state = st.session_state.power_confirm
                color = "#00cc96" if state == "ON" else "#ef553b"
                
                st.markdown(f"""
                <div style="background: rgba(255,161,90,0.1); border-left: 4px solid #ffa15a; padding: 15px; border-radius: 4px; margin-top: 15px;">
                    <strong style="color: #ffa15a;">Confirmation Required:</strong><br>
                    Do you want to turn the device <strong style="color: {color};">{state}</strong>?
                </div>
                """, unsafe_allow_html=True)
                
                conf1, conf2 = st.columns(2)
                with conf1:
                    if st.button(f"Yes, Confirm {state}", type="primary", width="stretch"):
                        with st.spinner("Transmitting..."):
                            success = mqtt_service.send_command(target_id, {"power": state})
                            if success:
                                st.success(f"Command successful: Device powered {state}")
                            else:
                                st.error("Failed to reach broker.")
                        st.session_state.power_confirm = None
                        time.sleep(1.5)
                        st.rerun()
                with conf2:
                    if st.button("Cancel", width="stretch"):
                        st.session_state.power_confirm = None
                        st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("### Configuration")
        
        tab_basal, tab_bolus = st.tabs(["Set Basal Rate", "Administer Bolus"])
        
        with tab_basal:
            render_dynamic_calculator("Basal Rate", "basal_rate", live_data_static, target_id)
            
        with tab_bolus:
            render_dynamic_calculator("Correction / Meal Bolus", "bolus_dose", live_data_static, target_id)

    # --- 3. RIGHT COLUMN: QUEUE & LIVE MONITORING ---
    with right_col:
        st.markdown("### Send Command")
        
        if not st.session_state.payload_queue:
            st.info("No commands generated. Add a dose from the configuration section.")
        else:
            with st.container(border=True):
                st.markdown("<div style='font-size:12px; color:#888;'>Command Payload</div>", unsafe_allow_html=True)
                st.json(st.session_state.payload_queue)
                
                if st.button("Clear Payload", width="stretch"):
                    st.session_state.payload_queue = {}
                    st.rerun()
                
            send_btn = st.button(
                "TRANSMIT COMMAND", 
                type="primary", 
                width="stretch", 
                disabled=not is_online or not st.session_state.payload_queue
            )
            
            if send_btn:
                with st.spinner("Transmitting..."):
                    success = mqtt_service.send_command(target_id, st.session_state.payload_queue)
                    if success:
                        st.success("Command transmitted.")
                        st.session_state.payload_queue = {} 
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Transmission failed.")
                        
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("### Live Telemetry")
        # Call the standalone updating fragment
        render_control_telemetry_fragment(target_id)


def view_history():
    st.markdown('<h1 class="animate-up">Medical Archives</h1>', unsafe_allow_html=True)
    pts = db.get_patients()
    if not pts:
        st.warning("No patients registered.")
        return
    
    with st.container():
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            target_id = get_selected_device(pts, "hist")
        
        # --- FIX: Store default times in session state so they don't overwrite user input ---
        if "hist_start_default" not in st.session_state:
            st.session_state.hist_start_default = datetime.now() - timedelta(hours=1)
        if "hist_end_default" not in st.session_state:
            st.session_state.hist_end_default = datetime.now()

        row2_c1, row2_c2 = st.columns(2)
        with row2_c1:
            st.caption("FROM")
            date_from = st.date_input("Start Date", value=st.session_state.hist_start_default.date())
            time_from = st.time_input("Start Time", value=st.session_state.hist_start_default.time())
        with row2_c2:
            st.caption("UPTO")
            date_to = st.date_input("End Date", value=st.session_state.hist_end_default.date())
            time_to = st.time_input("End Time", value=st.session_state.hist_end_default.time())

        st.markdown("<br>", unsafe_allow_html=True)
        fetch = st.button("Query Database", type="primary", width="stretch")

    if fetch:
        # Capture local system timezone to handle UTC conversion correctly
        local_tz = datetime.now().astimezone().tzinfo
        
        dt_from = datetime.combine(date_from, time_from).replace(tzinfo=local_tz)
        dt_to = datetime.combine(date_to, time_to).replace(tzinfo=local_tz)
        
        if dt_from >= dt_to:
            st.error("Invalid Range: 'From' time must be earlier than 'Upto' time.")
        else:
            with st.spinner("Processing Time-Series Data..."):
                # Send explicit Start and End dates to InfluxDB instead of calculating lookback
                df = db.get_history(target_id, dt_from, dt_to)
                
                if isinstance(df, list):
                    if len(df) == 0:
                        df = pd.DataFrame()
                    else:
                        df = pd.concat(df, ignore_index=True)
                
                if df.empty:
                    st.error("No telemetry records found for the requested time period.")
                else:
                    # Convert InfluxDB UTC timestamps back to Local Time for graphing
                    df['_time'] = pd.to_datetime(df['_time']).dt.tz_convert(local_tz)
                    
                    st.success(f"Retrieved {len(df)} matching samples")
                    
                    # Ensure we separate graphable numerics and text-based logs
                    num_cols = df.select_dtypes(include=['number']).columns.tolist()
                    num_cols = [c for c in num_cols if c not in ['result', 'table']]
                    
                    fig = go.Figure()
                    for c in num_cols:
                        color = "#00cc96" if "glucose" in c.lower() else None
                        fig.add_trace(go.Scatter(x=df['_time'], y=df[c], name=c.title(), line=dict(width=2, color=color)))
                    
                    fig.update_layout(
                        height=500, 
                        paper_bgcolor='rgba(0,0,0,0)', 
                        plot_bgcolor='rgba(30,33,48,0.3)', 
                        font=dict(color='#888'),
                        margin=dict(t=20),
                        xaxis=dict(gridcolor='rgba(255,255,255,0.05)', title='Timestamp'), 
                        yaxis=dict(gridcolor='rgba(255,255,255,0.05)', title='Measured Value'),
                        hovermode="x unified"
                    )
                    
                    st.plotly_chart(fig, width="stretch")
                    
                    # --- NEW: Extract and display non-numeric (status/text) parameters ---
                    non_num_cols = [c for c in df.columns if c not in num_cols and c not in ['_time', 'result', 'table', '_start', '_stop', '_measurement', 'device_id', 'patient_name']]
                    if non_num_cols:
                        st.markdown("### Status & Events Log")
                        # Format dataframe to highlight the exact times status changed or was logged
                        log_df = df[['_time'] + non_num_cols].copy()
                        log_df.rename(columns={'_time': 'Timestamp'}, inplace=True)
                        st.dataframe(log_df, width="stretch", hide_index=True)
                        st.markdown("<br>", unsafe_allow_html=True)

                    with st.expander("Diagnostic Table (Raw Data)"):
                        st.dataframe(df, width="stretch")

def view_setup():
    st.markdown('<h1 class="animate-up">System Settings</h1>', unsafe_allow_html=True)
    
    c1, c2 = st.columns([1, 1.5], gap="large")
    with c1:
        with st.form("registration_form"):
            st.markdown("### Device Enrollment")
            p_name = st.text_input("Patient Full Name", placeholder="John Doe")
            d_name = st.text_input("Hardware Model", placeholder="Medtronic 780G")
            d_id = st.text_input("Unique Device ID (Topic)", placeholder="pump_001")
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("Register Device", width="stretch"):
                if p_name and d_id:
                    success, msg = db.add_patient(d_id, p_name, d_name)
                    if success:
                        st.success(msg)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("Please fill all required fields.")
    
    with c2:
        st.markdown("### Active Registry")
        pts = db.get_patients()
        if pts:
            st.dataframe(
                pd.DataFrame(pts)[['patient_name', 'device_id', 'device_name', 'joined_at']], 
                width="stretch", 
                hide_index=True
            )
        else:
            st.info("Registry is currently empty.")

# --- ROUTING ---
if nav == "Dashboard": view_dashboard()
elif nav == "Live Monitor": view_monitor()
elif nav == "Device Control": view_control() 
elif nav == "History": view_history()
elif nav == "Settings": view_setup()
