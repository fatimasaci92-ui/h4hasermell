import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

# ================= CONFIG =================

st.set_page_config(page_title="Surveillance CH4 – HSE", layout="wide")

# ================= PATHS =================

dataDir = "data"
meanDir = os.path.join(dataDir, "Moyenne CH4")
anomalyDir = os.path.join(dataDir, "anomaly CH4")
csvDir = os.path.join(dataDir, "2020 2024")

meanFiles = {year: os.path.join(meanDir, f"CH4_mean_{year}.tif") for year in range(2020, 2026)}
anomalyFiles = {year: os.path.join(anomalyDir, f"CH4_anomaly_{year}.tif") for year in range(2020, 2026)}

csvGlobal = os.path.join(csvDir, "CH4_HassiRmel_2020_2024.csv")
csvAnnual = os.path.join(csvDir, "CH4_HassiRmel_annual_2020_2024.csv")
csvMonthly = os.path.join(csvDir, "CH4_HassiRmel_monthly_2020_2024.csv")
csvDailyAnom = os.path.join(csvDir, "Anomalies_CH4_HassiRmel.csv")
csvDaily2025 = os.path.join(csvDir, "CH4_daily_2025.csv")
csvAnnual2025 = os.path.join(csvDir, "CH4_annual_2020_2025.csv")

# ================= SESSION STATE =================

if "analysisToday" not in st.session_state:
st.session_state["analysisToday"] = None

# ================= UTIL FUNCTIONS =================

def hazopAnalysis(ch4Value: float) -> pd.DataFrame:
data = []
if ch4Value < 1800:
data.append(["CH₄", "Normal", "Pas d’anomalie", "Fonctionnement normal", "Surveillance continue"])
elif ch4Value < 1850:
data.append(["CH₄", "Modérément élevé", "Torchage possible", "Risque faible d’incident", "Vérifier torches et informer l'équipe HSE"])
elif ch4Value < 1900:
data.append(["CH₄", "Élevé", "Fuite probable", "Risque d’explosion accru", "Inspection urgente du site et mesures de sécurité immédiates"])
else:
data.append(["CH₄", "Critique", "Fuite majeure", "Risque critique d’explosion/incendie", "Alerter direction, sécuriser zone, stopper les opérations si nécessaire"])
return pd.DataFrame(data, columns=["Paramètre","Déviation","Cause","Conséquence","Action HSE"])

def generatePDFBytes(siteName, latitude, longitude, reportDate, ch4Value, anomalyFlag, actionHSE, hazopDF=None) -> bytes:
buffer = io.BytesIO()
doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Rapport_HSE_{siteName}_{reportDate}")
styles = getSampleStyleSheet()
story = []

```
# TITRE
story.append(Paragraph(f"<para align='center'><b><font size=16>RAPPORT HSE – SURVEILLANCE MÉTHANE (CH₄)</font></b></para>", styles["Title"]))
story.append(Spacer(1,12))

# META
timeStr = datetime.now().strftime("%H:%M")
story.append(Paragraph(f"<b>Date :</b> {reportDate}<br/><b>Heure :</b> {timeStr}<br/><b>Site :</b> {siteName}<br/><b>Latitude :</b> {latitude}<br/><b>Longitude :</b> {longitude}<br/>", styles["Normal"]))
story.append(Spacer(1,12))

# EXPLICATION
explanation = f"Ce rapport présente l'analyse automatisée du niveau de méthane (CH₄) détecté sur le site <b>{siteName}</b>. La surveillance du CH₄ permet d'identifier les anomalies, d'évaluer le niveau de risque HSE et de recommander des actions."
story.append(Paragraph(explanation, styles["Normal"]))
story.append(Spacer(1,12))

# TABLEAU PRINCIPAL
tableData = [["Paramètre","Valeur"], ["Concentration CH₄ (ppb)", f"{ch4Value:.2f}"], ["Anomalie détectée", "Oui" if anomalyFlag else "Non"], ["Action recommandée HSE", actionHSE]]
table = Table(tableData, colWidths=[180,260])
table.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0B4C6E")),
    ("TEXTCOLOR",(0,0),(-1,0),colors.white),
    ("ALIGN",(0,0),(-1,-1),"LEFT"),
    ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
    ("BACKGROUND",(0,1),(-1,-1),colors.whitesmoke),
    ("GRID",(0,0),(-1,-1),0.8,colors.grey)
]))
story.append(table)
story.append(Spacer(1,16))

# CAUSES
causeText = "<b>Causes possibles d'une anomalie CH₄ :</b><br/>- Fuite sur canalisation ou bride endommagée<br/>- Torchage défaillant<br/>- Purge de gaz ou opération de maintenance<br/>- Pression anormale dans le réseau<br/>"
story.append(Paragraph(causeText, styles["Normal"]))
story.append(Spacer(1,12))

# ACTIONS
actionText = "<b>Actions recommandées (niveau critique) :</b><br/>- Alerter immédiatement la direction HSE<br/>- Sécuriser/évacuer la zone si nécessaire<br/>- Localiser la fuite avec OGI / capteurs portables<br/>- Réparer ou isoler la section affectée, stopper opérations si besoin" if anomalyFlag else "<b>Actions recommandées :</b><br/>- Surveillance continue<br/>- Contrôles périodiques et maintenance préventive"
story.append(Paragraph(actionText, styles["Normal"]))
story.append(Spacer(1,12))

# HAZOP
if hazopDF is not None and not hazopDF.empty:
    hazopData = [list(hazopDF.columns)] + hazopDF.values.tolist()
    hazopTable = Table(hazopData, colWidths=[100]*len(hazopDF.columns))
    hazopTable.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0B4C6E")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("BACKGROUND",(0,1),(-1,-1),colors.whitesmoke),
        ("GRID",(0,0),(-1,-1),0.8,colors.grey)
    ]))
    story.append(Spacer(1,12))
    story.append(Paragraph("<b>Tableau HAZOP :</b>", styles["Normal"]))
    story.append(Spacer(1,6))
    story.append(hazopTable)
    story.append(Spacer(1,12))

# FOOTER
story.append(Paragraph("<para align='center'><font size=9 color='#6B7280'>Rapport généré automatiquement — Système HSE CH₄</font></para>", styles["Normal"]))
doc.build(story)
pdfData = buffer.getvalue()
buffer.close()
return pdfData
```

# ================= UI =================

def uiHeader():
st.title("Surveillance du Méthane – HSE")
st.markdown("## Dashboard interactif CH₄ + HSE")
latitude = st.number_input("Latitude du site", value=32.93, format="%.6f")
longitude = st.number_input("Longitude du site", value=3.3, format="%.6f")
siteName = st.text_input("Nom du site", value="Hassi R'mel")
return latitude, longitude, siteName

def main():
latitude, longitude, siteName = uiHeader()

```
# SECTION A
if st.button("Afficher le contenu des sous-dossiers"):
    st.write("Moyenne CH4 :", os.listdir(meanDir) if os.path.exists(meanDir) else "Introuvable")
    st.write("Anomalies CH4 :", os.listdir(anomalyDir) if os.path.exists(anomalyDir) else "Introuvable")
    st.write("CSV 2020-2025 :", os.listdir(csvDir) if os.path.exists(csvDir) else "Introuvable")

# SECTION E: Analyse du jour
if st.button("Analyser aujourd'hui"):
    analysis = analyzeToday()
    st.write(analysis)
```

if **name** == "**main**":
main()
