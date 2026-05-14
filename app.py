# ================= =================
# 📦 IMPORTS
# ================= =================
import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
import tempfile
import io
from datetime import datetime, timedelta

import folium
from streamlit_folium import st_folium

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4


# ================= =================
# 🔐 CARBON MAPPER API CONFIG
# ================= =================
BASE_URL = "https://api.carbonmapper.org/api/v1/"

# ⚠️ better: move to st.secrets later
EMAIL = "fatimasaci92@gmail.com"
PASSWORD = "7htdwqsZGE2!Uvh"


# ================= =================
# 🔑 AUTH FUNCTIONS
# ================= =================
def get_access_token():
    """Login and get access token"""
    r = requests.post(
        BASE_URL + "token/pair",
        json={"email": EMAIL, "password": PASSWORD}
    )
    r.raise_for_status()
    return r.json()["access"]


def get_stac_token(access_token):
    """Create STAC token for data access"""
    expiration_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    r = requests.post(
        BASE_URL + "account/tokens/create-stac",
        json={
            "name": "streamlit-app",
            "expiration_date": expiration_date
        },
        headers={"Authorization": f"Bearer {access_token}"}
    )
    r.raise_for_status()
    return r.json()["token_value"]


# ================= =================
# 📡 FETCH PLUME DATA
# ================= =================
def fetch_plumes(datetime_range, bbox, limit, gas, stac_token):
    """Download plume CSV from Carbon Mapper"""
    url = BASE_URL + "catalog/plume-csv"

    headers = {"Authorization": f"Bearer {stac_token}"}

    params = {
        "datetime": datetime_range,
        "limit": limit,
        "plume_gas": gas,
        "bbox": bbox
    }

    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()

    return r.text


# ================= =================
# ⚙️ STREAMLIT CONFIG
# ================= =================
st.set_page_config(page_title="CH₄ Monitoring", layout="wide")
st.title("🛰️ Carbon Mapper CH₄ Monitoring Dashboard")


# ================= =================
# 🎛️ USER INPUTS
# ================= =================
st.sidebar.header("Filters")

cm_lat_min = st.sidebar.number_input("Lat min", value=32.45)
cm_lat_max = st.sidebar.number_input("Lat max", value=33.28)
cm_lon_min = st.sidebar.number_input("Lon min", value=2.88)
cm_lon_max = st.sidebar.number_input("Lon max", value=3.81)

cm_date_start = st.sidebar.date_input("Start date", value=datetime(2022, 1, 1))
cm_date_end = st.sidebar.date_input("End date", value=datetime.utcnow())

cm_gas = st.sidebar.selectbox("Gas", ["CH4", "CO2"])
limit = st.sidebar.slider("Limit", 50, 1000, 200)


# ================= =================
# 📥 LOAD DATA BUTTON
# ================= =================
if st.button("📥 Load Carbon Mapper Data"):

    try:
        # 1. Auth
        access_token = get_access_token()
        stac_token = get_stac_token(access_token)

        # 2. bbox format: [min_lon, min_lat, max_lon, max_lat]
        bbox = [cm_lon_min, cm_lat_min, cm_lon_max, cm_lat_max]

        # 3. Fetch CSV
        csv_text = fetch_plumes(
            datetime_range=f"{cm_date_start}/{cm_date_end}",
            bbox=bbox,
            limit=limit,
            gas=cm_gas,
            stac_token=stac_token
        )

        # 4. Convert to DataFrame
        df = pd.read_csv(io.StringIO(csv_text))

        st.session_state["plume_df"] = df
        st.success("Data loaded successfully ✅")

    except Exception as e:
        st.error(f"Error: {e}")


# ================= =================
# 📊 SHOW TABLE
# ================= =================
if "plume_df" in st.session_state:
    st.markdown("## 📊 Plume Data Table")
    st.dataframe(st.session_state["plume_df"])


# ================= =================
# 🗺️ MAP (WITH SATELLITE / STREET SWITCH)
# ================= =================
st.markdown("## 🗺️ Plume Map")

# 🎛️ Basemap selector
basemap = st.radio(
    "Map style",
    ["🛣️ Street Map", "🌍 Satellite"],
    horizontal=True
)

# ================= CREATE MAP =================
if basemap == "🌍 Satellite":
    m = folium.Map(
        location=[32.8, 3.2],
        zoom_start=6,
        tiles=None
    )

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="ESRI Satellite",
        name="Satellite",
        overlay=False,
        control=True
    ).add_to(m)

else:
    m = folium.Map(
        location=[32.8, 3.2],
        zoom_start=6,
        tiles="OpenStreetMap"
    )

# ================= PLOT DATA =================
if "plume_df" in st.session_state:
    df = st.session_state["plume_df"]

    for _, row in df.iterrows():
        try:
            lat = float(row["plume_latitude"])
            lon = float(row["plume_longitude"])
            emission = row.get("emission_auto", 0)

            # 🎨 COLOR SCALE
            if emission > 1000:
                color = "red"
                radius = 12
            elif emission > 300:
                color = "orange"
                radius = 8
            else:
                color = "green"
                radius = 5

            folium.CircleMarker(
                location=[lat, lon],
                radius=radius,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7,
                popup=f"""
                <b>Plume ID:</b> {row.get('plume_id','N/A')}<br>
                <b>Emission:</b> {emission} kg/h<br>
                <b>Gas:</b> {row.get('gas','N/A')}<br>
                <b>Sector:</b> {row.get('ipcc_sector','N/A')}<br>
                <b>Date:</b> {row.get('datetime','N/A')}
                """
            ).add_to(m)

        except:
            continue

# ================= DISPLAY =================
st_folium(m, width=1200, height=600)
# ================= =================
# 📄 PDF REPORT
# ================= =================
st.markdown("## 📄 Report")

if st.button("Generate PDF"):

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    elements = []
    elements.append(Paragraph("CH₄ Carbon Mapper Report", styles["Title"]))
    elements.append(Spacer(1, 12))

    if "plume_df" in st.session_state:
        df = st.session_state["plume_df"]
        elements.append(Paragraph(f"Number of plumes: {len(df)}", styles["Normal"]))

    doc.build(elements)
    buffer.seek(0)

    st.download_button(
        "Download PDF",
        buffer,
        file_name="ch4_report.pdf",
        mime="application/pdf"
    )
