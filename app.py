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

# ================= INFORMATIONS SITE =================
st.title("Surveillance du Méthane – HSE")
st.markdown("## Dashboard interactif CH₄ + HSE")

latitude = st.number_input("Latitude du site", value=32.93, format="%.6f")
longitude = st.number_input("Longitude du site", value=3.3, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")
site_geom = (latitude, longitude)

# ================= PATHS =================
DATA_DIR = "data"
MEAN_DIR = os.path.join(DATA_DIR, "Moyenne CH4")
ANOMALY_DIR = os.path.join(DATA_DIR, "anomaly CH4")
CSV_DIR = os.path.join(DATA_DIR, "2020 2024")

# TIF 2020–2025
mean_files = {year: os.path.join(MEAN_DIR, f"CH4_mean_{year}.tif") for year in range(2020, 2026)}
anomaly_files = {year: os.path.join(ANOMALY_DIR, f"CH4_anomaly_{year}.tif") for year in range(2020, 2026)}

# CSV
csv_global = os.path.join(CSV_DIR, "CH4_HassiRmel_2020_2024.csv")
csv_annual = os.path.join(CSV_DIR, "CH4_HassiRmel_annual_2020_2024.csv")
csv_monthly = os.path.join(CSV_DIR, "CH4_HassiRmel_monthly_2020_2024.csv")
csv_daily_anom = os.path.join(CSV_DIR, "Anomalies_CH4_HassiRmel.csv")
csv_daily_2025 = os.path.join(CSV_DIR, "CH4_daily_2025.csv")
csv_annual_2025 = os.path.join(CSV_DIR, "CH4_annual_2020_2025.csv")

# ================= SESSION STATE INIT =================
if "analysis_today" not in st.session_state:
st.session_state["analysis_today"] = None # dict avec ch4_today, threshold, action, date

# ================= UTIL FUNCTIONS =================
def hazop_analysis(ch4_value: float) -> pd.DataFrame:
data = []
if ch4_value < 1800:
data.append([
"CH₄", "Normal", "Pas d’anomalie",
"Fonctionnement normal", "Surveillance continue"
])
elif ch4_value < 1850:
data.append([
"CH₄", "Modérément élevé", "Torchage possible",
"Risque faible d’incident", "Vérifier torches et informer l'équipe HSE"
])
elif ch4_value < 1900:
data.append([
"CH₄", "Élevé", "Fuite probable",
"Risque d’explosion accru", "Inspection urgente du site et mesures de sécurité immédiates"
])
else:
data.append([
"CH₄", "Critique", "Fuite majeure",
"Risque critique d’explosion/incendie",
"Alerter direction, sécuriser zone, stopper les opérations si nécessaire"
])
return pd.DataFrame(
data,
columns=["Paramètre", "Déviation", "Cause", "Conséquence", "Action HSE"]
)


def generate_pdf_bytes_professional(
site_name: str,
latitude: float,
longitude: float,
report_date: str,
ch4_value: float,
anomaly_flag: bool,
action_hse: str,
hazop_df: pd.DataFrame | None = None
) -> bytes:
buffer = io.BytesIO()
doc = SimpleDocTemplate(
buffer,
pagesize=A4,
title=f"Rapport_HSE_{site_name}_{report_date}"
)
styles = getSampleStyleSheet()
story = []

# TITRE
story.append(
Paragraph(
"<para align='center'><b><font size=16>"
"RAPPORT HSE – SURVEILLANCE MÉTHANE (CH₄)"
"</font></b></para>",
styles["Title"],
)
)
story.append(Spacer(1, 12))

# META
date_str = report_date
time_str = datetime.now().strftime("%H:%M")
meta = (
f"<b>Date :</b> {date_str}<br/>"
f"<b>Heure :</b> {time_str}<br/>"
f"<b>Site :</b> {site_name}<br/>"
f"<b>Latitude :</b> {latitude}<br/>"
f"<b>Longitude :</b> {longitude}<br/>"
)
story.append(Paragraph(meta, styles["Normal"]))
story.append(Spacer(1, 12))

# EXPLICATION
explanation = (
"Ce rapport présente l'analyse automatisée du niveau de méthane (CH₄) détecté "
f"sur le site <b>{site_name}</b>. La surveillance du CH₄ permet d'identifier les anomalies, "
"d'évaluer le niveau de risque HSE et de recommander des actions."
)
story.append(Paragraph(explanation, styles["Normal"]))
story.append(Spacer(1, 12))

# TABLEAU PRINCIPAL
table_data = [
["Paramètre", "Valeur"],
["Concentration CH₄ (ppb)", f"{ch4_value:.2f}"],
["Anomalie détectée", "Oui" if anomaly_flag else "Non"],
["Action recommandée HSE", action_hse],
]
table = Table(table_data, colWidths=[180, 260])
table.setStyle(
TableStyle(
[
("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B4C6E")),
("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
("ALIGN", (0, 0), (-1, -1), "LEFT"),
("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
("GRID", (0, 0), (-1, -1), 0.8, colors.grey),
]
)
)
story.append(table)
story.append(Spacer(1, 16))

# CAUSES POSSIBLES
cause_text = (
"<b>Causes possibles d'une anomalie CH₄ :</b><br/>"
"- Fuite sur canalisation ou bride endommagée<br/>"
"- Torchage défaillant<br/>"
"- Purge de gaz ou opération de maintenance<br/>"
"- Pression anormale dans le réseau<br/>"
)
story.append(Paragraph(cause_text, styles["Normal"]))
story.append(Spacer(1, 12))

# INTERPRETATION / RECOMMANDATIONS
if anomaly_flag:
action_text = (
"<b>Actions recommandées (niveau critique) :</b><br/>"
"- Alerter immédiatement la direction HSE<br/>"
"- Sécuriser/évacuer la zone si nécessaire<br/>"
"- Localiser la fuite avec OGI / capteurs portables<br/>"
"- Réparer ou isoler la section affectée, stopper opérations si besoin"
)
else:
action_text = (
"<b>Actions recommandées :</b><br/>"
"- Surveillance continue<br/>"
"- Contrôles périodiques et maintenance préventive"
)
story.append(Paragraph(action_text, styles["Normal"]))
story.append(Spacer(1, 12))

# HAZOP (optionnel)
if hazop_df is not None and not hazop_df.empty:
hazop_data = [list(hazop_df.columns)] + hazop_df.values.tolist()
hazop_table = Table(hazop_data, colWidths=[100] * len(hazop_df.columns))
hazop_table.setStyle(
TableStyle(
[
("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B4C6E")),
("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
("ALIGN", (0, 0), (-1, -1), "CENTER"),
("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
("GRID", (0, 0), (-1, -1), 0.8, colors.grey),
]
)
)
story.append(Spacer(1, 12))
story.append(Paragraph("<b>Tableau HAZOP :</b>", styles["Normal"]))
story.append(Spacer(1, 6))
story.append(hazop_table)
story.append(Spacer(1, 12))

# FOOTER
footer = (
"<para align='center'><font size=9 color='#6B7280'>"
"Rapport généré automatiquement — Système HSE CH₄"
"</font></para>"
)
story.append(Paragraph(footer, styles["Normal"]))

doc.build(story)
pdf_data = buffer.getvalue()
buffer.close()
return pdf_data


# ===================== SECTION A: Contenu des sous-dossiers =====================
st.markdown("##  Contenu des sous-dossiers")
if st.button("Afficher le contenu des sous-dossiers"):
st.write("Moyenne CH4 :", os.listdir(MEAN_DIR) if os.path.exists(MEAN_DIR) else "Introuvable")
st.write("Anomalies CH4 :", os.listdir(ANOMALY_DIR) if os.path.exists(ANOMALY_DIR) else "Introuvable")
st.write("CSV 2020-2025 :", os.listdir(CSV_DIR) if os.path.exists(CSV_DIR) else "Introuvable")

# ===================== SECTION B: Aperçu CSV annuel =====================
st.markdown("##  Aperçu CSV annuel")
if st.button("Afficher aperçu CSV annuel"):
for csv_file in [csv_annual_2025, csv_annual]:
if os.path.exists(csv_file):
try:
df_tmp = pd.read_csv(csv_file)
st.write(os.path.basename(csv_file))
st.dataframe(df_tmp.head())
break
except Exception as e:
st.error(f"Erreur lecture {csv_file}: {e}")

# ===================== SECTION C: Cartes par année =====================
st.markdown("##  Cartes Moyenne & Anomalie par année")
year_choice = st.selectbox("Choisir l'année", [2020, 2021, 2022, 2023, 2024, 2025])

if st.button("Afficher les cartes de l'année sélectionnée"):
col1, col2 = st.columns(2)

with col1:
st.subheader(f"CH₄ moyen {year_choice}")
mean_path = mean_files.get(year_choice)
if mean_path and os.path.exists(mean_path):
try:
with rasterio.open(mean_path) as src:
arr = src.read(1)
arr = np.array(arr, dtype=float)
arr[arr <= 0] = np.nan
fig, ax = plt.subplots(figsize=(6, 5))
im = ax.imshow(arr, cmap="viridis")
ax.set_title(f"CH₄ moyen {year_choice}")
ax.axis("off")
plt.colorbar(im, ax=ax, shrink=0.8)
st.pyplot(fig)
plt.close(fig)
except Exception as e:
st.error(f"Erreur affichage CH4 mean: {e}")
else:
st.warning("Fichier CH₄ moyen introuvable.")

with col2:
st.subheader(f"Anomalie CH₄ {year_choice}")
an_path = anomaly_files.get(year_choice)
if an_path and os.path.exists(an_path):
try:
with rasterio.open(an_path) as src:
arr2 = src.read(1)
arr2 = np.array(arr2, dtype=float)
arr2[arr2 == 0] = np.nan
fig2, ax2 = plt.subplots(figsize=(6, 5))
im2 = ax2.imshow(arr2, cmap="coolwarm")
ax2.set_title(f"Anomalie CH₄ {year_choice}")
ax2.axis("off")
plt.colorbar(im2, ax=ax2, shrink=0.8)
st.pyplot(fig2)
plt.close(fig2)
except Exception as e:
st.error(f"Erreur affichage anomalie CH4: {e}")
else:
st.warning("Fichier anomalie CH₄ introuvable.")

# ===================== SECTION D: Analyse HSE annuelle =====================
st.markdown("##  Analyse HSE annuelle")
if st.button("Afficher l'analyse HSE pour l'année sélectionnée"):
df_annual_local = pd.DataFrame()
for csv_file in [csv_annual_2025, csv_annual]:
if os.path.exists(csv_file):
try:
df_annual_local = pd.read_csv(csv_file)
break
except Exception as e:
st.error(f"Erreur lecture {csv_file}: {e}")

if not df_annual_local.empty:
year_col = None
ch4_col = None
for c in df_annual_local.columns:
if "year" in c.lower():
year_col = c
if "ch4" in c.lower() and "mean" in c.lower():
ch4_col = c
if year_col and ch4_col and year_choice in df_annual_local[year_col].values:
mean_ch4_year = float(
df_annual_local[df_annual_local[year_col] == year_choice][ch4_col].values[0]
)
if mean_ch4_year < 1800:
risk = "Faible"
action = "Surveillance continue."
elif mean_ch4_year < 1850:
risk = "Modéré"
action = "Vérifier les torches et informer l'équipe HSE."
elif mean_ch4_year < 1900:
risk = "Élevé"
action = "Inspection urgente du site et mesures de sécurité immédiates."
else:
risk = "Critique"
action = "Alerter la direction, sécuriser la zone, stopper les opérations si nécessaire."

st.success(f"Année : {year_choice}")
st.write(f"**Moyenne CH₄ :** {mean_ch4_year:.2f} ppb")
st.write(f"**Niveau de risque HSE :** {risk}")
st.write(f"**Actions recommandées :** {action}")

df_hazop_local = hazop_analysis(mean_ch4_year)
st.markdown("### Tableau HAZOP")
st.table(df_hazop_local)
else:
st.warning("Pas de données CH₄ pour cette année.")
else:
st.warning("CSV annuel introuvable.")

# ===================== SECTION E: Analyse CH4 du jour =====================
st.markdown("##  Analyse CH₄ du jour")
if st.button("Analyser aujourd'hui"):
ch4_today = 0.0

# priorité au daily 2025
if os.path.exists(csv_daily_2025):
try:
df_daily = pd.read_csv(csv_daily_2025)
if not df_daily.empty:
cols = [c for c in df_daily.columns if any(k in c.lower() for k in ["ch4", "value", "ppb"])]
if cols:
ch4_today = float(df_daily[cols[0]].iloc[-1])
except Exception as e:
st.error(f"Erreur lecture CH4_daily_2025.csv: {e}")

# fallback anomalies
if ch4_today == 0.0 and os.path.exists(csv_daily_anom):
try:
df_daily2 = pd.read_csv(csv_daily_anom)
if not df_daily2.empty:
cols = [c for c in df_daily2.columns if any(k in c.lower() for k in ["ch4", "value", "ppb"])]
if cols:
ch4_today = float(df_daily2[cols[0]].iloc[-1])
except Exception as e:
st.error(f"Erreur lecture Anomalies_CH4_HassiRmel.csv: {e}")

if ch4_today == 0.0:
ch4_today = 1935.0 # valeur simulée

threshold = 1900.0
date_now = datetime.now().strftime("%d/%m/%Y %H:%M")

if ch4_today > threshold:
action_hse = "Alerter, sécuriser la zone et stopper opérations"
elif ch4_today > threshold - 50:
action_hse = "Surveillance renforcée et vérification des torches"
else:
action_hse = "Surveillance continue"

st.session_state["analysis_today"] = {
"date": date_now,
"ch4": ch4_today,
"anomaly": ch4_today > threshold,
"action": action_hse,
"threshold": threshold,
}

st.write(f"**CH₄ du jour :** {ch4_today:.1f} ppb ({date_now})")
if ch4_today > threshold:
st.error(" Anomalie détectée : niveau CH₄ critique !")
elif ch4_today > threshold - 50:
st.warning(" CH₄ élevé, surveillance recommandée.")
else:
st.success("CH₄ normal, aucune anomalie détectée.")

anomalies_today_df = pd.DataFrame(
[
{
"Date": date_now.split()[0],
"Heure": date_now.split()[1],
"Site": site_name,
"Latitude": latitude,
"Longitude": longitude,
"CH4 (ppb)": ch4_today,
"Anomalie": "Oui" if ch4_today > threshold else "Non",
"Action HSE": action_hse,
}
]
)
st.table(anomalies_today_df)

# ===================== SECTION F: PDF du jour =====================
st.markdown("##  Générer rapport PDF du jour")
if st.button("Générer rapport PDF du jour"):
analysis = st.session_state.get("analysis_today")
if analysis is None:
st.warning("Aucune analyse du jour. Cliquer d'abord sur 'Analyser aujourd'hui'.")
else:
report_date = analysis["date"].split()[0]
pdf_bytes = generate_pdf_bytes_professional(
site_name=site_name,
latitude=latitude,
longitude=longitude,
report_date=report_date,
ch4_value=analysis["ch4"],
anomaly_flag=analysis["anomaly"],
action_hse=analysis["action"],
hazop_df=hazop_analysis(analysis["ch4"]),
)
st.download_button(
label="⬇ Télécharger le rapport PDF du jour",
data=pdf_bytes,
file_name=f"Rapport_HSE_CH4_{site_name}_{report_date}.pdf",
mime="application/pdf",
)

# ===================== DASHBOARD HISTORIQUE =====================
st.markdown("##  Dashboard Historique CH₄ (2020-2025)")

df_hist = pd.DataFrame()
if os.path.exists(csv_global):
try:
df_hist = pd.read_csv(csv_global)
except Exception as e:
st.error(f"Erreur lecture {csv_global}: {e}")

if df_hist.empty and os.path.exists(csv_monthly):
try:
df_hist = pd.read_csv(csv_monthly)
except Exception:
df_hist = pd.DataFrame()


def find_date_col(df: pd.DataFrame) -> str | None:
if df is None or df.empty:
return None
for c in df.columns:
if "date" in c.lower() or "time" in c.lower():
return c
try:
pd.to_datetime(df.iloc[:, 0])
return df.columns[0]
except Exception:
return None


if not df_hist.empty:
date_col = find_date_col(df_hist)
if date_col:
df_hist["__date"] = pd.to_datetime(df_hist[date_col], errors="coerce")
else:
df_hist["__date"] = pd.NaT

st.markdown("###  Filtres historiques")
colf1, colf2, colf3 = st.columns(3)

with colf1:
if not df_hist.empty and df_hist["__date"].notna().any():
min_date = df_hist["__date"].min().date()
max_date = df_hist["__date"].max().date()
else:
min_date = datetime(2020, 1, 1).date()
max_date = datetime.now().date()
date_range = st.date_input("Période", [min_date, max_date])

with colf2:
anomaly_filter = st.selectbox(
"Filtrer par anomalie", ["Tous", "Anomalies seulement", "Normales seulement"]
)

with colf3:
year_filter = st.selectbox("Filtrer par année", ["Toutes"] + [str(y) for y in range(2020, 2026)])

filtered = df_hist.copy() if not df_hist.empty else pd.DataFrame()
if not filtered.empty and "__date" in filtered.columns:
start_d = pd.to_datetime(date_range[0])
end_d = pd.to_datetime(date_range[1]) + pd.Timedelta(days=1)
filtered = filtered[(filtered["__date"] >= start_d) & (filtered["__date"] <= end_d)]

anomaly_col = None
for c in filtered.columns:
if any(k in c.lower() for k in ["anomal", "alert", "flag"]):
anomaly_col = c
break

if anomaly_filter != "Tous" and anomaly_col is not None:
if anomaly_filter == "Anomalies seulement":
filtered = filtered[filtered[anomaly_col].astype(bool)]
elif anomaly_filter == "Normales seulement":
filtered = filtered[~filtered[anomaly_col].astype(bool)]

if year_filter != "Toutes":
filtered = filtered[filtered["__date"].dt.year == int(year_filter)]

st.markdown("###  Historique filtré")
if filtered.empty:
st.info("Aucune donnée historique trouvée pour les critères sélectionnés.")
else:
to_show = filtered.copy()
if "__date" in to_show.columns:
to_show["Date"] = to_show["__date"].dt.strftime("%Y-%m-%d %H:%M:%S")
to_show = to_show.drop(columns=["__date"])
st.dataframe(to_show, use_container_width=True)

csv_bytes = to_show.to_csv(index=False).encode("utf-8")
st.download_button(
"⬇ Exporter historique filtré (CSV)",
data=csv_bytes,
file_name=f"Historique_CH4_{date_range[0]}_to_{date_range[1]}.csv",
mime="text/csv",
)

# ===================== RAPPORT PDF PÉRIODE =====================
st.markdown("##  Générer un rapport PDF pour une période")
colp1, colp2 = st.columns([2, 1])
with colp1:
pdf_date_range = st.date_input("Période pour le rapport", [min_date, max_date])
with colp2:
if st.button("Générer rapport période (PDF)"):
if filtered.empty:
st.warning("Aucune donnée pour la période sélectionnée.")
else:
val_col = None
for c in filtered.columns:
cl = c.lower()
if "ch4" in cl and any(k in cl for k in ["mean", "value", "ppb"]):
val_col = c
break
if val_col is None:
numeric_cols = filtered.select_dtypes(include=[np.number]).columns.tolist()
val_col = numeric_cols[0] if numeric_cols else None

if val_col and not filtered[val_col].isna().all():
mean_period = float(filtered[val_col].mean())
anomaly_flag_period = mean_period >= 1900
action_period = (
"Alerter, sécuriser la zone et stopper opérations"
if anomaly_flag_period
else "Surveillance continue"
)
hazop_df_period = hazop_analysis(mean_period)
report_date_str = f"{pdf_date_range[0]}_to_{pdf_date_range[1]}"
pdf_bytes_period = generate_pdf_bytes_professional(
site_name=site_name,
latitude=latitude,
longitude=longitude,
report_date=report_date_str,
ch4_value=mean_period,
anomaly_flag=anomaly_flag_period,
action_hse=action_period,
hazop_df=hazop_df_period,
)
st.download_button(
label="⬇ Télécharger le rapport PDF (période sélectionnée)",
data=pdf_bytes_period,
file_name=f"Rapport_HSE_CH4_{site_name}_{report_date_str}.pdf",
mime="application/pdf",
)
else:
st.error("Impossible de calculer la moyenne CH4 pour cette période.")
