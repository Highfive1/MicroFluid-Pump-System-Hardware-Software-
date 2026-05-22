import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime, timedelta, timezone
import json
import re
import os
from backend import DatabaseService, MQTTService
from mealdetection import MealDetectionService

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="InsulinPump OS", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- THEME STATE INITIALIZATION ---
if 'theme' not in st.session_state:
    st.session_state.theme = "Dark"

# Determine dynamic CSS variables
if st.session_state.theme == "Dark":
    theme_css = """
    :root {
        --bg-grad-1: #0f111a;
        --bg-grad-2: #171926;
        --card-bg: rgba(30, 33, 48, 0.6);
        --card-border: rgba(255, 255, 255, 0.08);
        --text-main: #ffffff;
        --text-sub: #888888;
        --sidebar-bg: #0c0e14;
        --accent-green: #00cc96;
        --accent-red: #ef553b;
        --accent-blue: #636efa;
        --accent-purple: #ab63fa;
        --accent-cyan: #19d3f3;
        --accent-orange: #ffa15a;
    }
    """
else:
    theme_css = """
    :root {
        --bg-grad-1: #f4f6f9;
        --bg-grad-2: #e4e9f2;
        --card-bg: #ffffff;
        --card-border: #d1d9e6;
        --text-main: #1a1a2e;
        --text-sub: #555566;
        --sidebar-bg: #f8f9fa;
        --accent-green: #00a076;
        --accent-red: #d33c24;
        --accent-blue: #404bdf;
        --accent-purple: #8a3cd9;
        --accent-cyan: #0babc4;
        --accent-orange: #e07b22;
    }
    """

# --- AGGRESSIVE GLOBAL UI STYLING ---
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');
    {theme_css}

    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}

    /* App background */
    .stApp, [data-testid="stAppViewContainer"] {{
        background: linear-gradient(135deg, var(--bg-grad-1) 0%, var(--bg-grad-2) 100%) !important;
        background-color: var(--bg-grad-1) !important;
    }}

    /* Keep text readable in both themes */
    body, p, h1, h2, h3, h4, h5, h6, span, label, li, div, .stMarkdown {{
        color: var(--text-main) !important;
    }}
    .text-sub, .text-sub * {{ color: var(--text-sub) !important; }}

    /* Sidebar */
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {{
        background-color: var(--sidebar-bg) !important;
        border-right: 1px solid var(--card-border) !important;
    }}

    /* Glass cards */
    [data-testid="stVerticalBlock"] > div {{ background-color: transparent !important; }}

    .card,
    [data-testid="stForm"],
    [data-testid="stExpander"] > details,
    [data-testid="stExpander"] > details > summary,
    [data-testid="stContainer"],
    .st-emotion-cache-12w0qpk {{
        background: var(--card-bg) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 12px !important;
    }}

    .card {{ padding: 20px; margin-bottom: 20px; transition: all 0.25s ease; }}
    .card:hover {{ border-color: var(--accent-green) !important; transform: translateY(-2px); }}

    /* Divider */
    hr {{ border-color: var(--card-border) !important; }}

    /* Inputs */
    div[data-baseweb="select"] > div,
    input[type="text"],
    input[type="number"],
    textarea,
    .stNumberInput input {{
        background-color: var(--card-bg) !important;
        color: var(--text-main) !important;
        border: 1px solid var(--card-border) !important;
    }}

    /* Selectbox text/icon fix (BaseWeb) */
    div[data-baseweb="select"] * {{
        color: var(--text-main) !important;
    }}
    div[data-baseweb="select"] input {{
        caret-color: var(--text-main) !important;
    }}
    div[data-baseweb="select"] svg {{
        fill: var(--text-main) !important;
    }}
    /* Placeholder-ish text inside select */
    div[data-baseweb="select"] span {{
        color: var(--text-main) !important;
    }}

    
    /* Input caret + placeholder + focus (Light mode especially) */
    input, textarea {{ caret-color: var(--text-main) !important; }}
    input::placeholder, textarea::placeholder {{ color: var(--text-sub) !important; opacity: 0.85; }}
    input:focus, textarea:focus, .stNumberInput input:focus {{
        outline: none !important;
        box-shadow: 0 0 0 3px rgba(64, 75, 223, 0.18) !important;
        border-color: var(--accent-blue) !important;
    }}
    *:focus-visible {{ outline: none !important; }}
/* BaseWeb popovers (select dropdowns, menus) */

    /* Date picker / calendar popover (BaseWeb) */
    div[data-baseweb="calendar"],
    div[data-baseweb="calendar"] > div {{
        background: var(--card-bg) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 12px !important;
    }}
    div[data-baseweb="calendar"] * {{
        color: var(--text-main) !important;
    }}

    /* calendar header/nav */
    div[data-baseweb="calendar"] [role="navigation"],
    div[data-baseweb="calendar"] [role="banner"],
    div[data-baseweb="calendar"] header,
    div[data-baseweb="calendar"] nav,
    div[data-baseweb="calendar"] [aria-label*="Month"],
    div[data-baseweb="calendar"] [aria-label*="Year"],
    div[data-baseweb="calendar"] [aria-label*="month"],
    div[data-baseweb="calendar"] [aria-label*="year"] {{
        background: var(--card-bg) !important;
        background-color: var(--card-bg) !important;
    }}
    div[data-baseweb="calendar"] [role="navigation"] * {{
        color: var(--text-main) !important;
        fill: var(--text-main) !important;
    }}

    /* calendar wrapper overrides (fix dark header strip) */
    div[data-baseweb="calendar"] > div,
    div[data-baseweb="calendar"] > div > div,
    div[data-baseweb="calendar"] > div > div > div {{
        background: var(--card-bg) !important;
        background-color: var(--card-bg) !important;
    }}
    div[data-baseweb="calendar"] [role="grid"],
    div[data-baseweb="calendar"] [role="rowgroup"],
    div[data-baseweb="calendar"] [role="row"] {{
        background: var(--card-bg) !important;
        background-color: var(--card-bg) !important;
    }}
    div[data-baseweb="calendar"] button {{
        background: transparent !important;
        border-radius: 10px !important;
    }}
    div[data-baseweb="calendar"] button:hover {{
        background: var(--bg-grad-2) !important;
    }}

    /* calendar day selection fixes */
    div[data-baseweb="calendar"] button[aria-selected="true"],
    div[data-baseweb="calendar"] button[aria-current="date"] {{
        background: var(--accent-blue) !important;
        background-color: var(--accent-blue) !important;
        color: #ffffff !important;
        border: 1px solid var(--accent-blue) !important;
        box-shadow: none !important;
        outline: none !important;
    }}
    div[data-baseweb="calendar"] button:focus,
    div[data-baseweb="calendar"] button:focus-visible {{
        outline: none !important;
        box-shadow: none !important;
    }}

    /* remove dark stray blocks inside calendar popover */
    div[data-baseweb="calendar"] input,
    div[data-baseweb="calendar"] textarea {{
        background: transparent !important;
        background-color: transparent !important;
        border: 0 !important;
        box-shadow: none !important;
        color: transparent !important;
        caret-color: transparent !important;
    }}
    div[data-baseweb="calendar"] div {{
        background-color: transparent;
    }}
    div[data-baseweb="calendar"] > div,
    div[data-baseweb="calendar"] > div * {{
        background-clip: padding-box;
    }}
    div[data-baseweb="calendar"] button[aria-selected="true"],
    div[data-baseweb="calendar"] button[aria-current="date"] {{
        background: var(--accent-blue) !important;
        color: #ffffff !important;
    }}

    /* DataFrame (Glide Data Grid) theme vars */
    [data-testid="stDataFrame"],
    [data-testid="stDataFrame"] > div {{
        background: var(--card-bg) !important;
    }}
    [data-testid="stDataFrame"] {{
        --gdg-bg-cell: var(--card-bg);
        --gdg-bg-cell-medium: var(--card-bg);
        --gdg-bg-header: var(--bg-grad-2);
        --gdg-bg-header-hovered: var(--bg-grad-2);
        --gdg-bg-header-selected: var(--bg-grad-2);
        --gdg-text-dark: var(--text-main);
        --gdg-text-medium: var(--text-sub);
        --gdg-border-color: var(--card-border);
        --gdg-accent-color: var(--accent-blue);
    }}
    [data-testid="stDataFrame"] [role="grid"],
    [data-testid="stDataFrame"] canvas {{
        background: var(--card-bg) !important;
    }}

    div[data-baseweb="popover"],
    div[data-baseweb="popover"] > div,
    ul[role="listbox"],
    ul[data-baseweb="menu"] {{
        background-color: var(--card-bg) !important;
        border: 1px solid var(--card-border) !important;
        box-shadow: 0 16px 60px rgba(0,0,0,0.18) !important;
    }}
    div[data-baseweb="popover"] * {{ color: var(--text-main) !important; }}
    li[role="option"] {{ background-color: var(--card-bg) !important; color: var(--text-main) !important; }}
    li[role="option"]:hover, li[role="option"][aria-selected="true"] {{
        background-color: var(--bg-grad-2) !important;
        color: var(--accent-green) !important;
    }}

    /* Buttons */
    .stButton button,
    [data-testid="stFormSubmitButton"] button,
    button[kind="primary"],
    button[kind="secondaryFormSubmit"] {{
        background-color: var(--card-bg) !important;
        color: var(--text-main) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 10px !important;
        transition: transform 0.12s ease, border-color 0.12s ease, color 0.12s ease;
    }}
    .stButton button:hover,
    [data-testid="stFormSubmitButton"] button:hover,
    button[kind="primary"]:hover,
    button[kind="secondaryFormSubmit"]:hover {{
        border-color: var(--accent-green) !important;
        color: var(--accent-green) !important;
        transform: translateY(-1px);
    }}

    /* Tabs */
    [data-baseweb="tab-list"] {{
        gap: 8px;
        background: transparent !important;
    }}
    button[data-baseweb="tab"] {{
        background: var(--card-bg) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 999px !important;
        padding: 8px 14px !important;
        color: var(--text-main) !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        border-color: var(--accent-blue) !important;
        box-shadow: 0 10px 24px rgba(0,0,0,0.12);
    }}

    /* Toggle / checkbox / radio readability */
    [data-testid="stToggle"],
    [data-testid="stCheckbox"],
    [data-testid="stRadio"] {{
        background: transparent !important;
    }}

    /* Dataframe: fix Light-mode contrast */
    [data-testid="stDataFrame"] {{
        background: var(--card-bg) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 12px !important;
        overflow: hidden;
    }}
    [data-testid="stDataFrame"] * {{
        color: var(--text-main) !important;
    }}

    /* Streamlit alerts */
    [data-testid="stAlert"] {{
        border-radius: 12px !important;
        border: 1px solid var(--card-border) !important;
        background: var(--card-bg) !important;
    }}

    .metric-value {{
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        color: var(--accent-green) !important;
        font-size: 1.1em;
        font-weight: 700;
    }}

    /* Small entrance animation */
    .animate-up {{
        animation: riseIn 360ms ease-out both;
    }}
    @keyframes riseIn {{
        from {{ transform: translateY(6px); opacity: 0; }}
        to   {{ transform: translateY(0); opacity: 1; }}
    }}
</style>
""", unsafe_allow_html=True)

# Disable browser spellcheck underlines on inputs (looks like red squiggles in Light mode)
def disable_spellcheck():
    components.html("""
    <script>
    (function(){
      function apply(){
        const nodes = window.parent.document.querySelectorAll('input, textarea');
        nodes.forEach(n => {
          try { n.setAttribute('spellcheck','false'); } catch(e) {}
        });
      }
      apply();
      setInterval(apply, 2000);
    })();
    </script>
    """, height=0, width=0)

disable_spellcheck()

# Helper function to get theme-specific colors for Plotly charts
def get_theme_vars():
    is_dark = st.session_state.theme == "Dark"
    return {
        'plot_bg': 'rgba(15,17,26,0.6)' if is_dark else 'rgba(255,255,255,0.9)',
        'plot_grid': 'rgba(255,255,255,0.1)' if is_dark else 'rgba(0,0,0,0.08)',
        'plot_line': 'rgba(255,255,255,0.2)' if is_dark else 'rgba(0,0,0,0.15)',
        'plot_text': '#888888' if is_dark else '#555566',
        'polar_bg': 'rgba(15,17,26,0.3)' if is_dark else 'rgba(240,242,246,0.5)',
        'accent_green': '#00cc96' if is_dark else '#00a076',
        'accent_blue': '#636efa' if is_dark else '#404bdf',
        'accent_orange': '#ffa15a' if is_dark else '#e07b22',
        'accent_cyan': '#19d3f3' if is_dark else '#0babc4',
        'accent_purple': '#ab63fa' if is_dark else '#8a3cd9',
        'accent_red': '#ef553b' if is_dark else '#d33c24'
    }

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

if 'meal_detector' not in st.session_state:
    # Per-session detector state (avoids cross-user/thread issues)
    # Meal detector sampling must match CGM publish rate. Dummy CGM publishes every 5 seconds.
    st.session_state.meal_detector = MealDetectionService(sampling_interval_min=(5.0 / 60.0))

if 'meal_notices' not in st.session_state:
    st.session_state.meal_notices = {}

if 'autobolus_sent' not in st.session_state:
    st.session_state.autobolus_sent = {}

if 'meal_needs_bolus' not in st.session_state:
    st.session_state.meal_needs_bolus = {}

def get_selected_device(pts, key_prefix):
    if not pts: return None
    opts = {f"{p['patient_name']} - {p['device_name']} ({p['device_id']})": p['device_id'] for p in pts}
    options_list = list(opts.keys())
    
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

# Theme Update Callback
def update_theme():
    st.session_state.theme = st.session_state.theme_selector

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.markdown('<div style="font-size: 20px; font-weight: 800; border-bottom: 1px solid var(--card-border); padding-bottom: 20px; margin-bottom: 20px;">INSULIN PUMP OS</div>', unsafe_allow_html=True)
    
    st.radio(
        "APPEARANCE", 
        ["Dark", "Light"],
        index=0 if st.session_state.theme == "Dark" else 1,
        horizontal=True,
        key="theme_selector",
        on_change=update_theme
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    nav = st.radio(
        "NAVIGATION", 
        ["Dashboard", "Live Monitor", "Patient Profile", "Device Control", "History", "Settings"],
        index=0,
        label_visibility="collapsed"
    )
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.caption("CORE STATUS")

    if st.button('Reset Backend (MQTT)', width='stretch'):
        st.cache_resource.clear()
        st.rerun()

    
    db_ok = db.pg_conn and db.influx_client
    mqtt_ok = mqtt_service.client.is_connected()
    
    status_color_db = "var(--accent-green)" if db_ok else "var(--accent-red)"
    status_color_mqtt = "var(--accent-green)" if mqtt_ok else "var(--accent-red)"
    
    st.markdown(f"""
        <div style="background: var(--card-bg); border: 1px solid var(--card-border); padding: 12px; border-radius: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 12px;" class="text-sub">Databases</span>
                <span style="color: {status_color_db}; font-size: 12px; font-weight: 600;">{'ACTIVE' if db_ok else 'ERROR'}</span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 12px;" class="text-sub">MQTT Broker</span>
                <span style="color: {status_color_mqtt}; font-size: 12px; font-weight: 600;">{'CONNECTED' if mqtt_ok else 'OFFLINE'}</span>
            </div>
        </div>
    """, unsafe_allow_html=True)


# --- VIEWS ---
def view_dashboard():
    st.markdown('<h1 class="animate-up">Fleet Command</h1>', unsafe_allow_html=True)
    st.markdown('<p class="text-sub">System-wide overview of all registered infusion pumps.</p>', unsafe_allow_html=True)
    
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
            <div class="card" style="border-left: 4px solid var(--accent-blue);">
                <div class="text-sub" style="font-size: 12px; font-weight: 600; text-transform: uppercase;">Total Units</div>
                <div style="font-size: 32px; font-weight: 800; color: var(--text-main);">{len(pts)}</div>
            </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
            <div class="card" style="border-left: 4px solid var(--accent-green);">
                <div class="text-sub" style="font-size: 12px; font-weight: 600; text-transform: uppercase;">Active Signals</div>
                <div style="font-size: 32px; font-weight: 800; color: var(--text-main);">{active_count}</div>
            </div>
        """, unsafe_allow_html=True)
    with k3:
        offline = len(pts) - active_count
        st.markdown(f"""
            <div class="card" style="border-left: 4px solid var(--accent-red);">
                <div class="text-sub" style="font-size: 12px; font-weight: 600; text-transform: uppercase;">Disconnected</div>
                <div style="font-size: 32px; font-weight: 800; color: var(--text-main);">{offline}</div>
            </div>
        """, unsafe_allow_html=True)
    with k4:
        st.markdown(f"""
            <div class="card" style="border-left: 4px solid var(--accent-purple);">
                <div class="text-sub" style="font-size: 12px; font-weight: 600; text-transform: uppercase;">Storage</div>
                <div style="font-size: 20px; font-weight: 800; color: var(--text-main); margin-top: 10px;">TS: InfluxDB</div>
            </div>
        """, unsafe_allow_html=True)

    st.subheader("Device Registry")
    if not pts:
        st.info("No devices registered in the system.")
        return

    cols = st.columns(3)
    for i, p in enumerate(pts):
        is_on = status_map[p['device_id']]
        color = "var(--accent-green)" if is_on else "var(--accent-red)"
        
        with cols[i % 3]:
            st.markdown(f"""
                <div class="card" style="margin-bottom: 15px; padding: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div>
                            <div style="color: var(--text-main); font-weight: 600; font-size: 18px;">{p['patient_name']}</div>
                            <div class="text-sub" style="font-size: 12px;">{p['device_id']}</div>
                        </div>
                        <div style="color: {color}; border: 1px solid {color}; padding: 4px 8px; border-radius: 6px; font-size: 10px; font-weight: 800;">
                            {'[ ACTIVE ]' if is_on else '[ INACTIVE ]'}
                        </div>
                    </div>
                    <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid var(--card-border); display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 12px;" class="text-sub">Hardware:</span>
                        <span style="font-size: 12px; color: var(--text-main); font-weight: 500;">{p['device_name']}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)


@st.fragment(run_every=5)
def render_patient_profile_fragment(target_id):
    ist_tz = timezone(timedelta(hours=5, minutes=30), name="IST")
    tv = get_theme_vars()

    mqtt_cgm = getattr(mqtt_service, 'cgm_latest_data', {})
    payload = mqtt_cgm.get(target_id, {})

    if not isinstance(payload, dict) or not payload:
        st.info('INFO: Waiting for CGM telemetry on MQTT topics ending with /cgm ...')
        with st.expander('CGM Diagnostics'):
            all_cgm = getattr(mqtt_service, 'cgm_latest_data', {})
            st.write('cgm_latest_data device_ids:', list(all_cgm.keys()) if isinstance(all_cgm, dict) else str(type(all_cgm)))
            if isinstance(all_cgm, dict) and all_cgm:
                # Show one sample payload
                any_dev = next(iter(all_cgm.keys()))
                st.write('Sample device_id:', any_dev)
                st.json(all_cgm.get(any_dev))
            st.write('Selected device_id:', target_id)
            st.write('MQTT connected:', mqtt_service.client.is_connected() if hasattr(mqtt_service, 'client') else None)
            st.write('backend last_mqtt_error:', getattr(mqtt_service, 'last_mqtt_error', None))
        return

    # Show all numeric values from /cgm payload (except identifiers)
    ignored = {'device_id', 'patient_name', 'device_name', 'timestamp', 'patient_id'}
    numeric = {}
    for k, v in payload.items():
        if k in ignored:
            continue
        try:
            if isinstance(v, bool):
                continue
            fv = float(v)
            if np.isfinite(fv):
                numeric[k] = fv
        except Exception:
            continue

    if not numeric:
        st.warning('CGM payload received on /cgm but contains no numeric fields to display.')
        st.json(payload)
        return

    cols = st.columns(min(len(numeric), 4))
    for i, (k, v) in enumerate(sorted(numeric.items())):
        with cols[i % len(cols)]:
            st.markdown(
                f"<div class='card'>"
                f"<div class='text-sub' style='font-size:12px; font-weight:700;'>{k.replace('_',' ').upper()}</div>"
                f"<div style='font-size:34px; font-weight:900;'>{v:.2f}</div>"
                f"</div>",
                unsafe_allow_html=True
            )


    # Live CGM chart from MQTT /cgm stream (discrete samples)
    cgm_hist = getattr(mqtt_service, 'cgm_history', {})
    hist = cgm_hist.get(target_id) if isinstance(cgm_hist, dict) else None

    points = []
    if hist:
        for row in list(hist):
            if not isinstance(row, dict):
                continue
            ts = row.get('timestamp')
            g = row.get('glucose') if 'glucose' in row else row.get('cgm')
            try:
                g = float(g)
            except Exception:
                continue
            if ts is None:
                continue
            points.append((ts, g))

    if points:
        dfp = pd.DataFrame(points, columns=['timestamp', 'glucose'])
        # dummycgm sends ISO timestamps in UTC
        dfp['timestamp'] = pd.to_datetime(dfp['timestamp'], errors='coerce', utc=True).dt.tz_convert(ist_tz)
        dfp = dfp.dropna(subset=['timestamp']).sort_values('timestamp')
        # Keep only last 5 minutes for a clean, real-time window
        cutoff = datetime.now(ist_tz) - timedelta(minutes=5)
        dfp = dfp[dfp['timestamp'] >= cutoff]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dfp['timestamp'],
            y=dfp['glucose'],
            mode='markers+lines',
            line=dict(width=1, color=tv['accent_green'], shape='hv'),
            marker=dict(size=8, color=tv['accent_green']),
            name='Glucose',
            hovertemplate='<b>Glucose</b>: %{y:.1f}<br>%{x}<extra></extra>'
        ))
        fig.update_layout(
            height=420,
        uirevision='cgm_static',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor=tv['plot_bg'],
            font=dict(color=tv['plot_text']),
            margin=dict(t=20, b=20, l=10, r=10),
            hovermode='x unified'
        )

        # --- PLOTLY STYLE PACK (CGM) ---
        fig.update_traces(hoverlabel=dict(namelength=-1))
        fig.update_layout(
            hoverlabel=dict(bgcolor=tv['plot_bg'], font=dict(color=tv['plot_text'])),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        )
        fig.update_xaxes(showgrid=True, gridcolor=tv['plot_grid'], range=[cutoff, datetime.now(ist_tz)])
        fig.update_yaxes(showgrid=True, gridcolor=tv['plot_grid'], title='Glucose (mg/dL)')
        st.plotly_chart(fig, use_container_width=True, theme=None, key=f'cgm_chart_{target_id}')
        return

    # Fallback: Plot recent CGM-like history from Influx (if present)
    end_dt = datetime.now(ist_tz)
    start_dt = end_dt - timedelta(hours=3)
    df = db.get_history(target_id, start_dt, end_dt)
    if isinstance(df, list):
        df = pd.concat(df, ignore_index=True) if len(df) else pd.DataFrame()
    if df is None or df.empty or '_time' not in df.columns:
        return

    df['_time'] = pd.to_datetime(df['_time']).dt.tz_convert(ist_tz)
    df = df.sort_values('_time').reset_index(drop=True)

    # Coerce possible numeric columns
    for c in df.columns:
        if c in ['_time']:
            continue
        if isinstance(c, str) and (('glucose' in c.lower()) or ('cgm' in c.lower()) or (c.lower() == 'bg')):
            df[c] = pd.to_numeric(df[c], errors='coerce')

    series_cols = []
    for c in df.columns:
        if c == '_time' or not isinstance(c, str):
            continue
        lc = c.lower()
        if ('cgm' in lc) or ('glucose' in lc) or (lc == 'bg'):
            if pd.api.types.is_numeric_dtype(df[c]):
                series_cols.append(c)

    if not series_cols:
        return

    fig = go.Figure()
    colors = [tv['accent_green'], tv['accent_blue'], tv['accent_orange'], tv['accent_purple']]
    for i, c in enumerate(series_cols[:6]):
        fig.add_trace(go.Scatter(
            x=df['_time'], y=df[c], mode='markers+lines',
            name=c.replace('_',' ').title(),
            line=dict(width=1, color=colors[i % len(colors)], shape='hv'),
            marker=dict(size=6, color=colors[i % len(colors)])
        ))

    fig.update_layout(
        height=420,
        uirevision='cgm_static',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor=tv['plot_bg'],
        font=dict(color=tv['plot_text']),
        margin=dict(t=20, b=20, l=10, r=10),
        hovermode='x unified'
    )

    # --- PLOTLY STYLE PACK (CGM) ---
    fig.update_traces(hoverlabel=dict(namelength=-1))
    fig.update_layout(
        hoverlabel=dict(bgcolor=tv['plot_bg'], font=dict(color=tv['plot_text'])),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    )
    fig.update_xaxes(showgrid=True, gridcolor=tv['plot_grid'])
    fig.update_yaxes(showgrid=True, gridcolor=tv['plot_grid'], title='CGM')
    st.plotly_chart(fig, use_container_width=True, theme=None, key=f'cgm_chart_{target_id}')


def view_patient_profile():
    st.markdown('<h1 class="animate-up">Patient Profile (CGM)</h1>', unsafe_allow_html=True)
    st.markdown('<p class="text-sub">Real-time patient monitoring driven by Continuous Glucose Monitor (CGM) telemetry.</p>', unsafe_allow_html=True)
    
    pts = db.get_patients()
    if not pts:
        st.warning("No patients registered. Connect a device first.")
        return

    c1, c2 = st.columns([2, 1])
    with c1:
        target_id = get_selected_device(pts, "profile")
        
    st.markdown("<hr style='border: 1px solid var(--card-border); margin: 10px 0 30px 0;'>", unsafe_allow_html=True)
    
    render_patient_profile_fragment(target_id)


@st.fragment(run_every=1)
def render_live_monitor_fragment(target_id):
    # --- MEAL DETECTION (from latest MQTT telemetry) ---
    mqtt_latest_data = getattr(mqtt_service, 'latest_data', {})
    mqtt_cgm_data = getattr(mqtt_service, 'cgm_latest_data', {})
    live_payload = mqtt_cgm_data.get(target_id, {}) or mqtt_latest_data.get(target_id, {})
    if live_payload:
        md = st.session_state.meal_detector
        md_out = md.update(target_id, live_payload)
        if md_out.get('detected'):
            detected_at = datetime.now(timezone.utc)
            st.session_state.meal_notices[target_id] = {
                'detected_at': detected_at.isoformat(),
                'sstar': md_out.get('sstar'),
                'threshold': md_out.get('threshold'),
            }
            # User-facing notice
            if hasattr(st, 'toast'):
                try:
                    st.toast('Meal detected for ' + str(target_id))
                except Exception:
                    pass
            # Auto-bolus delivery using last saved user dose
            doses = load_doses()
            last_bolus = None
            try:
                last_bolus = float(doses.get(target_id, {}).get('bolus_dose'))
            except Exception:
                last_bolus = None
            if last_bolus is None:
                st.session_state.meal_needs_bolus[target_id] = True
            else:
                last_sent = st.session_state.autobolus_sent.get(target_id)
                if last_sent != st.session_state.meal_notices[target_id]['detected_at']:
                    ok = mqtt_service.send_command(target_id, {'bolus_dose': last_bolus})
                    if ok:
                        st.session_state.autobolus_sent[target_id] = st.session_state.meal_notices[target_id]['detected_at']
                        st.session_state.meal_needs_bolus[target_id] = False
                    else:
                        st.session_state.meal_needs_bolus[target_id] = True

    if 'focused_metric' not in st.session_state: 
        st.session_state.focused_metric = None

    ist_tz = timezone(timedelta(hours=5, minutes=30), name="IST")
    now_ist = datetime.now(ist_tz)
    tv = get_theme_vars()
    # --- ROLLING AXIS WINDOW LOGIC (smooth 2-minute window) ---
    window_minutes = 2
    window_end_dt = now_ist
    window_start_dt = window_end_dt - timedelta(minutes=window_minutes)

    # Fetch a little extra to avoid gaps and allow lines to enter smoothly
    fetch_start_dt = window_start_dt - timedelta(minutes=1)

    try:
        df = db.get_history(target_id, fetch_start_dt, now_ist)
        if isinstance(df, list):
            df = pd.concat(df, ignore_index=True) if len(df) > 0 else pd.DataFrame()
    except Exception:
        df = pd.DataFrame()

    if df.empty:
        st.markdown("""
            <div style="text-align: center; padding: 100px 0;">
                <div style="font-family: monospace; font-size: 48px; margin-bottom: 20px; color: var(--text-sub);">[ TELEMETRY ]</div>
                <div style="color: var(--text-sub); font-size: 18px;">Listening for data from device...</div>
            </div>
        """, unsafe_allow_html=True)
        return

    # Process and clean database timeframe
    df['_time'] = pd.to_datetime(df['_time']).dt.tz_convert(ist_tz)
    df = df.sort_values('_time').reset_index(drop=True)
    df = df.ffill().bfill()
    
    latest = df.iloc[-1].to_dict()

    # Define system columns to ignore
    ignore = ['device_id', 'patient_name', 'device_name', 'timestamp', 'patient_id', 'result', 'table', '_start', '_stop', '_measurement', '_time']
    
    num_keys = [k for k in latest.keys() if k not in ignore and isinstance(latest[k], (int, float, np.number))]
    num_keys.sort()
    
    non_num_keys = [k for k in latest.keys() if k not in ignore and not isinstance(latest[k], (int, float, np.number))]
    non_num_keys.sort()

    has_pos = 'position_deg' in latest
    if has_pos and 'position_deg' in num_keys:
        num_keys.remove('position_deg')
        if st.session_state.focused_metric == 'position_deg':
            st.session_state.focused_metric = None

    # Render top section: Status logs and Position Dial
    if non_num_keys or has_pos:
        top_cols = st.columns(2) if (non_num_keys and has_pos) else st.columns(1)
        col_idx = 0
        
        if non_num_keys:
            with top_cols[col_idx]:
                with st.container(border=True):
                    st.markdown("<div class='text-sub' style='font-size: 12px; font-weight: 600; margin-bottom: 10px;'>STATUS LOGS</div>", unsafe_allow_html=True)
                    bullet_list = "".join([f"<li style='margin-bottom: 8px;'><span class='text-sub' style='font-size: 14px;'>{k.replace('_', ' ').upper()}:</span> <span style='color: var(--accent-green); font-weight: 600; font-size: 15px;'>{str(latest[k]).upper()}</span></li>" for k in non_num_keys])
                    st.markdown(f"<ul style='padding-left: 20px; margin:0;'>{bullet_list}</ul>", unsafe_allow_html=True)
            col_idx += 1
            
        if has_pos:
            with top_cols[col_idx]:
                pos_val = float(latest['position_deg'])
                
                fig_polar = go.Figure()
                
                fig_polar.add_trace(go.Scatterpolar(
                    r=[1]*360, theta=list(range(360)), mode='lines',
                    line=dict(color=tv['plot_grid'], width=4), hoverinfo='skip'
                ))
                
                fig_polar.add_trace(go.Scatterpolar(
                    r=[1], theta=[pos_val], mode='markers+text',
                    marker=dict(size=20, color=tv['accent_cyan'], line=dict(color=tv['plot_bg'], width=2)),
                    text=[f"<b>{pos_val}°</b>"], textposition='bottom center',
                    textfont=dict(color=tv['accent_cyan'], size=16), name='Position'
                ))
                
                fig_polar.add_trace(go.Scatterpolar(
                    r=[0], theta=[0], mode='markers', 
                    marker=dict(size=6, color=tv['plot_text']), hoverinfo='skip'
                ))
                
                fig_polar.add_trace(go.Scatterpolar(
                    r=[0, 1], theta=[pos_val, pos_val], mode='lines',
                    line=dict(color=tv['accent_cyan'], width=2, dash='dot'), hoverinfo='skip'
                ))

                fig_polar.update_layout(
                    uirevision="static_polar_revision", 
                    polar=dict(
                        radialaxis=dict(visible=False, range=[0, 1.4]),
                        angularaxis=dict(
                            visible=True, direction='clockwise', rotation=90,
                            gridcolor=tv['plot_grid'], linecolor=tv['plot_grid'],
                            tickfont=dict(color=tv['plot_text'], size=10),
                        ),
                        bgcolor=tv['polar_bg']
                    ),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(t=30, b=30, l=30, r=30), height=200, showlegend=False,
                    title=dict(text="POSITION (DEG)", font=dict(color=tv['plot_text'], size=12, weight="bold"), x=0.5, y=0.95)
                )
                
                st.plotly_chart(fig_polar, use_container_width=True, config={'displayModeBar': False}, theme=None, key=f"polar_{target_id}")
        
        st.markdown("<br>", unsafe_allow_html=True)

    theme_colors = [tv['accent_green'], tv['accent_blue'], tv['accent_orange'], tv['accent_purple'], tv['accent_cyan'], tv['accent_red']]

    if num_keys:
        cols = st.columns(len(num_keys))
        for idx, key in enumerate(num_keys):
            val_display = round(float(latest[key]), 2)
            is_focused = (st.session_state.focused_metric == key)
            
            with cols[idx]:
                btn_label = f"{key.replace('_', ' ').upper()}\n{val_display}"
                if st.button(btn_label, key=f"btn_{key}", width="stretch"):
                    st.session_state.focused_metric = None if is_focused else key
                    st.rerun()

    show_keys = [st.session_state.focused_metric] if st.session_state.focused_metric else num_keys
    
    if show_keys:
        fig = make_subplots(
            rows=len(show_keys), cols=1, shared_xaxes=True,
            vertical_spacing=0.1, subplot_titles=[k.replace('_', ' ').title() for k in show_keys]
        )
        
        for i, key in enumerate(show_keys):
            color = theme_colors[i % len(theme_colors)]
            if "glucose" in key.lower(): color = tv['accent_green']
            elif "insulin" in key.lower(): color = tv['accent_blue']
            elif "battery" in key.lower(): color = tv['accent_orange']
            
            fig.add_trace(go.Scatter(
                x=df['_time'], y=df[key], mode='lines',
                line=dict(width=2.5, color=color, shape='spline'),
                name=key.replace('_', ' ').title(),
                hovertemplate=f"<b>{key.replace('_', ' ').title()}</b>: %{{y:.2f}}<extra></extra>"
            ), row=i+1, col=1)

        fig.update_layout(
            uirevision=f"live_monitor_{target_id}", 
            height=300 * len(show_keys) if len(show_keys) > 1 else 500,
            margin=dict(l=20, r=20, t=60, b=20),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor=tv['plot_bg'],
            showlegend=False,
            font=dict(color=tv['plot_text'], size=10),
            hovermode="x unified", 
            dragmode="zoom"
        )

        # --- PLOTLY STYLE PACK (LIVE) ---
        fig.update_traces(line=dict(width=2), mode='lines')
        fig.update_layout(
            hoverlabel=dict(bgcolor=tv['plot_bg'], font=dict(color=tv['plot_text'])),
            dragmode='pan',
        )
        
        fig.update_yaxes(
            showgrid=True, gridcolor=tv['plot_grid'], gridwidth=1,
            minor=dict(showgrid=True, gridcolor=tv['plot_grid'], griddash='dot'),
            zeroline=True, zerolinecolor=tv['plot_line'], zerolinewidth=2,
            showline=True, linewidth=1, linecolor=tv['plot_line'], mirror=True, fixedrange=False,
            autorange=True 
        )
        
        fig.update_xaxes(
            range=[window_start_dt, window_end_dt],
            showgrid=True, gridcolor=tv['plot_grid'], gridwidth=1,
            minor=dict(showgrid=True, gridcolor=tv['plot_grid'], griddash='dot'),
            visible=True, tickformat='%H:%M:%S', title='Time (IST)',
            showline=True, linewidth=1, linecolor=tv['plot_line'], mirror=True,
            showspikes=True, spikemode="across+marker", spikethickness=1, spikedash="solid", spikecolor=tv['plot_text'] 
        )
        
        keys_str = "_".join(show_keys)
        lines_key = f"render_lines_{target_id}_{keys_str}"
        
        st.plotly_chart(
            fig, 
            use_container_width=True, 
            theme=None, 
            config={
                'displayModeBar': True, 
                'scrollZoom': True, 
                'displaylogo': False,
                'modeBarButtonsToAdd': ['zoom2d', 'pan2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d']
            },
            key=lines_key 
        )


def view_monitor():
    st.markdown('<h1 class="animate-up">Live Telemetry</h1>', unsafe_allow_html=True)
    
    pts = db.get_patients()
    if not pts:
        st.warning("No patients registered. Go to Settings to add a device.")
        return

    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        target_id = get_selected_device(pts, "monitor")

    notice = st.session_state.meal_notices.get(target_id)
    if notice:
        st.warning(f"MEAL DETECTED for {target_id} (S**={notice.get('sstar')}, thr={notice.get('threshold')})")
    
    last = getattr(mqtt_service, 'device_heartbeats', {}).get(target_id, 0)
    is_online = (time.time() - last) < 30
    
    status_text = "[ ACTIVE ]" if is_online else "[ INACTIVE ]"
    status_color = "var(--accent-green)" if is_online else "var(--accent-red)"
    
    with c2:
        st.markdown(f"""
            <div style="padding: 8px 15px; border: 1px solid {status_color}; border-radius: 8px; 
            text-align: center; color: {status_color}; font-weight: 800; font-size: 14px; background: var(--card-bg);">
                {status_text}
            </div>
        """, unsafe_allow_html=True)
        
    with c3:
        active = st.toggle("Active Feed", value=True)

    st.markdown("<hr style='border: 0.5px solid var(--card-border);'>", unsafe_allow_html=True)

    if active:
        st.caption("INFO: Use the toolbar at the top right of the graph to View Fullscreen (Maximize) or Zoom.")
        render_live_monitor_fragment(target_id)
    else:
        st.info("Telemetry stream paused.")


# --- FORMULA STORAGE HELPERS ---
FORMULA_FILE = "saved_formulas.json"
DOSE_FILE = "saved_doses.json"

def load_doses():
    if os.path.exists(DOSE_FILE):
        try:
            with open(DOSE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_dose(device_id, dose_type, dose_value):
    doses = load_doses()
    if device_id not in doses:
        doses[device_id] = {}
    doses[device_id][dose_type] = dose_value
    with open(DOSE_FILE, "w") as f:
        json.dump(doses, f)


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
        
        if st.button("Save Formula", key=f"save_btn_{target_id}_{payload_key}", width="stretch"):
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
            st.markdown("<div class='text-sub' style='margin-top: 10px; font-size:14px; margin-bottom:5px;'>Provide Variable Values:</div>", unsafe_allow_html=True)
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
                <div style="border: 1px solid var(--accent-green); background: var(--card-bg); border-radius: 8px; padding: 15px; margin-top: 15px; display: flex; justify-content: space-between; align-items: center;">
                    <div><span style="color: var(--accent-green); font-size: 14px;">Calculated {calc_title}:</span><br><span style="font-size: 24px; font-weight: 800; color: var(--text-main);">{result} Units</span></div>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(f"Add to Command Payload", key=f"btn_add_{target_id}_{payload_key}", width="stretch"):
                st.session_state.payload_queue[payload_key] = result
                if payload_key == 'bolus_dose':
                    # Persist last user-approved bolus so auto-delivery can reuse it on meal detection
                    save_dose(target_id, 'bolus_dose', result)
                st.rerun()
                
        except ZeroDivisionError:
            st.error("Error: Division by zero detected in formula.")
        except Exception as e:
            st.error("Waiting for a valid mathematical formula... (check your syntax)")


@st.fragment(run_every=1)
def render_control_telemetry_fragment(target_id):
    mqtt_latest_data = getattr(mqtt_service, 'latest_data', {})
    live_data = mqtt_latest_data.get(target_id, {})
    
    with st.container(border=True):
        if live_data:
            ignored = ['device_id', 'patient_name', 'device_name', 'timestamp', 'patient_id']
            valid_vars = {k: v for k, v in live_data.items() if k not in ignored}
            
            if valid_vars:
                for k, v in valid_vars.items():
                    val_str = f"{v:.2f}" if isinstance(v, float) else str(v)
                    st.markdown(f"<div><span class='text-sub'>{k}:</span> <span class='metric-value'>{val_str}</span></div>", unsafe_allow_html=True)
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
    if 'reset_confirm' not in st.session_state:
        st.session_state.reset_confirm = False
        
    c1, c2 = st.columns([2, 1])
    with c1:
        target_id = get_selected_device(pts, "control")
        
    mqtt_latest_data = getattr(mqtt_service, 'latest_data', {})
    live_data_static = mqtt_latest_data.get(target_id, {})
    
    mqtt_heartbeats = getattr(mqtt_service, 'device_heartbeats', {})
    is_online = (time.time() - mqtt_heartbeats.get(target_id, 0)) < 30
    
    if not is_online:
        st.warning(f"INFO: {target_id} is currently OFFLINE. Clinical configurations are disabled to ensure patient safety, but Power commands are permitted.")

    if st.session_state.meal_needs_bolus.get(target_id):
        st.error('Meal detected but no saved bolus dose exists for this device. Enter a bolus dose to deliver.')
        with st.container(border=True):
            bol = st.number_input('Bolus dose (Units)', min_value=0.0, value=0.0, step=0.1, format='%.2f', key=f'auto_bolus_in_{target_id}')
            c_a, c_b = st.columns(2)
            with c_a:
                if st.button('Save Bolus', width='stretch', key=f'save_auto_bolus_{target_id}'):
                    save_dose(target_id, 'bolus_dose', float(bol))
                    st.session_state.meal_needs_bolus[target_id] = False
                    st.success('Bolus saved. It will be auto-used on the next meal detection.')
                    time.sleep(1)
                    st.rerun()
            with c_b:
                if st.button('Save + Deliver Now', type='primary', width='stretch', key=f'send_auto_bolus_{target_id}'):
                    save_dose(target_id, 'bolus_dose', float(bol))
                    with st.spinner('Transmitting...'):
                        ok = mqtt_service.send_command(target_id, {'bolus_dose': float(bol)})
                    if ok:
                        st.session_state.meal_needs_bolus[target_id] = False
                        st.success('Auto bolus delivered.')
                    else:
                        st.error('Failed to reach broker.')
                    time.sleep(1)
                    st.rerun()

    
    st.markdown("<hr style='border: 1px solid var(--card-border); margin: 10px 0 30px 0;'>", unsafe_allow_html=True)
    
    left_col, right_col = st.columns([2.5, 1], gap="large")
    
    with left_col:
        st.markdown("### Power Operations")
        
        with st.container(border=True):
            p1, p2, p3 = st.columns(3)
            with p1:
                if st.button("POWER ON", width="stretch"):
                    st.session_state.power_confirm = "ON"
                    st.session_state.reset_confirm = False
            with p2:
                if st.button("POWER OFF", width="stretch"):
                    st.session_state.power_confirm = "OFF"
                    st.session_state.reset_confirm = False
            with p3:
                if st.button("RESET FAULT", width="stretch"):
                    st.session_state.reset_confirm = True
                    st.session_state.power_confirm = None
                    
            if st.session_state.power_confirm:
                state = st.session_state.power_confirm
                color = "var(--accent-green)" if state == "ON" else "var(--accent-red)"
                
                st.markdown(f"""
                <div style="border-left: 4px solid var(--accent-orange); padding: 15px; border-radius: 4px; margin-top: 15px; background: var(--card-bg);">
                    <strong style="color: var(--accent-orange);">Confirmation Required:</strong><br>
                    <span style="color: var(--text-main);">Do you want to turn the device <strong style="color: {color};">{state}</strong>?</span>
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

            if st.session_state.reset_confirm:
                st.markdown("""
                <div style="border-left: 4px solid var(--accent-cyan); padding: 15px; border-radius: 4px; margin-top: 15px; background: var(--card-bg);">
                    <strong style="color: var(--accent-cyan);">Confirmation Required:</strong><br>
                    <span style="color: var(--text-main);">Do you want to send a <strong>FAULT RESET</strong> command to the device?</span>
                </div>
                """, unsafe_allow_html=True)
                
                conf1, conf2 = st.columns(2)
                with conf1:
                    if st.button("Yes, Reset Fault", type="primary", width="stretch"):
                        with st.spinner("Transmitting..."):
                            success = mqtt_service.send_command(target_id, {"reset_fault": True})
                            if success:
                                st.success("Command successful: Fault Reset transmitted")
                            else:
                                st.error("Failed to reach broker.")
                        st.session_state.reset_confirm = False
                        time.sleep(1.5)
                        st.rerun()
                with conf2:
                    if st.button("Cancel Reset", width="stretch"):
                        st.session_state.reset_confirm = False
                        st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("### Configuration")
        
        tab_basal, tab_bolus = st.tabs(["Set Basal Rate", "Administer Bolus"])
        
        with tab_basal:
            render_dynamic_calculator("Basal Rate", "basal_rate", live_data_static, target_id)
            
        with tab_bolus:
            render_dynamic_calculator("Correction / Meal Bolus", "bolus_dose", live_data_static, target_id)

    with right_col:
        st.markdown("### Send Command")
        
        if not st.session_state.payload_queue:
            st.info("No commands generated. Add a dose from the configuration section.")
        else:
            with st.container(border=True):
                st.markdown("<div style='font-size:12px;' class='text-sub'>Command Payload</div>", unsafe_allow_html=True)
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
        render_control_telemetry_fragment(target_id)


def view_history():
    st.markdown('<h1 class="animate-up">Medical Archives</h1>', unsafe_allow_html=True)
    pts = db.get_patients()
    if not pts:
        st.warning("No patients registered.")
        return
    
    ist_tz = timezone(timedelta(hours=5, minutes=30), name="IST")
    tv = get_theme_vars()
    
    with st.container():
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            target_id = get_selected_device(pts, "hist")
        
        if "hist_start_default" not in st.session_state:
            st.session_state.hist_start_default = datetime.now(ist_tz) - timedelta(hours=1)
        if "hist_end_default" not in st.session_state:
            st.session_state.hist_end_default = datetime.now(ist_tz)

        row2_c1, row2_c2 = st.columns(2)
        with row2_c1:
            st.caption("FROM (IST)")
            date_from = st.date_input("Start Date", value=st.session_state.hist_start_default.date())
            time_from = st.time_input("Start Time", value=st.session_state.hist_start_default.time())
        with row2_c2:
            st.caption("UPTO (IST)")
            date_to = st.date_input("End Date", value=st.session_state.hist_end_default.date())
            time_to = st.time_input("End Time", value=st.session_state.hist_end_default.time())

        st.markdown("<br>", unsafe_allow_html=True)
        fetch = st.button("Query Database", type="primary", width="stretch")

    # Persist results so UI interactions (multiselect) don't wipe the view on rerun.
    if 'hist_result' not in st.session_state:
        st.session_state.hist_result = None

    if fetch:
        dt_from = datetime.combine(date_from, time_from).replace(tzinfo=ist_tz)
        dt_to = datetime.combine(date_to, time_to).replace(tzinfo=ist_tz)

        if dt_from >= dt_to:
            st.error("Invalid Range: 'From' time must be earlier than 'Upto' time.")
        else:
            with st.spinner("Processing Time-Series Data..."):
                df = db.get_history(target_id, dt_from, dt_to)

                if isinstance(df, list):
                    df = pd.concat(df, ignore_index=True) if len(df) else pd.DataFrame()

                if df is None or df.empty:
                    st.session_state.hist_result = {
                        'target_id': target_id,
                        'dt_from': dt_from,
                        'dt_to': dt_to,
                        'df': pd.DataFrame(),
                    }
                else:
                    df['_time'] = pd.to_datetime(df['_time']).dt.tz_convert(ist_tz)
                    df = df.sort_values('_time').reset_index(drop=True)
                    st.session_state.hist_result = {
                        'target_id': target_id,
                        'dt_from': dt_from,
                        'dt_to': dt_to,
                        'df': df,
                    }

    # Render last fetched results (if any)
    hr = st.session_state.hist_result
    if not hr or hr.get('target_id') != target_id:
        st.info('Query the database to view history.')
        return

    df = hr.get('df')
    if df is None or df.empty:
        st.error('No telemetry records found for the requested time period.')
        return

    st.success(f"Retrieved {len(df)} matching samples")

    # Coerce common numeric fields that may come back as strings/objects from Influx merges
    for c in list(df.columns):
        if c in ['_time', 'result', 'table', '_start', '_stop', '_measurement', 'device_id', 'patient_name', 'device_name', 'timestamp']:
            continue
        if isinstance(c, str):
            lc = c.lower()
            if ('glucose' in lc) or ('cgm' in lc) or (lc == 'bg') or ('trend' in lc):
                df[c] = pd.to_numeric(df[c], errors='coerce')

    num_cols = df.select_dtypes(include=['number']).columns.tolist()
    num_cols = [c for c in num_cols if c not in ['result', 'table']]

    st.markdown('### Select Signals to Plot')
    plot_key = f"hist_plot_cols_{target_id}"

    # Start with no default selection (user chooses). Keep selection across reruns via key.
    if plot_key not in st.session_state:
        st.session_state[plot_key] = []

    plot_cols = st.multiselect(
        'Signals',
        options=num_cols,
        default=st.session_state.get(plot_key, []),
        key=plot_key,
        help='Choose which numeric fields to plot.'
    )

    # Show latest values for selected signals
    if plot_cols:
        latest_row = df.iloc[-1]
        st.markdown('### Latest Values')
        cols = st.columns(min(len(plot_cols), 4))
        for i, c in enumerate(plot_cols):
            with cols[i % len(cols)]:
                try:
                    v = float(latest_row[c])
                    st.metric(str(c).replace('_', ' ').title(), f"{v:.2f}")
                except Exception:
                    st.metric(str(c).replace('_', ' ').title(), str(latest_row.get(c)))

    if not plot_cols:
        st.info('Select one or more signals above to draw the graph.')
    else:
        theme_colors = [tv['accent_green'], tv['accent_blue'], tv['accent_orange'], tv['accent_purple'], tv['accent_cyan'], tv['accent_red']]
        st.caption('INFO: Use the toolbar at the top right of the graph to View Fullscreen (Maximize) or Zoom.')

        fig = go.Figure()
        for idx, c in enumerate(plot_cols):
            color = theme_colors[idx % len(theme_colors)]
            lc = str(c).lower()
            if 'glucose' in lc or 'cgm' in lc or lc == 'bg':
                color = tv['accent_green']
            elif 'insulin' in lc or 'bolus' in lc or 'basal' in lc:
                color = tv['accent_blue']
            elif 'battery' in lc:
                color = tv['accent_orange']

            fig.add_trace(go.Scatter(
                x=df['_time'], y=df[c],
                name=str(c).replace('_', ' ').title(),
                mode='lines',
                line=dict(width=1.8, color=color),
                hovertemplate=f"<b>{str(c).replace('_', ' ').title()}</b>: %{{y:.2f}}<extra></extra>"
            ))

        fig.update_layout(
            height=600,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor=tv['plot_bg'],
            font=dict(color=tv['plot_text']),
            margin=dict(t=40, b=40),
            hovermode='x unified',
            dragmode='zoom',
            legend=dict(orientation='h', yanchor='bottom', y=1.05, xanchor='right', x=1),
            uirevision=f"history_{target_id}",
        )

        fig.update_xaxes(
            showgrid=True, gridcolor=tv['plot_grid'], gridwidth=1,
            minor=dict(showgrid=True, gridcolor=tv['plot_grid'], griddash='dot'),
            title='Timestamp (IST)', showline=True, linewidth=1, linecolor=tv['plot_line'], mirror=True,
            showspikes=True, spikemode='across+marker', spikethickness=1, spikedash='solid', spikecolor=tv['plot_text'],
            rangeslider=dict(visible=True, thickness=0.08),
        )
        fig.update_yaxes(
            showgrid=True, gridcolor=tv['plot_grid'], gridwidth=1,
            minor=dict(showgrid=True, gridcolor=tv['plot_grid'], griddash='dot'),
            zeroline=True, zerolinecolor=tv['plot_line'], zerolinewidth=2,
            showline=True, linewidth=1, linecolor=tv['plot_line'], mirror=True,
            title='Measured Value', fixedrange=False, autorange=True
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            theme=None,
            key=f"history_chart_{target_id}",
            config={'scrollZoom': True, 'displayModeBar': True, 'displaylogo': False, 'modeBarButtonsToAdd': ['zoom2d', 'pan2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d']},
        )

    non_num_cols = [c for c in df.columns if c not in num_cols and c not in ['_time', 'result', 'table', '_start', '_stop', '_measurement', 'device_id', 'patient_name']]
    if non_num_cols:
        st.markdown('### Status & Events Log')
        log_df = df[['_time'] + non_num_cols].copy()
        log_df.rename(columns={'_time': 'Timestamp'}, inplace=True)
        st.dataframe(log_df, use_container_width=True, hide_index=True)
        st.markdown('<br>', unsafe_allow_html=True)

    with st.expander('Diagnostic Table (Raw Data)'):
        st.dataframe(df, use_container_width=True)

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
elif nav == "Patient Profile": view_patient_profile()
elif nav == "Device Control": view_control() 
elif nav == "History": view_history()
elif nav == "Settings": view_setup()
