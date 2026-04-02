# ================= SECTION I — PDF Professionnel HSI =================
st.markdown("## 📝 Générer rapport PDF professionnel HSI")

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
import io

if st.button("Générer rapport PDF professionnel"):

    today = datetime.utcnow()
    start = today - timedelta(days=7)

    # Collection CH4
    collection = ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4") \
        .filterDate(start, today) \
        .select("CH4_column_volume_mixing_ratio_dry_air")
    image = collection.mean()

    zones = [("Centre", zoneCentre), ("Sud", zoneSud), ("Nord", zoneNord)]
    results = []

    # Analyse par zone
    for name, zone in zones:
        value = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=zone,
            scale=7000,
            maxPixels=1e9,
            bestEffort=True
        ).get("CH4_column_volume_mixing_ratio_dry_air")

        try:
            val = value.getInfo()
        except:
            val = None

        status_ia, score = detect_ch4_anomaly(np.array([[val]]) if val else np.array([[np.nan]]))

        # Niveau HSI
        if status_ia == "🔥 Fuite critique":
            hsi_level = "Risque élevé"
            color = colors.red
            action = "Intervention immédiate + maintenance"
        elif status_ia == "⚠️ Suspect":
            hsi_level = "Risque moyen"
            color = colors.orange
            action = "Surveillance renforcée"
        else:
            hsi_level = "Faible"
            color = colors.green
            action = "Continuer suivi standard"

        # Coordonnées approximatives du centre de la zone
        coords_raw = zone.coordinates().getInfo()
        all_lats = []
        all_lons = []
        for poly in coords_raw:
            for lon, lat in poly:
                all_lats.append(lat)
                all_lons.append(lon)
        center_lat = round((max(all_lats)+min(all_lats))/2, 5)
        center_lon = round((max(all_lons)+min(all_lons))/2, 5)

        results.append({
            "Zone": name,
            "CH4": round(val,2) if val else "No data",
            "IA": status_ia,
            "Score": round(score,2),
            "HSI": hsi_level,
            "Action": action,
            "Color": color,
            "Lat": center_lat,
            "Lon": center_lon
        })

    # Création PDF
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Titre
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawCentredString(width/2, height - 40, "Rapport HSI - CH₄")

    # Date
    pdf.setFont("Helvetica", 12)
    pdf.drawString(40, height - 70, f"Date du rapport : {today.strftime('%Y-%m-%d')}")

    y = height - 110
    pdf.setFont("Helvetica", 12)

    for r in results:
        if y < 100:  # Nouvelle page si bas
            pdf.showPage()
            pdf.setFont("Helvetica", 12)
            y = height - 50

        # Zone
        pdf.setFillColor(r["Color"])
        pdf.drawString(40, y, f"Zone : {r['Zone']} — Niveau HSI : {r['HSI']}")
        y -= 18

        # Coordonnées
        pdf.setFillColor(colors.black)
        pdf.drawString(50, y, f"Coordonnées : Latitude {r['Lat']}, Longitude {r['Lon']}")
        y -= 15

        # CH4 et IA
        pdf.drawString(50, y, f"CH₄ : {r['CH4']} ppb — IA : {r['IA']} (Score {r['Score']})")
        y -= 15

        # Action recommandée
        pdf.drawString(50, y, f"Action recommandée : {r['Action']}")
        y -= 25

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    st.download_button(
        label="Télécharger rapport PDF professionnel HSI",
        data=buffer,
        file_name=f"rapport_HSI_CH4_professionnel_{today.strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )
