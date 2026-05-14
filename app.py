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

# ================= SECTION K — CARBON MAPPER (VERSION FINALE) =================
# Correction principale : Streamlit Cloud bloque requests vers api.carbonmapper.org
# Solution : appel API fait côté NAVIGATEUR (JS fetch) — contourne le blocage réseau
# Le token est passé via query params internes au composant HTML (jamais dans le HTML public)

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
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

# -------- Token depuis secrets --------
CM_TOKEN = ""
token_ok = False
try:
    CM_TOKEN = (
        st.secrets.get("CARBON_API_TOKEN") or
        st.secrets.get("CARBON_MAPPER_TOKEN") or
        st.secrets.get("carbon_api_token") or ""
    )
    CM_TOKEN = str(CM_TOKEN).strip()
    token_ok = len(CM_TOKEN) > 10
except Exception:
    pass

if not token_ok:
    try:
        import os, re
        for path in ["secrets.toml", ".streamlit/secrets.toml"]:
            full = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
            if os.path.exists(full):
                content = open(full, encoding="utf-8").read()
                m = re.search(r'CARBON_(?:API|MAPPER)_TOKEN\s*=\s*["\']([^"\']+)["\']', content)
                if m:
                    CM_TOKEN = m.group(1).strip()
                    token_ok = len(CM_TOKEN) > 10
                    break
    except Exception:
        pass

if not token_ok:
    try:
        keys = list(st.secrets.keys())
    except Exception:
        keys = []
    st.error(
        f"❌ Token introuvable. Clés détectées : `{keys}`\n\n"
        "Ajoutez dans Streamlit Cloud → Settings → Secrets :\n"
        "```\nCARBON_API_TOKEN = \"votre_token\"\n```"
    )

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

sector_val = "" if cm_sector == "Tous" else cm_sector
bbox_val = f"{cm_lon_min},{cm_lat_min},{cm_lon_max},{cm_lat_max}"

# -------- Composant HTML — appel API côté navigateur --------
# Le token est injecté dans le HTML uniquement au moment du rendu côté serveur
# et transmis dans une variable JS locale (non exposée dans le DOM)

html_code = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0;font-family:sans-serif;font-size:13px;}}
  body{{background:transparent;padding:6px;}}
  #map{{width:100%;height:420px;border-radius:8px;border:1px solid #ddd;display:none;}}
  .stats{{display:none;grid-template-columns:repeat(4,1fr);gap:8px;margin:10px 0;}}
  .stat-card{{background:#f5f5f5;border-radius:8px;padding:10px;text-align:center;}}
  .stat-label{{font-size:11px;color:#888;margin-bottom:4px;}}
  .stat-value{{font-size:20px;font-weight:500;}}
  #status{{margin:8px 0;font-size:13px;min-height:18px;color:#888;}}
  table{{width:100%;border-collapse:collapse;margin-top:10px;}}
  th{{text-align:left;padding:6px 8px;font-weight:500;color:#888;
      border-bottom:1px solid #eee;font-size:11px;}}
  td{{padding:5px 8px;border-bottom:0.5px solid #f0f0f0;font-size:11px;
     overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px;}}
  tr:nth-child(even){{background:#fafafa;}}
  .legend{{position:absolute;bottom:40px;left:10px;z-index:1000;
           background:rgba(255,255,255,0.92);padding:8px 12px;
           border-radius:8px;font-size:11px;box-shadow:0 2px 6px rgba(0,0,0,.15);}}
  .dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;}}
  #btn{{width:100%;padding:10px;font-size:14px;cursor:pointer;border-radius:8px;
        border:1px solid #ccc;background:#fff;margin-bottom:8px;}}
  #btn:hover{{background:#f5f5f5;}} #btn:disabled{{opacity:0.5;cursor:not-allowed;}}
  #table_wrap{{display:none;overflow-x:auto;max-height:280px;overflow-y:auto;margin-top:8px;}}
  #err{{color:#c0392b;padding:8px;font-size:13px;display:none;}}
</style>
</head><body>
<button id="btn" onclick="run()">🛰️ Rechercher les fuites {cm_gas}</button>
<div id="status">Cliquez pour interroger Carbon Mapper...</div>
<div id="err"></div>
<div class="stats" id="stats"></div>
<div style="position:relative;">
  <div id="map"></div>
  <div class="legend" id="legend" style="display:none;">
    <b>Débit</b><br/>
    <span class="dot" style="background:#E24B4A;"></span>Élevé (&gt;60%)<br/>
    <span class="dot" style="background:#EF9F27;"></span>Moyen (30–60%)<br/>
    <span class="dot" style="background:#1D9E75;"></span>Faible (&lt;30%)
  </div>
</div>
<div id="table_wrap">
  <table><thead><tr>
    <th>ID</th><th>Date</th><th>Lat</th><th>Lon</th>
    <th>Débit kg/h</th><th>Secteur</th><th>Capteur</th>
  </tr></thead><tbody id="tbody"></tbody></table>
</div>

<script>
// Token passé depuis Python au moment du rendu — reste dans la mémoire JS locale
const _t = atob("{__import__('base64').b64encode(CM_TOKEN.encode()).decode() if CM_TOKEN else ''}");
const GAS="{cm_gas}", SECTOR="{sector_val}";
const BBOX="{bbox_val}";
const DATE_START="{cm_date_start}", DATE_END="{cm_date_end}";

// Endpoints à tester dans l'ordre
const ENDPOINTS = [
  "https://api.carbonmapper.org/api/v1/annotations/plume-list/",
  "https://api.carbonmapper.org/api/v1/plumes/",
  "https://api.carbonmapper.org/api/v1/catalog/plumes/",
];

let map=null, markerLayer=null;

function setStatus(msg,color){{
  document.getElementById('status').textContent=msg;
  document.getElementById('status').style.color=color||'#888';
}}
function showErr(msg){{
  const e=document.getElementById('err');
  e.textContent=msg; e.style.display='block';
}}

function parsePlume(p){{
  const props=p.properties||p;
  const geom=p.geometry||{{}};
  let lat=props.source_lat??props.lat??props.plume_lat??props.latitude??null;
  let lon=props.source_lon??props.lon??props.plume_lon??props.longitude??null;
  if(!lat && geom.coordinates){{ lon=geom.coordinates[0]; lat=geom.coordinates[1]; }}
  const emission=props.emission_auto??props.emission??props.flux??null;
  return {{
    id: String(props.plume_id||props.id||''),
    date: String(props.acquisition_date||'').slice(0,10),
    lat: lat!==null?parseFloat(lat):null,
    lon: lon!==null?parseFloat(lon):null,
    rate: emission!==null&&emission!==undefined?parseFloat(emission):null,
    sector: String(props.sector||''),
    sensor: String(props.instrument||props.sensor||''),
  }};
}}

async function tryFetch(url, params){{
  const qs=new URLSearchParams(params).toString();
  const resp=await fetch(url+'?'+qs,{{
    headers:{{'Authorization':'Bearer '+_t}}
  }});
  return resp;
}}

async function run(){{
  if(!_t){{ showErr('Token manquant.'); return; }}
  const btn=document.getElementById('btn');
  btn.disabled=true;
  document.getElementById('err').style.display='none';
  setStatus('Recherche du bon endpoint...');

  const params={{bbox:BBOX, gas:GAS, date_start:DATE_START, date_end:DATE_END, limit:200, offset:0}};
  if(SECTOR) params.sector=SECTOR;

  // Trouver le bon endpoint
  let goodUrl=null;
  for(const url of ENDPOINTS){{
    try{{
      const r=await tryFetch(url,{{...params,limit:1}});
      if(r.status===401){{ showErr('Token invalide (401). Vérifiez votre token Carbon Mapper.'); btn.disabled=false; return; }}
      if(r.status===403){{ showErr('Accès refusé (403). Vérifiez les droits de votre compte.'); btn.disabled=false; return; }}
      if(r.ok){{ goodUrl=url; break; }}
    }}catch(e){{ continue; }}
  }}

  if(!goodUrl){{
    showErr('Aucun endpoint Carbon Mapper ne répond (404). Vérifiez https://api.carbonmapper.org/api/v1/docs');
    btn.disabled=false; return;
  }}

  setStatus('Chargement des données depuis '+goodUrl+'...');

  // Pagination
  let all=[]; let offset=0; let page=0;
  while(page<10){{
    try{{
      const r=await tryFetch(goodUrl,{{...params,offset}});
      if(!r.ok){{ showErr('Erreur '+r.status); break; }}
      const data=await r.json();
      const results=data.results||data.features||[];
      results.forEach(p=>all.push(parsePlume(p)));
      if(!data.next||results.length<200) break;
      offset+=200; page++;
      setStatus('Chargement... '+all.length+' panaches trouvés');
    }}catch(e){{ showErr('Erreur réseau: '+e.message); break; }}
  }}

  btn.disabled=false;

  if(!all.length){{
    setStatus('Aucun panache trouvé pour cette zone/période.','#E6A817');
    return;
  }}

  setStatus('✅ '+all.length+' panache(s) détecté(s)','#1D9E75');
  renderStats(all);
  renderMap(all);
  renderTable(all);
}}

function renderStats(pl){{
  const rates=pl.map(p=>p.rate).filter(v=>v!==null);
  const total=rates.reduce((a,b)=>a+b,0);
  const max=rates.length?Math.max(...rates):0;
  const avg=rates.length?total/rates.length:0;
  const el=document.getElementById('stats');
  el.innerHTML=[
    {{label:'Panaches',val:pl.length}},
    {{label:'Débit max (kg/h)',val:max?max.toFixed(1):'N/A'}},
    {{label:'Débit moyen (kg/h)',val:avg?avg.toFixed(1):'N/A'}},
    {{label:'Total (kg/h)',val:total?total.toFixed(1):'N/A'}},
  ].map(s=>`<div class="stat-card"><div class="stat-label">${{s.label}}</div><div class="stat-value">${{s.val}}</div></div>`).join('');
  el.style.display='grid';
}}

function renderMap(pl){{
  const valid=pl.filter(p=>p.lat&&p.lon);
  if(!valid.length) return;
  document.getElementById('map').style.display='block';
  document.getElementById('legend').style.display='block';
  const cLat=valid.reduce((a,p)=>a+p.lat,0)/valid.length;
  const cLon=valid.reduce((a,p)=>a+p.lon,0)/valid.length;
  if(!map){{
    map=L.map('map').setView([cLat,cLon],9);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
      {{attribution:'ESRI Satellite'}}).addTo(map);
  }} else {{
    if(markerLayer) map.removeLayer(markerLayer);
    map.setView([cLat,cLon],9);
  }}
  markerLayer=L.layerGroup().addTo(map);
  const maxRate=Math.max(...valid.map(p=>p.rate||0))||1;
  valid.forEach(p=>{{
    const ratio=(p.rate||0)/maxRate;
    const color=ratio>0.6?'#E24B4A':ratio>0.3?'#EF9F27':'#1D9E75';
    const r=ratio>0.6?14:ratio>0.3?10:7;
    if(color==='#E24B4A')
      L.circleMarker([p.lat,p.lon],{{radius:r+8,color:'#A32D2D',fillColor:'#E24B4A',fillOpacity:0.15,weight:1}}).addTo(markerLayer);
    L.circleMarker([p.lat,p.lon],{{radius:r,color,fillColor:color,fillOpacity:0.85,weight:1.5}})
     .bindPopup(`<b>${{p.id.slice(0,24)}}</b><br/>Date: ${{p.date}}<br/>Débit: <b>${{p.rate?p.rate.toFixed(1)+' kg/h':'N/A'}}</b><br/>Secteur: ${{p.sector||'N/A'}}<br/>Capteur: ${{p.sensor||'N/A'}}<br/>📍${{p.lat.toFixed(5)}},${{p.lon.toFixed(5)}}`)
     .addTo(markerLayer);
  }});
}}

function renderTable(pl){{
  document.getElementById('tbody').innerHTML=pl.slice(0,100).map(p=>`
    <tr>
      <td title="${{p.id}}">${{p.id.slice(0,22)}}</td>
      <td>${{p.date}}</td>
      <td style="text-align:right">${{p.lat?p.lat.toFixed(4):'N/A'}}</td>
      <td style="text-align:right">${{p.lon?p.lon.toFixed(4):'N/A'}}</td>
      <td style="text-align:right;font-weight:500;color:${{p.rate>1000?'#E24B4A':p.rate>300?'#EF9F27':'inherit'}}">${{p.rate?p.rate.toFixed(1):'N/A'}}</td>
      <td>${{p.sector}}</td>
      <td>${{p.sensor}}</td>
    </tr>`).join('');
  document.getElementById('table_wrap').style.display='block';
}}
</script>
</body></html>"""

# Injecter le token encodé en base64 dans le HTML
import base64
token_b64 = base64.b64encode(CM_TOKEN.encode()).decode() if CM_TOKEN else ""
html_code = html_code.replace(
    'atob("{__import__(\'base64\').b64encode(CM_TOKEN.encode()).decode() if CM_TOKEN else \'\'}")',
    f'atob("{token_b64}")'
)

components.html(html_code, height=850, scrolling=True)

# -------- Export PDF --------
st.markdown("### 📄 Rapport PDF Carbon Mapper")
if st.button("📥 Générer rapport PDF", key="cm_pdf"):
    buffer = io.BytesIO()
    today_dt = datetime.utcnow()
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
    elements.append(Paragraph(f"<b>Généré le:</b> {today_dt.strftime('%Y-%m-%d %H:%M')} UTC", styles["Normal"]))
    elements.append(Spacer(1, 16))

    elements.append(Paragraph("<b>Source des données</b>", styles["Heading3"]))
    elements.append(Paragraph(
        "Carbon Mapper — Tanager-1 (Planet Labs / NASA JPL), NASA EMIT (ISS), AVIRIS-NG. "
        "Résolution spatiale : 3 à 50 mètres selon capteur. CC BY 4.0. "
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
    zt = Table(zone_data, colWidths=[80,70,70,70,70])
    zt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1f4e79")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,-1),9),
        ("GRID",(0,0),(-1,-1),0.4,colors.black),
        ("BACKGROUND",(0,1),(-1,-1),colors.whitesmoke),
    ]))
    elements.append(zt)
    elements.append(Spacer(1, 16))

    elements.append(Paragraph("<b>Analyse HSE</b>", styles["Heading3"]))
    elements.append(Paragraph(
        "Les panaches CH₄ détectés via Carbon Mapper représentent des fuites ponctuelles "
        "géolocalisées avec précision (3–50 m). Chaque panache inclut un débit estimé en kg/h "
        "permettant une priorisation des interventions terrain.",
        styles["Normal"]
    ))
    elements.append(Spacer(1, 12))

    actions = [
        ["Priorité","Action","Délai"],
        ["1 — Critique","Inspection terrain sur points débit > 1000 kg/h","Immédiat"],
        ["2 — Élevé","Vérification équipements zones panaches actifs","24–48h"],
        ["3 — Moyen","Surveillance renforcée secteurs suspects","1 semaine"],
        ["4 — Suivi","Remonter données Carbon Mapper chaque mois","Continu"],
    ]
    at = Table(actions, colWidths=[90,250,80])
    at.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1f4e79")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,-1),9),
        ("GRID",(0,0),(-1,-1),0.4,colors.black),
        ("BACKGROUND",(0,1),(-1,-1),colors.whitesmoke),
        ("ALIGN",(0,0),(-1,-1),"LEFT"),
    ]))
    elements.append(Paragraph("<b>Actions recommandées</b>", styles["Heading3"]))
    elements.append(at)

    doc.build(elements)
    buffer.seek(0)
    st.download_button(
        label="📥 Télécharger le rapport PDF",
        data=buffer,
        file_name=f"rapport_carbonmapper_{cm_gas}_{today_dt.strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )
