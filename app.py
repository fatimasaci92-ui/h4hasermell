# ================= app.py — VERSION FINALE AVEC IA LÉGÈRE =================

import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import ee
import json
import tempfile
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import io
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image
from reportlab.lib.units import inch
import matplotlib.pyplot as plt 
from reportlab.lib.pagesizes import A4


# ================= INIT GEE =================
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(ee_key_json, f)
        key_path = f.name
    credentials = ee.ServiceAccountCredentials(ee_key_json["client_email"], key_path)
    ee.Initialize(credentials)
    os.remove(key_path)
except Exception as e:
    st.error(f"Erreur GEE : {e}")
    st.stop()

# ================= CONFIG =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= IA LÉGÈRE (SANS TORCH) =================
def detect_ch4_anomaly(image_array):
    """IA simplifiée par seuils, compatible Streamlit Cloud"""
    val = np.nanmean(image_array)
    if np.isnan(val):
        return "❌ Pas de données", 0.0
    elif val > 1920:
        return "🔥 Fuite critique", 1.0
    elif val > 1880:
        return "⚠️ Suspect", 0.7
    else:
        return "✅ Normal", 0.1

# ================= ZONES FIXES =================
zoneCentre = ee.Geometry.Polygon([
  [3.37696562, 32.75662617],
  [3.61159117, 32.75663435],
  [3.60634757, 33.01349055],
  [2.93385218, 33.02401464],
  [2.92757292, 32.89394392],
  [3.3769424, 32.88954646],
  [3.37696562, 32.75662617]
])

zoneSud = ee.Geometry.Polygon([
  [2.88567251, 32.45093128],
  [3.37963967, 32.45092697],
  [3.37964793, 32.88379946],
  [2.88561768, 32.88378899],
  [2.88567251, 32.45093128]
])

zoneNord = ee.Geometry.Polygon([
  [3.18513508, 33.01358581],
  [3.18482285, 33.28297225],
  [3.81093387, 33.27857017],
  [3.81077745, 33.01358819],
  [3.18513508, 33.01358581]
])

# ================= PATHS =================
DATA_DIR = "data"
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
csv_annual = "data/2020 2024/CH4_HassiRmel_annual_2020_2024.csv"

# ================= SECTION A =================
st.markdown("## 📁 Section A — Données")
if st.button("Afficher dossiers"):
    for root, dirs, files in os.walk(DATA_DIR):
        st.write(root)
        for f in files:
            st.write(" └─", f)

# ================= SECTION K — CARBON MAPPER (VERSION CORRIGÉE FINALE) =================

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import io
import base64
import json
from datetime import datetime
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

st.markdown("## 🛰️ Carbon Mapper — Fuites CH₄ réelles géolocalisées")

st.info(
    "Source : Carbon Mapper (Tanager-1, NASA EMIT, AVIRIS-NG). "
    "Résolution 3–50 m. Données réelles de panaches géolocalisés."
)

# ================= TOKEN =================

CM_TOKEN = ""

try:
    CM_TOKEN = (
        st.secrets.get("CARBON_API_TOKEN")
        or ""
    ).strip()
except:
    CM_TOKEN = ""

if not CM_TOKEN:
    st.error(
        "❌ Token Carbon Mapper introuvable.\n\n"
        "Ajoutez dans secrets.toml :\n"
        'CARBON_API_TOKEN = "VOTRE_TOKEN"'
    )
    st.stop()

# ================= PARAMÈTRES =================

col1, col2 = st.columns(2)

with col1:
    cm_lat_min = st.number_input(
        "Lat min",
        value=32.45,
        format="%.4f"
    )

    cm_lat_max = st.number_input(
        "Lat max",
        value=33.28,
        format="%.4f"
    )

with col2:
    cm_lon_min = st.number_input(
        "Lon min",
        value=2.88,
        format="%.4f"
    )

    cm_lon_max = st.number_input(
        "Lon max",
        value=3.81,
        format="%.4f"
    )

col3, col4 = st.columns(2)

with col3:
    cm_date_start = st.date_input(
        "Date début",
        value=datetime(2022, 1, 1)
    )

with col4:
    cm_date_end = st.date_input(
        "Date fin",
        value=datetime.utcnow()
    )

cm_gas = st.selectbox(
    "Gaz",
    ["CH4", "CO2"]
)

cm_sector = st.selectbox(
    "Secteur",
    [
        "Tous",
        "oil-and-gas",
        "solid-waste",
        "coal",
        "agriculture",
        "wastewater"
    ]
)

sector_val = "" if cm_sector == "Tous" else cm_sector

# ================= BBOX CORRIGÉ =================

bbox_val = [
    float(cm_lon_min),
    float(cm_lat_min),
    float(cm_lon_max),
    float(cm_lat_max)
]

# ================= TOKEN BASE64 =================

token_b64 = base64.b64encode(
    CM_TOKEN.encode()
).decode()

# ================= HTML + JS =================

html_code = f"""
<!DOCTYPE html>
<html>

<head>

<meta charset="utf-8"/>

<link rel="stylesheet"
href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<style>

* {{
box-sizing:border-box;
margin:0;
padding:0;
font-family:sans-serif;
}}

body {{
padding:6px;
}}

#map {{
width:100%;
height:500px;
border-radius:10px;
border:1px solid #ddd;
display:none;
margin-top:10px;
}}

#status {{
margin:8px 0;
font-size:13px;
color:#666;
}}

#btn {{
width:100%;
padding:10px;
border-radius:8px;
border:1px solid #ccc;
background:white;
cursor:pointer;
font-size:14px;
}}

#btn:hover {{
background:#f5f5f5;
}}

table {{
width:100%;
border-collapse:collapse;
margin-top:10px;
}}

th, td {{
padding:6px;
font-size:12px;
border-bottom:1px solid #eee;
}}

th {{
background:#f5f5f5;
}}

</style>

</head>

<body>

<button id="btn" onclick="run()">
🛰️ Rechercher les fuites {cm_gas}
</button>

<div id="status">
Cliquez pour interroger Carbon Mapper...
</div>

<div id="map"></div>

<div id="table_wrap"></div>

<script>

const TOKEN = atob("{token_b64}");

const GAS = "{cm_gas}";
const SECTOR = "{sector_val}";

const BBOX = {json.dumps(bbox_val)};

const DATE_START = "{cm_date_start}";
const DATE_END = "{cm_date_end}";

const API_URL =
"https://api.carbonmapper.org/api/v1/catalog/plumes/annotated";

let map = null;
let layer = null;

function setStatus(msg,color="#666") {{
    const s = document.getElementById("status");
    s.innerHTML = msg;
    s.style.color = color;
}}

async function run() {{

    setStatus("Chargement...", "#888");

    const params = {{
        limit: 200,
        offset: 0,
        gas: GAS,
        bbox: BBOX.join(","),
        datetime:
            DATE_START + "T00:00:00Z/" +
            DATE_END + "T23:59:59Z"
    }};

    if (SECTOR) {{
        params.sector = SECTOR;
    }}

    const qs = new URLSearchParams(params).toString();

    const final_url = API_URL + "?" + qs;

    console.log(final_url);

    try {{

        const response = await fetch(
            final_url,
            {{
                headers: {{
                    "Authorization":
                        "Bearer " + TOKEN
                }}
            }}
        );

        console.log("STATUS:", response.status);

        const txt = await response.text();

        console.log(txt);

        if (!response.ok) {{

            setStatus(
                "❌ Erreur API : " +
                response.status,
                "red"
            );

            return;
        }}

        const data = JSON.parse(txt);

        const items = data.items || [];

        if (items.length === 0) {{

            setStatus(
                "⚠️ Aucun panache trouvé",
                "orange"
            );

            return;
        }}

        setStatus(
            "✅ " + items.length +
            " panache(s) détecté(s)",
            "green"
        );

        renderMap(items);

        renderTable(items);

    }}

    catch(err) {{

        console.log(err);

        setStatus(
            "❌ Erreur réseau/API",
            "red"
        );
    }}
}}

function renderMap(items) {{

    document.getElementById("map").style.display = "block";

    let pts = [];

    items.forEach(p => {{

        const prop = p.properties || p;

        let lat =
            prop.source_lat ||
            prop.lat ||
            null;

        let lon =
            prop.source_lon ||
            prop.lon ||
            null;

        if (!lat && p.geometry) {{
            lon = p.geometry.coordinates[0];
            lat = p.geometry.coordinates[1];
        }}

        if (lat && lon) {{
            pts.push([lat, lon, prop]);
        }}
    }});

    if (pts.length === 0) return;

    const centerLat =
        pts.reduce((a,b)=>a+b[0],0)/pts.length;

    const centerLon =
        pts.reduce((a,b)=>a+b[1],0)/pts.length;

    if (!map) {{

        map = L.map("map").setView(
            [centerLat, centerLon],
            8
        );

        L.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}",
            {{
                attribution:"ESRI"
            }}
        ).addTo(map);

    }} else {{

        map.setView(
            [centerLat, centerLon],
            8
        );

        if (layer) {{
            map.removeLayer(layer);
        }}
    }}

    layer = L.layerGroup().addTo(map);

    pts.forEach(p => {{

        const lat = p[0];
        const lon = p[1];
        const prop = p[2];

        const emission =
            prop.emission_auto ||
            prop.emission ||
            0;

        let color = "green";

        if (emission > 1000)
            color = "red";
        else if (emission > 300)
            color = "orange";

        L.circleMarker(
            [lat, lon],
            {{
                radius:10,
                color:color,
                fillColor:color,
                fillOpacity:0.8
            }}
        )
        .bindPopup(
            "<b>Débit:</b> " +
            emission +
            " kg/h"
        )
        .addTo(layer);

    }});
}}

function renderTable(items) {{

    let html = `
    <table>
    <thead>
    <tr>
        <th>ID</th>
        <th>Date</th>
        <th>Débit kg/h</th>
    </tr>
    </thead>
    <tbody>
    `;

    items.forEach(p => {{

        const prop = p.properties || p;

        html += `
        <tr>
            <td>${{prop.id || "N/A"}}</td>
            <td>${{prop.acquisition_date || "N/A"}}</td>
            <td>${{
                prop.emission_auto ||
                prop.emission ||
                "N/A"
            }}</td>
        </tr>
        `;
    }});

    html += `
    </tbody>
    </table>
    `;

    document.getElementById(
        "table_wrap"
    ).innerHTML = html;
}}

</script>

</body>
</html>
"""

components.html(
    html_code,
    height=800,
    scrolling=True
)

# ================= PDF =================

st.markdown("### 📄 Rapport PDF Carbon Mapper")

if st.button("📥 Générer rapport PDF"):

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4
    )

    styles = getSampleStyleSheet()

    elements = []

    elements.append(
        Paragraph(
            "<b>DATA.SAT — Carbon Mapper Report</b>",
            styles["Title"]
        )
    )

    elements.append(Spacer(1,10))

    elements.append(
        Paragraph(
            f"Gaz : {cm_gas}",
            styles["Normal"]
        )
    )

    elements.append(
        Paragraph(
            f"Secteur : {cm_sector}",
            styles["Normal"]
        )
    )

    elements.append(
        Paragraph(
            f"Période : {cm_date_start} → {cm_date_end}",
            styles["Normal"]
        )
    )

    elements.append(Spacer(1,15))

    elements.append(
        Paragraph(
            "Analyse Carbon Mapper des panaches CH₄.",
            styles["Normal"]
        )
    )

    doc.build(elements)

    buffer.seek(0)

    st.download_button(
        label="📥 Télécharger PDF",
        data=buffer,
        file_name="carbon_mapper_report.pdf",
        mime="application/pdf"
    )
