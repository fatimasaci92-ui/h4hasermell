# ================= app.py — Analyse CH4 + Rapport =================

import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import ee
import tempfile
import os
import io
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from datetime import datetime, timedelta

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

# ================= ZONES =================
zoneCentre = ee.Geometry.Polygon([[3.37696562,32.75662617],[3.61159117,32.75663435],[3.60634757,33.01349055],[2.93385218,33.02401464],[2.92757292,32.89394392],[3.3769424,32.88954646],[3.37696562,32.75662617]])
zoneSud = ee.Geometry.Polygon([[2.88567251,32.45093128],[3.37963967,32.45092697],[3.37964793,32.88379946],[2.88561768,32.88378899],[2.88567251,32.45093128]])
zoneNord = ee.Geometry.Polygon([[3.18513508,33.01358581],[3.18482285,33.28297225],[3.81093387,33.27857017],[3.81077745,33.01358819],[3.18513508,33.01358581]])
zones = [("Centre", zoneCentre),("Sud", zoneSud),("Nord", zoneNord)]

# ================= IA LÉGÈRE =================
def detect_ch4_anomaly(val):
    if np.isnan(val):
        return "❌ Pas de données", 0.0
    elif val > 1920:
        return "🔥 Fuite critique", 1.0
    elif val > 1880:
        return "⚠️ Suspect", 0.7
    else:
        return "✅ Normal", 0.1

# ================= STREAMLIT UI =================
st.set_page_config(page_title="Surveillance CH4", layout="wide")
st.title("Surveillance CH4 – Détection et Rapport")

# Choix période
days = st.number_input("Analyser les derniers jours", min_value=1, max_value=30, value=7)

if st.button("Lancer Analyse"):
    today = datetime.utcnow()
    start = today - timedelta(days=days)

    # Collection CH4
    collection = ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
    collection = collection.filterDate(start, today).select("CH4_column_volume_mixing_ratio_dry_air")
    image = collection.mean()

    results = []
    critical_points = []

    # Analyse par zone
    for name, zone in zones:
        try:
            val = image.reduceRegion(reducer=ee.Reducer.mean(), geometry=zone, scale=7000, maxPixels=1e9, bestEffort=True).getInfo()["CH4_column_volume_mixing_ratio_dry_air"]
        except:
            val = np.nan

        status, score = detect_ch4_anomaly(val)

        coords = zone.centroid().coordinates().getInfo()
        lon, lat = coords

        results.append([name, round(val,2) if val else 'N/A', status, round(score,2), lat, lon])
        if status == "🔥 Fuite critique":
            critical_points.append({'lat': lat, 'lon': lon, 'zone': name, 'val': val})

    # Affichage tableau
    df = pd.DataFrame(results, columns=["Zone","CH4 (ppb)","Statut IA","Score IA","Lat","Lon"])
    st.dataframe(df)

    # ================= CARTE =================
    if df.shape[0] > 0:
        if critical_points:
            center_lat = critical_points[0]['lat']
            center_lon = critical_points[0]['lon']
        else:
            center_lat = np.mean([r[4] for r in results])
            center_lon = np.mean([r[5] for r in results])

        m = folium.Map(location=[center_lat, center_lon], zoom_start=10)

        for r in results:
            color = "green" if r[2]=="✅ Normal" else ("orange" if r[2]=="⚠️ Suspect" else "red")
            folium.CircleMarker([r[4], r[5]], radius=10, color=color, fill=True, fill_opacity=0.7, tooltip=f"{r[0]}: {r[2]} ({r[1]} ppb)").add_to(m)

        st_folium(m, width=800, height=500)

        # ================= PDF =================
        if st.button("📄 Générer Rapport PDF"):
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            elements = []

            elements.append(Paragraph("<b>DATA.SAT</b>", styles['Title']))
            elements.append(Paragraph(f"Date: {today.strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
            elements.append(Spacer(1,12))

            # Tableau
            table = Table([df.columns.tolist()] + df.values.tolist(), colWidths=[70,70,80,60,60,60])
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#1f4e79")),
                ('TEXTCOLOR',(0,0),(-1,0),colors.white),
                ('ALIGN',(0,0),(-1,-1),'CENTER'),
                ('GRID',(0,0),(-1,-1),0.5,colors.black),
                ('BACKGROUND',(0,1),(-1,-1),colors.whitesmoke),
            ]))
            elements.append(table)
            elements.append(Spacer(1,12))

            # Capture carte + plume
            if critical_points:
                try:
                    import matplotlib.pyplot as plt
                    fig, ax = plt.subplots()
                    ax.scatter([p['lon'] for p in critical_points],[p['lat'] for p in critical_points], color='red', s=200)
                    ax.set_title("Point(s) critique(s) de fuite")
                    ax.set_xlabel("Longitude")
                    ax.set_ylabel("Latitude")
                    img_path = os.path.join(tempfile.gettempdir(),"critical_points.png")
                    plt.savefig(img_path, bbox_inches='tight', dpi=300)
                    plt.close()

                    elements.append(Paragraph("<b>Carte des points critiques</b>", styles['Heading3']))
                    elements.append(Image(img_path, width=6*inch, height=4*inch))
                except Exception as e:
                    st.warning(f"Erreur image plume: {e}")

            doc.build(elements)
            buffer.seek(0)
            st.download_button("📥 Télécharger PDF", data=buffer, file_name=f"rapport_CH4_{today.strftime('%Y%m%d')}.pdf", mime="application/pdf")
