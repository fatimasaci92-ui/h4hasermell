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



# ================= SECTION K — CARBON MAPPER (CORRIGÉ) =================
# Correction principale : l'appel API se fait côté NAVIGATEUR (HTML/JS)
# car Streamlit Cloud bloque api.carbonmapper.org côté serveur.
# Collez cette section dans app.py après la Section H.
#
# PRÉREQUIS requirements.txt :
#   streamlit, folium, streamlit-folium, pandas, requests, reportlab
#
# SECRETS .streamlit/secrets.toml :
#   CARBON_MAPPER_TOKEN = "votre_token_ici"

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import io
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

st.markdown("## 🛰️ Carbon Mapper — Fuites CH₄ réelles géolocalisées")
st.info(
    "Source : Carbon Mapper (Tanager-1, NASA EMIT, AVIRIS-NG). "
    "Résolution 3–50 m. Données réelles de panaches géolocalisés."
)

# -------- Récupération token depuis secrets --------
try:
    CM_TOKEN = st.secrets["CARBON_MAPPER_TOKEN"]
except Exception:
    CM_TOKEN = ""

# -------- Paramètres utilisateur --------
col1, col2 = st.columns(2)
with col1:
    cm_lat_min = st.number_input("Lat min", value=32.45, format="%.4f", key="cm_lat_min")
    cm_lat_max = st.number_input("Lat max", value=33.28, format="%.4f", key="cm_lat_max")
with col2:
    cm_lon_min = st.number_input("Lon min", value=2.88, format="%.4f", key="cm_lon_min")
    cm_lon_max = st.number_input("Lon max", value=3.81, format="%.4f", key="cm_lon_max")

col3, col4 = st.columns(2)
with col3:
    cm_date_start = st.date_input("Date début", value=datetime(2022, 1, 1), key="cm_date_start")
with col4:
    cm_date_end = st.date_input("Date fin", value=datetime.utcnow(), key="cm_date_end")

cm_gas = st.selectbox("Gaz", ["CH4", "CO2"], key="cm_gas")
cm_sector = st.selectbox(
    "Secteur",
    ["Tous", "oil-and-gas", "solid-waste", "coal", "agriculture", "wastewater"],
    key="cm_sector"
)

# -------- Génération du composant HTML/JS --------
# L'appel API Carbon Mapper se fait depuis le navigateur de l'utilisateur,
# contournant ainsi le blocage réseau de Streamlit Cloud.

sector_val = "" if cm_sector == "Tous" else cm_sector

html_code = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: sans-serif; font-size: 13px; }}
  body {{ background: transparent; padding: 8px; }}
  #map {{ width: 100%; height: 420px; border-radius: 8px; border: 1px solid #ddd; }}
  .stats {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 8px; margin: 10px 0; }}
  .stat-card {{ background: #f5f5f5; border-radius: 8px; padding: 10px; text-align: center; }}
  .stat-label {{ font-size: 11px; color: #888; margin-bottom: 4px; }}
  .stat-value {{ font-size: 20px; font-weight: 500; }}
  #status {{ margin: 8px 0; font-size: 13px; min-height: 18px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
  th {{ text-align: left; padding: 6px 8px; font-weight: 500; color: #888;
        border-bottom: 1px solid #eee; font-size: 11px; }}
  td {{ padding: 5px 8px; border-bottom: 0.5px solid #f0f0f0; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 120px; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  .legend {{ position: absolute; bottom: 40px; left: 10px; z-index: 1000;
             background: rgba(255,255,255,0.92); padding: 8px 12px;
             border-radius: 8px; font-size: 11px; box-shadow: 0 2px 6px rgba(0,0,0,0.15); }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; }}
  #btn {{ width: 100%; padding: 10px; font-size: 14px; font-weight: 500;
          cursor: pointer; border-radius: 8px; border: 1px solid #ccc;
          background: #fff; margin-bottom: 8px; }}
  #btn:hover {{ background: #f5f5f5; }}
  #btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
</style>
</head>
<body>

<button id="btn" onclick="fetchPlumes()">🛰️ Rechercher les fuites {cm_gas}</button>
<div id="status" style="color:#888;">Cliquez pour interroger Carbon Mapper...</div>
<div class="stats" id="stats" style="display:none;"></div>
<div style="position:relative;">
  <div id="map" style="display:none;"></div>
  <div class="legend" id="legend" style="display:none;">
    <b>Débit</b><br/>
    <span class="dot" style="background:#E24B4A;"></span> Élevé (&gt;60%)<br/>
    <span class="dot" style="background:#EF9F27;"></span> Moyen (30–60%)<br/>
    <span class="dot" style="background:#1D9E75;"></span> Faible (&lt;30%)
  </div>
</div>
<div id="table_wrap" style="display:none; overflow-x:auto;max-height:300px;overflow-y:auto;">
  <table>
    <thead>
      <tr>
        <th style="width:140px;">ID</th>
        <th style="width:85px;">Date</th>
        <th style="width:70px;text-align:right;">Lat</th>
        <th style="width:70px;text-align:right;">Lon</th>
        <th style="width:80px;text-align:right;">Débit kg/h</th>
        <th style="width:90px;">Secteur</th>
        <th style="width:70px;">Capteur</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<script>
const TOKEN = "{CM_TOKEN}";
const GAS = "{cm_gas}";
const SECTOR = "{sector_val}";
const LAT_MIN = {cm_lat_min};
const LAT_MAX = {cm_lat_max};
const LON_MIN = {cm_lon_min};
const LON_MAX = {cm_lon_max};
const DATE_START = "{cm_date_start}";
const DATE_END = "{cm_date_end}";

let map = null;
let markerLayer = null;

function setStatus(msg, color) {{
  const el = document.getElementById('status');
  el.textContent = msg;
  el.style.color = color || '#888';
}}

function parsePlume(p) {{
  const props = p.properties || p;
  const geom = p.geometry;
  let lat = props.source_lat ?? props.lat ?? props.plume_lat ?? null;
  let lon = props.source_lon ?? props.lon ?? props.plume_lon ?? null;
  if (!lat && geom && geom.coordinates) {{
    lon = geom.coordinates[0];
    lat = geom.coordinates[1];
  }}
  const emission = props.emission_auto ?? props.emission ?? props.emission_uncertainty_upper ?? null;
  return {{
    id: props.plume_id || props.id || '',
    date: (props.acquisition_date || '').slice(0, 10),
    lat: lat !== null ? parseFloat(lat) : null,
    lon: lon !== null ? parseFloat(lon) : null,
    rate: emission !== null && emission !== undefined ? parseFloat(emission) : null,
    sector: props.sector || '',
    sensor: props.instrument || props.sensor || '',
    source: props.source_name || '',
  }};
}}

async function fetchPlumes() {{
  if (!TOKEN) {{
    setStatus('Token manquant dans secrets.toml', '#E24B4A');
    return;
  }}
  const btn = document.getElementById('btn');
  btn.disabled = true;
  document.getElementById('stats').style.display = 'none';
  document.getElementById('map').style.display = 'none';
  document.getElementById('legend').style.display = 'none';
  document.getElementById('table_wrap').style.display = 'none';

  const bbox = `${{LON_MIN}},${{LAT_MIN}},${{LON_MAX}},${{LAT_MAX}}`;
  let baseUrl = `https://api.carbonmapper.org/api/v1/catalog/plumes/?bbox=${{bbox}}&gas=${{GAS}}&date_start=${{DATE_START}}&date_end=${{DATE_END}}&limit=200`;
  if (SECTOR) baseUrl += `&sector=${{SECTOR}}`;

  let all = [];
  let offset = 0;
  let page = 1;

  try {{
    while (true) {{
      setStatus(`Chargement page ${{page}}...`);
      const resp = await fetch(baseUrl + `&offset=${{offset}}`, {{
        headers: {{ 'Authorization': `Bearer ${{TOKEN}}` }}
      }});

      if (!resp.ok) {{
        const txt = await resp.text();
        setStatus(`Erreur API ${{resp.status}}: ${{txt.slice(0,150)}}`, '#E24B4A');
        btn.disabled = false;
        return;
      }}

      const data = await resp.json();
      const results = data.results || data.features || [];
      results.forEach(p => all.push(parsePlume(p)));

      if (!data.next || results.length < 200 || page >= 10) break;
      offset += 200;
      page++;
    }}
  }} catch(e) {{
    setStatus(`Erreur réseau: ${{e.message}}`, '#E24B4A');
    btn.disabled = false;
    return;
  }}

  btn.disabled = false;

  if (all.length === 0) {{
    setStatus('Aucun panache trouvé. Carbon Mapper n\'a peut-être pas encore survolé cette zone.', '#EF9F27');
    return;
  }}

  setStatus(`✅ ${{all.length}} panache(s) détecté(s)`, '#1D9E75');
  renderStats(all);
  renderMap(all);
  renderTable(all);
}}

function renderStats(plumes) {{
  const rates = plumes.map(p => p.rate).filter(v => v !== null);
  const total = rates.reduce((a,b)=>a+b,0);
  const max = rates.length ? Math.max(...rates) : 0;
  const avg = rates.length ? total/rates.length : 0;
  const el = document.getElementById('stats');
  el.innerHTML = [
    {{label:'Panaches', val: plumes.length}},
    {{label:'Débit max (kg/h)', val: max ? max.toFixed(1) : 'N/A'}},
    {{label:'Débit moyen (kg/h)', val: avg ? avg.toFixed(1) : 'N/A'}},
    {{label:'Total (kg/h)', val: total ? total.toFixed(1) : 'N/A'}},
  ].map(s => `
    <div class="stat-card">
      <div class="stat-label">${{s.label}}</div>
      <div class="stat-value">${{s.val}}</div>
    </div>
  `).join('');
  el.style.display = 'grid';
}}

function renderMap(plumes) {{
  const valid = plumes.filter(p => p.lat && p.lon);
  if (!valid.length) return;

  document.getElementById('map').style.display = 'block';
  document.getElementById('legend').style.display = 'block';

  const lats = valid.map(p=>p.lat);
  const lons = valid.map(p=>p.lon);
  const cLat = lats.reduce((a,b)=>a+b)/lats.length;
  const cLon = lons.reduce((a,b)=>a+b)/lons.length;

  if (!map) {{
    map = L.map('map').setView([cLat, cLon], 9);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      attribution: 'ESRI Satellite'
    }}).addTo(map);
  }} else {{
    if (markerLayer) {{ map.removeLayer(markerLayer); }}
    map.setView([cLat, cLon], 9);
  }}

  markerLayer = L.layerGroup().addTo(map);
  const rates = valid.map(p=>p.rate).filter(v=>v!==null);
  const maxRate = rates.length ? Math.max(...rates) : 1;

  valid.forEach(p => {{
    const ratio = p.rate !== null ? p.rate / maxRate : 0;
    const color = ratio > 0.6 ? '#E24B4A' : ratio > 0.3 ? '#EF9F27' : '#1D9E75';
    const radius = ratio > 0.6 ? 14 : ratio > 0.3 ? 10 : 7;

    if (color === '#E24B4A') {{
      L.circleMarker([p.lat, p.lon], {{
        radius: radius + 8, color: '#A32D2D',
        fillColor: '#E24B4A', fillOpacity: 0.15, weight: 1
      }}).addTo(markerLayer);
    }}

    L.circleMarker([p.lat, p.lon], {{
      radius, color, fillColor: color, fillOpacity: 0.85, weight: 1.5
    }}).bindPopup(`
      <b>${{p.id}}</b><br/>
      Date: ${{p.date}}<br/>
      Débit: <b>${{p.rate !== null ? p.rate.toFixed(1)+' kg/h' : 'N/A'}}</b><br/>
      Secteur: ${{p.sector || 'N/A'}}<br/>
      Capteur: ${{p.sensor || 'N/A'}}<br/>
      Source: ${{p.source || 'N/A'}}<br/>
      📍 ${{p.lat.toFixed(5)}}, ${{p.lon.toFixed(5)}}
    `).addTo(markerLayer);
  }});
}}

function renderTable(plumes) {{
  const tbody = document.getElementById('tbody');
  tbody.innerHTML = plumes.slice(0, 100).map((p, i) => `
    <tr>
      <td title="${{p.id}}">${{p.id.slice(0,22)}}</td>
      <td>${{p.date}}</td>
      <td style="text-align:right;">${{p.lat !== null ? p.lat.toFixed(4) : 'N/A'}}</td>
      <td style="text-align:right;">${{p.lon !== null ? p.lon.toFixed(4) : 'N/A'}}</td>
      <td style="text-align:right;font-weight:500;color:${{p.rate > 1000 ? '#E24B4A' : p.rate > 300 ? '#EF9F27' : 'inherit'}};">
        ${{p.rate !== null ? p.rate.toFixed(1) : 'N/A'}}
      </td>
      <td>${{p.sector}}</td>
      <td>${{p.sensor}}</td>
    </tr>
  `).join('');
  document.getElementById('table_wrap').style.display = 'block';
}}
</script>
</body>
</html>
"""

# -------- Affichage du composant --------
components.html(html_code, height=900, scrolling=True)

# -------- Export PDF (côté serveur Streamlit) --------
st.markdown("### 📄 Générer rapport PDF")
st.caption("Le PDF utilise les paramètres sélectionnés ci-dessus. Les données réelles sont dans le widget.")

if st.button("📥 Générer rapport PDF Carbon Mapper"):
    buffer = io.BytesIO()
    today = datetime.utcnow()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("<b>DATA.SAT — Carbon Mapper CH₄ Report</b>", styles["Title"]))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"<b>Gaz:</b> {cm_gas} | <b>Secteur:</b> {cm_sector}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Période:</b> {cm_date_start} → {cm_date_end}", styles["Normal"]))
    elements.append(Paragraph(
        f"<b>Zone:</b> Lat [{cm_lat_min}, {cm_lat_max}] | Lon [{cm_lon_min}, {cm_lon_max}]",
        styles["Normal"]
    ))
    elements.append(Paragraph(f"<b>Généré le:</b> {today.strftime('%Y-%m-%d %H:%M')} UTC", styles["Normal"]))
    elements.append(Spacer(1, 16))

    elements.append(Paragraph("<b>Source des données</b>", styles["Heading3"]))
    elements.append(Paragraph(
        "Carbon Mapper — Tanager-1 (Planet Labs / NASA JPL), NASA EMIT (ISS), AVIRIS-NG. "
        "Résolution spatiale : 3 à 50 mètres selon capteur. "
        "Données disponibles pour usage non-commercial (CC BY 4.0). "
        "Portail : https://data.carbonmapper.org",
        styles["Normal"]
    ))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>Zone d'analyse — Hassi Rmel</b>", styles["Heading3"]))
    zone_data = [
        ["Zone", "Lat min", "Lat max", "Lon min", "Lon max"],
        ["Centre", "32.756", "33.014", "2.928", "3.617"],
        ["Sud",    "32.451", "32.884", "2.886", "3.380"],
        ["Nord",   "33.014", "33.283", "3.185", "3.811"],
    ]
    zone_table = Table(zone_data, colWidths=[80, 70, 70, 70, 70])
    zone_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
    ]))
    elements.append(zone_table)
    elements.append(Spacer(1, 16))

    elements.append(Paragraph("<b>Analyse HSE</b>", styles["Heading3"]))
    elements.append(Paragraph(
        "Les panaches CH₄ détectés via Carbon Mapper représentent des fuites ponctuelles "
        "géolocalisées avec précision (3–50 m). Chaque panache inclut un débit estimé en kg/h "
        "permettant une priorisation des interventions terrain. "
        "Les sources oil & gas présentent le risque le plus élevé en termes d'inflammabilité et d'impact environnemental.",
        styles["Normal"]
    ))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>Actions recommandées</b>", styles["Heading3"]))
    actions = [
        ["Priorité", "Action", "Délai"],
        ["1 — Critique", "Inspection terrain sur points débit > 1000 kg/h", "Immédiat"],
        ["2 — Élevé",    "Vérification équipements zones panaches actifs",   "24–48h"],
        ["3 — Moyen",    "Surveillance renforcée secteurs suspects",          "1 semaine"],
        ["4 — Suivi",    "Remonter données Carbon Mapper chaque mois",       "Continu"],
    ]
    actions_table = Table(actions, colWidths=[90, 250, 80])
    actions_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    elements.append(actions_table)

    doc.build(elements)
    buffer.seek(0)
    st.download_button(
        label="📥 Télécharger le rapport PDF",
        data=buffer,
        file_name=f"rapport_carbonmapper_{cm_gas}_{today.strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )
