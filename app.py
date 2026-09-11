"""
Valanalys 2026 — en Streamlit-app för att följa opinionsläget och (när det
finns tillgängligt) det officiella resultatet inför riksdagsvalet den
13 september 2026.

VIKTIGT innan du publicerar/kör den här på valnatten:
  1. Fältet "Valmyndighetens API-URL" i sidopanelen är ett gissat/exempel-URL.
     Verifiera den riktiga adressen mot val.se innan kl. 20:00 den 13/9, och
     uppdatera DEFAULT_VALMYNDIGHETEN_URL nedan (eller mata in rätt URL direkt
     i appen — den sparas bara i sessionen, inget behöver kodas om).
  2. Allt i "Valnatt"-fliken som INTE uttryckligen kommer från ett lyckat
     API-svar är tydligt märkt som exempel/väntar-läge. Lägg aldrig till
     påhittade siffror eller rubriker attribuerade till riktiga redaktioner
     (SVT, SR, TT, Valmyndigheten m.fl.) — det är grogrund för missinformation
     om det råkar delas eller skärmdumpas.
"""

import io
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

try:
    from streamlit_sortables import sort_items
    SORTABLES_AVAILABLE = True
except ImportError:
    SORTABLES_AVAILABLE = False

st.set_page_config(page_title="Valanalys 2026", page_icon="🗳️", layout="wide")

# --------------------------------------------------------------------------
# Konstanter
# --------------------------------------------------------------------------

# Svensk tid, UTC+2 under sommartid (gäller fortfarande i mitten av september)
SWEDEN_TZ = timezone(timedelta(hours=2))
POLLS_CLOSE = datetime(2026, 9, 13, 20, 0, tzinfo=SWEDEN_TZ)

# OBS: inte verifierad mot Valmyndighetens faktiska produktions-URL för 2026.
# Kontrollera och uppdatera innan valnatten (se modulens docstring).
DEFAULT_VALMYNDIGHETEN_URL = (
    "https://data.val.se/val/val2026/riksdagsval/00/00/00/preliminart.json"
)

PARTY_COLORS = {
    "S": "#E8112d", "M": "#52BDEC", "SD": "#DDDD00", "C": "#009933",
    "V": "#DA291C", "KD": "#000077", "L": "#006AB3", "MP": "#83CF39",
    "Annat": "#999999",
}
FALLBACK_COLOR = "#777777"

# Opinionssiffrorna nedan (Novus) är manuellt inklistrade i koden, inte
# hämtade automatiskt från någon webbtjänst. De uppdateras bara när någon
# redigerar `load_novus_data()` nedan och lägger in en ny mätning.
#
# NOVUS_LAST_UPDATED_DATE ska matcha datumet för den senaste kolumnen i
# tabellen — kom ihåg att uppdatera BARA detta datum varje gång du lägger
# till en ny mätning, så uppdateras både visningstexten och länken till
# Novus arkiv (https://novus.se/valjarbarometer-arkiv/D-månad-ÅÅÅÅ/)
# automatiskt.
NOVUS_LAST_UPDATED_DATE = datetime(2026, 9, 11).date()

_SWEDISH_MONTHS = {
    1: "januari", 2: "februari", 3: "mars", 4: "april", 5: "maj", 6: "juni",
    7: "juli", 8: "augusti", 9: "september", 10: "oktober", 11: "november", 12: "december",
}


def _novus_archive_url(d) -> str:
    return f"https://novus.se/valjarbarometer-arkiv/{d.day}-{_SWEDISH_MONTHS[d.month]}-{d.year}/"


NOVUS_LAST_UPDATED = f"{NOVUS_LAST_UPDATED_DATE.day} {_SWEDISH_MONTHS[NOVUS_LAST_UPDATED_DATE.month]} {NOVUS_LAST_UPDATED_DATE.year}"
NOVUS_SOURCE_URL = _novus_archive_url(NOVUS_LAST_UPDATED_DATE)

PARTY_FULL_NAMES = {
    "M": "Moderaterna", "L": "Liberalerna", "C": "Centerpartiet", "KD": "Kristdemokraterna",
    "S": "Socialdemokraterna", "V": "Vänsterpartiet", "MP": "Miljöpartiet", "SD": "Sverigedemokraterna",
}

# Några färdiga exempel att snabbstarta ifrån i fliken "Egna block". Fritt att
# lägga till fler — nyckeln blir texten i väljaren.
BLOCK_PRESETS = {
    "Tidö vs Rödgröna (dagens blockindelning)": {
        "a_name": "Tidöpartierna", "a_parties": ["M", "KD", "L", "SD"],
        "b_name": "Rödgröna", "b_parties": ["S", "V", "MP"],
    },
    "Alliansen vs Övriga": {
        "a_name": "Alliansen", "a_parties": ["M", "C", "L", "KD"],
        "b_name": "Övriga", "b_parties": ["S", "V", "MP", "SD"],
    },
    "Storkoalition (M+S) vs Resten": {
        "a_name": "Storkoalition (M+S)", "a_parties": ["M", "S"],
        "b_name": "Resten", "b_parties": ["C", "L", "KD", "V", "MP", "SD"],
    },
    "Mittenblock vs Flyglarna": {
        "a_name": "Mittenblock (C+L+KD+MP)", "a_parties": ["C", "L", "KD", "MP"],
        "b_name": "Flyglarna (S+SD)", "b_parties": ["S", "SD"],
    },
    "Alla utom SD vs SD": {
        "a_name": "Alla utom SD", "a_parties": ["M", "L", "C", "KD", "S", "V", "MP"],
        "b_name": "SD", "b_parties": ["SD"],
    },
}

CUSTOM_SORTABLE_CSS = """
.sortable-component { border: none; }
.sortable-container {
    border-radius: 14px;
    padding: 4px;
    margin: 0 8px 8px 0;
    min-height: 180px;
}
.sortable-container-header {
    font-weight: 700;
    font-size: 17px;
    padding: 10px 14px;
    border-radius: 10px 10px 0 0;
}
.sortable-container-body { padding: 10px; }
.sortable-item {
    font-size: 16px;
    font-weight: 600;
    padding: 12px 16px;
    margin: 6px 0;
    border-radius: 10px;
    cursor: grab;
}
.sortable-container:nth-of-type(1) .sortable-container-header { background-color: #cfe2ff; }
.sortable-container:nth-of-type(1) .sortable-item { background-color: #e7f1ff; border: 2px solid #6ea8fe; }
.sortable-container:nth-of-type(2) .sortable-container-header { background-color: #ffe0c2; }
.sortable-container:nth-of-type(2) .sortable-item { background-color: #fff1e6; border: 2px solid #fd7e14; }
.sortable-container:nth-of-type(3) .sortable-container-header { background-color: #e9ecef; }
.sortable-container:nth-of-type(3) .sortable-item { background-color: #f8f9fa; border: 2px dashed #adb5bd; color: #495057; }
"""


def party_color(p: str) -> str:
    return PARTY_COLORS.get(p, FALLBACK_COLOR)


def chip_label(code: str) -> str:
    return f"{code} — {PARTY_FULL_NAMES.get(code, code)}"


def code_from_chip(label: str) -> str:
    return label.split(" — ")[0]


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------

st.markdown(
    """
    <style>
    @keyframes pulse-glow {
        0% { opacity: 0.6; } 50% { opacity: 1; } 100% { opacity: 0.6; }
    }
    .live-badge {
        background-color: #ff4b4b; color: white; padding: 4px 10px;
        border-radius: 12px; font-weight: bold; font-size: 12px;
        animation: pulse-glow 2s infinite; display: inline-block; margin-bottom: 10px;
    }
    .demo-badge {
        background-color: #6c757d; color: white; padding: 4px 10px;
        border-radius: 12px; font-weight: bold; font-size: 12px;
        display: inline-block; margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# 1. Historisk Novus-data (opinionsmätningar)
# --------------------------------------------------------------------------

@st.cache_data(ttl=86400)
def load_novus_data():
    data = """Parti\tValet 22\tnov 25\tdec 25\tjan 26\tfeb 26\tapril 26\tmaj 26\tjuni 26\tjuli 26\taug 26\t2 sep 26\t7 sep 26\t9 sep 26\t11 sep 26
M\t19,1\t19,4\t17,6\t17,5\t17,5\t18,4\t18,2\t16,6\t17,3\t18,3\t17,2\t17,9\t16,6\t18,1
L\t4,6\t2,2\t2,4\t2,4\t2,1\t2,9\t2,4\t2,2\t1,8\t1,9\t3,3\t4,3\t5,8\t4,7
C\t6,7\t5,1\t4,9\t4,8\t5,2\t6,6\t6,0\t6,1\t6,6\t7,1\t8,3\t7,7\t7,8\t9,2
KD\t5,3\t3,7\t3,9\t4,3\t3,8\t4,8\t5,6\t5,6\t6,1\t6,3\t6,5\t6,0\t6,4\t5,5
S\t30,3\t34,3\t34,1\t34,2\t34,6\t32,4\t30,9\t32,6\t31,8\t30,1\t25,8\t27,0\t26,6\t28,6
V\t6,8\t6,3\t6,2\t6,9\t7,4\t7,6\t8,8\t8,9\t7,8\t7,4\t8,4\t7,8\t7,5\t6,6
MP\t5,1\t5,4\t5,1\t5,5\t5,1\t6,1\t7,1\t6,4\t7,2\t7,9\t7,8\t7,8\t8,8\t6,4
SD\t20,5\t21,0\t23,7\t22,5\t22,9\t19,8\t19,2\t20,0\t20,4\t19,1\t20,7\t19,7\t19,3\t19,5
Annat\t1,5\t2,6\t2,1\t1,9\t1,4\t1,4\t1,8\t1,6\t1,0\t1,9\t2,0\t1,8\t1,2\t1,4"""
    df = pd.read_csv(io.StringIO(data), sep="\t")
    timeline_cols = df.columns[1:]
    for col in timeline_cols:
        df[col] = df[col].astype(str).str.replace(",", ".").astype(float)
    df.set_index("Parti", inplace=True)
    return df, timeline_cols


df_novus, timeline_cols = load_novus_data()

# --------------------------------------------------------------------------
# 2. Live-hämtning från Valmyndigheten
#
# Cachas medvetet INTE med @st.cache_data, eftersom det skulle cacha även
# felsvar (t.ex. 404 innan valnatten) i onödigt lång tid. Vi styr istället
# själva hur ofta ett nytt anrop får göras via session_state, så att en
# knapptryckning alltid ger ett färskt försök men vi ändå inte spammar
# servern om något (t.ex. auto-refresh) anropar funktionen ofta.
# --------------------------------------------------------------------------

MIN_SECONDS_BETWEEN_FETCH = 10


def fetch_valmyndigheten_data(url: str, force: bool = False):
    now = time.time()
    last_ts = st.session_state.get("live_fetch_ts", 0)
    if not force and (now - last_ts) < MIN_SECONDS_BETWEEN_FETCH and "live_fetch_result" in st.session_state:
        return st.session_state["live_fetch_result"]

    try:
        response = requests.get(url, timeout=6)
    except requests.exceptions.RequestException as e:
        result = (None, f"Nätverksfel: {e}")
        st.session_state["live_fetch_ts"] = now
        st.session_state["live_fetch_result"] = result
        return result

    if response.status_code == 200:
        try:
            data = response.json()
            parties_data = []
            for party in data.get("partier", []):
                parties_data.append(
                    {
                        "Parti": party.get("förkortning", party.get("kod", "Okänt")),
                        "Röster": party.get("antalRöster", party.get("rostAntal", 0)),
                        "Procent": party.get("andelRöster", party.get("rostAndel", 0.0)),
                    }
                )
            df = pd.DataFrame(parties_data)
            if df.empty:
                result = (None, "200 OK, men svaret innehöll ingen partidata (kontrollera fältnamnen i JSON-strukturen).")
            else:
                result = (df, "200 OK")
        except ValueError:
            result = (None, "200 OK, men svaret gick inte att tolka som JSON.")
    else:
        result = (None, f"HTTP {response.status_code}")

    st.session_state["live_fetch_ts"] = now
    st.session_state["live_fetch_result"] = result
    return result


# --------------------------------------------------------------------------
# 3. Jämkade uddatalsmetoden (modifierad Sainte-Laguë)
#
# Detta är metoden som faktiskt används för att fördela riksdagsmandat.
# OBS: i verkligheten fördelas 310 av 349 mandat per valkrets och 39 som
# nationella utjämningsmandat (för partier som klarat 4%-spärren
# nationellt, eller 12% i en enskild valkrets). Utan valkretsdata gör den
# här funktionen en förenklad nationell fördelning av samtliga 349 mandat,
# vilket ger ett resultat som ligger nära men inte alltid exakt matchar
# det riktiga utfallet.
# --------------------------------------------------------------------------

def sainte_lague_modified(weights: pd.Series, seats: int) -> pd.Series:
    if weights.sum() == 0 or seats <= 0:
        return pd.Series(0, index=weights.index)

    divisors = {p: 1.4 for p in weights.index}
    allocated = {p: 0 for p in weights.index}

    for _ in range(seats):
        quotients = {p: weights[p] / divisors[p] for p in weights.index}
        winner = max(quotients, key=quotients.get)
        allocated[winner] += 1
        divisors[winner] = 2 * allocated[winner] + 1

    return pd.Series(allocated)


# --------------------------------------------------------------------------
# 4. Fliksystem
# --------------------------------------------------------------------------

tab0, tab1, tab2, tab3, tab_custom, tab4 = st.tabs(
    ["🗳️ Valnatt", "📈 Tidslinje (Novus)", "⚖️ Mandatkollen", "📊 Blocken", "🧩 Egna block", "🔴 Valmyndigheten API"]
)

# === FLIK 0: VALNATT ======================================================
with tab0:
    now_sweden = datetime.now(SWEDEN_TZ)
    time_left = POLLS_CLOSE - now_sweden

    st.title("Valnatt 2026")

    if time_left.total_seconds() > 0:
        days = time_left.days
        hours, rem = divmod(time_left.seconds, 3600)
        minutes = rem // 60
        st.markdown(f"### ⏳ {days} dagar, {hours} timmar och {minutes} minuter kvar till vallokalerna stänger (20:00 den 13 september 2026)")
    else:
        st.markdown("### 🗳️ Vallokalerna har stängt — rösträkningen pågår eller är klar.")

    st.markdown("---")

    # --- Opinionsläget just nu (alltid synligt, oberoende av live-API:et) ---
    st.subheader("📊 Opinionsläget just nu")
    latest_col = timeline_cols[-1]
    prev_col = timeline_cols[-2] if len(timeline_cols) > 1 else None
    st.caption(
        f"Senaste Novus-mätningen ({latest_col}). Det här är en opinionsmätning, "
        "inte ett valresultat."
    )
    st.caption(
        f"📌 Källa: [Novus väljarbarometer]({NOVUS_SOURCE_URL}). Siffrorna är "
        f"manuellt inlagda i appens kod (senast uppdaterade {NOVUS_LAST_UPDATED}) — "
        "appen hämtar INGET automatiskt från Novus. För att få in en ny mätning "
        "måste någon redigera `load_novus_data()` i `app.py` och lägga till en kolumn."
    )

    latest = df_novus[latest_col].sort_values(ascending=False)
    leader = latest.index[0]
    tido_now = df_novus.loc[["M", "KD", "L", "SD"], latest_col].sum()
    rodgrona_now = df_novus.loc[["S", "V", "MP"], latest_col].sum()

    m1, m2, m3 = st.columns(3)
    m1.metric("Störst just nu", f"{leader} ({latest[leader]:.1f} %)")

    if prev_col is not None:
        tido_prev = df_novus.loc[["M", "KD", "L", "SD"], prev_col].sum()
        rodgrona_prev = df_novus.loc[["S", "V", "MP"], prev_col].sum()
        m2.metric("Tidöpartierna (M+KD+L+SD)", f"{tido_now:.1f} %", f"{tido_now - tido_prev:+.1f} pe")
        m3.metric("Rödgröna (S+V+MP)", f"{rodgrona_now:.1f} %", f"{rodgrona_now - rodgrona_prev:+.1f} pe")
    else:
        m2.metric("Tidöpartierna (M+KD+L+SD)", f"{tido_now:.1f} %")
        m3.metric("Rödgröna (S+V+MP)", f"{rodgrona_now:.1f} %")

    fig_poll = px.bar(
        latest.reset_index(), x=latest_col, y="Parti", orientation="h",
        color="Parti", color_discrete_map=PARTY_COLORS, text=latest_col,
    )
    fig_poll.update_layout(
        showlegend=False, height=380, margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="Procent (opinionsmätning, ej valresultat)",
    )
    st.plotly_chart(fig_poll, width='stretch')

    if prev_col is not None:
        delta = (df_novus[latest_col] - df_novus[prev_col]).sort_values(ascending=False)
        with st.expander(f"Förändring sedan förra mätningen ({prev_col})"):
            for p, d in delta.items():
                arrow = "🔺" if d > 0.05 else ("🔻" if d < -0.05 else "➖")
                st.write(f"{arrow} **{p}**: {d:+.1f} procentenheter")

    st.markdown("---")

    st.subheader("Officiellt preliminärt resultat")
    st.caption(
        "Den här panelen försöker hämta data direkt från Valmyndigheten. "
        "Fram till dess att räkningen börjar kvällen den 13 september kommer "
        "anropet normalt att misslyckas eller ge tomt resultat — det är väntat, "
        "inte ett fel i appen."
    )
    st.caption(
        "📌 Hämtas **inte** automatiskt i bakgrunden. Ett nytt anrop görs bara när "
        "sidan laddas om eller du trycker på knappen nedan, och är då spärrad till "
        f"max ett nytt anrop var {MIN_SECONDS_BETWEEN_FETCH}:e sekund för att inte "
        "belasta Valmyndighetens server i onödan."
    )

    with st.expander("⚙️ API-inställningar"):
        api_url = st.text_input(
            "Valmyndighetens API-URL",
            value=st.session_state.get("api_url_override", DEFAULT_VALMYNDIGHETEN_URL),
            help="Kontrollera och uppdatera denna mot val.se:s faktiska adress innan valnatten.",
        )
        st.session_state["api_url_override"] = api_url

    col_fetch, col_status = st.columns([1, 3])
    with col_fetch:
        force_refresh = st.button("🔄 Hämta senaste resultatet", width='stretch')

    df_live, status = fetch_valmyndigheten_data(api_url, force=force_refresh)

    with col_status:
        st.caption(f"Senaste anropsstatus: `{status}`")

    if df_live is not None and not df_live.empty:
        st.success("✅ Live-data hämtad från Valmyndigheten.")
        df_show = df_live.copy()
        if "Parti" in df_show.columns:
            df_show = df_show.sort_values("Procent", ascending=False)
        fig_live = px.bar(
            df_show, x="Procent", y="Parti", orientation="h",
            color="Parti", color_discrete_map=PARTY_COLORS,
            text="Procent", title="Officiell röstfördelning just nu (%)",
        )
        fig_live.update_layout(showlegend=False, height=420, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_live, width='stretch')
        st.dataframe(
            df_show.style.format({"Procent": "{:.1f} %", "Röster": "{:,}"}),
            width='stretch',
        )
    else:
        st.markdown('<span class="demo-badge">VÄNTAR PÅ DATA</span>', unsafe_allow_html=True)
        st.info(
            "Inget officiellt resultat tillgängligt ännu. Så fort Valmyndigheten "
            "publicerar preliminära siffror och API-URL:en ovan stämmer visas de här "
            "automatiskt. Se opinionsläget högre upp på sidan under tiden."
        )

    st.markdown("---")
    st.subheader("Följ den officiella bevakningen")
    st.caption("Länkar till redaktioner och myndigheter som faktiskt sänder/rapporterar under valnatten.")
    l1, l2, l3 = st.columns(3)
    l1.link_button("SVT — Guide till valet 2026", "https://www.svt.se/nyheter/inrikes/guide-val-2026-i-sverige", width='stretch')
    l2.link_button("Valmyndigheten", "https://www.val.se", width='stretch')
    l3.link_button("Riksdagen — Valet 2026", "https://www.riksdagen.se/sv/aktuellt/valet-2026/", width='stretch')

# === FLIK 1: TIDSLINJE =====================================================
with tab1:
    st.caption(
        f"📌 Källa: [Novus väljarbarometer]({NOVUS_SOURCE_URL}), manuellt "
        f"inlagd i koden — senast uppdaterad {NOVUS_LAST_UPDATED}. Ingen "
        "automatisk hämtning."
    )
    with st.expander("⚙️ Filtrera grafen", expanded=False):
        selected_parties = st.multiselect(
            "Välj partier", list(df_novus.index),
            default=["S", "M", "SD", "C", "V", "KD", "L", "MP"],
        )
        show_trend = st.checkbox("Visa glidande medelvärde")

    if selected_parties:
        df_plot = df_novus.loc[selected_parties].T
        fig = go.Figure()
        for party in selected_parties:
            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot[party], mode="lines+markers", name=party,
                line=dict(color=party_color(party), width=3),
            ))
            if show_trend:
                fig.add_trace(go.Scatter(
                    x=df_plot.index, y=df_plot[party].rolling(2, min_periods=1).mean(),
                    mode="lines", name=f"{party} (Trend)",
                    line=dict(color=party_color(party), width=2, dash="dot"),
                ))
        fig.update_layout(
            hovermode="x unified", legend=dict(orientation="h", y=-0.2, yanchor="top"),
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("Välj minst ett parti i filtret ovan för att visa grafen.")

# === FLIK 2: MANDATKOLLEN ==================================================
with tab2:
    st.markdown(
        "**Testa regeringsunderlaget:** Dra i reglagen för att se hur ett "
        "riksdagsval skulle sluta (349 mandat)."
    )
    st.caption(
        "Fördelningen använder jämkade uddatalsmetoden (samma metod som "
        "riktiga riksdagsval), men förenklad till nationell nivå — se kod-"
        "kommentarer för detaljer. Verkligt utfall kan avvika något eftersom "
        "310 mandat fördelas per valkrets och 39 som utjämningsmandat."
    )

    latest_poll = df_novus[timeline_cols[-1]].drop("Annat").copy()

    with st.expander("Justera valresultat (%)"):
        for p in latest_poll.index:
            latest_poll[p] = st.slider(p, 0.0, 40.0, float(latest_poll[p]), 0.1, key=f"slider_{p}")

    valid_parties = latest_poll[latest_poll >= 4.0]

    if valid_parties.empty:
        st.warning("Inget parti klarar 4%-spärren med nuvarande inställningar.")
    else:
        mandates = sainte_lague_modified(valid_parties, 349)

        col1, col2 = st.columns(2)
        reg_mandates = mandates.loc[mandates.index.intersection(["M", "KD", "L", "SD"])].sum()
        opp_mandates = mandates.loc[mandates.index.intersection(["S", "V", "C", "MP"])].sum()
        col1.metric("Tidöpartierna", f"{reg_mandates} mandat")
        col2.metric("Oppositionen", f"{opp_mandates} mandat")

        if reg_mandates > opp_mandates:
            st.success("Tidöpartierna har majoritet i riksdagen.")
        elif opp_mandates > reg_mandates:
            st.error("Oppositionen har majoritet i riksdagen.")
        else:
            st.warning("Blocken har lika många mandat — ingen majoritet.")

        fig_mandates = px.bar(
            mandates.sort_values(ascending=False).reset_index().rename(columns={"index": "Parti", 0: "Mandat"}),
            x="Parti", y="Mandat", color="Parti", color_discrete_map=PARTY_COLORS, text="Mandat",
        )
        fig_mandates.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_mandates, width='stretch')

# === FLIK 3: BLOCKEN ========================================================
with tab3:
    st.markdown("**Stöd för politiska block (Exklusive C, som inte hör till något fast block).**")
    block_data = pd.DataFrame(index=timeline_cols)
    block_data["Tidö (M+KD+L+SD)"] = df_novus.loc[["M", "KD", "L", "SD"]].sum()
    block_data["Rödgröna (S+V+MP)"] = df_novus.loc[["S", "V", "MP"]].sum()

    fig_block = px.line(
        block_data.reset_index(), x="index", y=["Tidö (M+KD+L+SD)", "Rödgröna (S+V+MP)"],
        color_discrete_sequence=["#1f77b4", "#d62728"],
    )
    fig_block.update_layout(
        hovermode="x unified", legend=dict(orientation="h", y=-0.2, yanchor="top"),
        margin=dict(l=0, r=0, t=10, b=0), xaxis_title="", yaxis_title="%",
    )
    st.plotly_chart(fig_block, width='stretch')

# === FLIK: EGNA BLOCK =======================================================
with tab_custom:
    st.markdown(
        "**Bygg egna block.** Standardblocken (Tidö/Rödgröna) i fliken "
        "'Blocken' är låsta till dagens riksdagsuppställning — här kan du "
        "istället testa vilka konstellationer som helst."
    )

    parties_selectable = [p for p in df_novus.index if p != "Annat"]

    # --- Grundtillstånd (första gången fliken visas) --------------------
    if "block_a_name" not in st.session_state:
        st.session_state["block_a_name"] = "Tidöpartierna"
    if "block_b_name" not in st.session_state:
        st.session_state["block_b_name"] = "Rödgröna"
    if "custom_block_state" not in st.session_state:
        assigned0 = {"M", "KD", "L", "SD", "S", "V", "MP"}
        st.session_state["custom_block_state"] = {
            "a": ["M", "KD", "L", "SD"],
            "b": ["S", "V", "MP"],
            "unassigned": [p for p in parties_selectable if p not in assigned0],
        }
    if "applied_preset" not in st.session_state:
        st.session_state["applied_preset"] = "Tidö vs Rödgröna (dagens blockindelning)"

    def _apply_block_preset():
        chosen = st.session_state["preset_selectbox"]
        st.session_state["applied_preset"] = chosen
        if chosen in BLOCK_PRESETS:
            preset = BLOCK_PRESETS[chosen]
            st.session_state["block_a_name"] = preset["a_name"]
            st.session_state["block_b_name"] = preset["b_name"]
            assigned = set(preset["a_parties"]) | set(preset["b_parties"])
            st.session_state["custom_block_state"] = {
                "a": list(preset["a_parties"]),
                "b": list(preset["b_parties"]),
                "unassigned": [p for p in parties_selectable if p not in assigned],
            }

    preset_options = ["🎨 Anpassat (mitt eget val)"] + list(BLOCK_PRESETS.keys())
    st.selectbox(
        "Snabbstart — välj ett färdigt exempel eller bygg helt eget",
        preset_options,
        index=preset_options.index(st.session_state["applied_preset"])
        if st.session_state["applied_preset"] in preset_options else 0,
        key="preset_selectbox",
        on_change=_apply_block_preset,
    )

    col_a, col_b = st.columns(2)
    with col_a:
        block_a_name = st.text_input("Namn på block A", key="block_a_name")
    with col_b:
        block_b_name = st.text_input("Namn på block B", key="block_b_name")

    state = st.session_state["custom_block_state"]

    if SORTABLES_AVAILABLE:
        st.caption("🖱️ Dra partierna mellan rutorna för att bygga dina egna block.")
        container_items = [
            {"header": f"🟦 {block_a_name} ({len(state['a'])})", "items": [chip_label(p) for p in state["a"]]},
            {"header": f"🟧 {block_b_name} ({len(state['b'])})", "items": [chip_label(p) for p in state["b"]]},
            {"header": f"⚪ Inte tilldelat ({len(state['unassigned'])})", "items": [chip_label(p) for p in state["unassigned"]]},
        ]
        sorted_result = sort_items(container_items, multi_containers=True, custom_style=CUSTOM_SORTABLE_CSS)
        new_state = {
            "a": [code_from_chip(x) for x in sorted_result[0]["items"]],
            "b": [code_from_chip(x) for x in sorted_result[1]["items"]],
            "unassigned": [code_from_chip(x) for x in sorted_result[2]["items"]],
        }
        st.session_state["custom_block_state"] = new_state
        block_a_parties = new_state["a"]
        block_b_parties = new_state["b"]
    else:
        st.info(
            "💡 Installera `streamlit-sortables` (finns i requirements.txt) för att "
            "kunna dra-och-släppa partier mellan blocken. Använder vanliga "
            "väljare tills vidare."
        )
        with st.container(border=True):
            block_a_parties = st.multiselect(
                f"Partier i {block_a_name}", parties_selectable, default=state["a"], key="block_a_multiselect",
            )
        with st.container(border=True):
            block_b_parties = st.multiselect(
                f"Partier i {block_b_name}", parties_selectable, default=state["b"], key="block_b_multiselect",
            )
        overlap = set(block_a_parties) & set(block_b_parties)
        if overlap:
            st.warning(
                f"⚠️ {', '.join(sorted(overlap))} ingår i båda blocken — "
                "totalerna nedan räknar då med partiet dubbelt."
            )

    latest_col_cb = timeline_cols[-1]
    a_pct = df_novus.loc[block_a_parties, latest_col_cb].sum() if block_a_parties else 0.0
    b_pct = df_novus.loc[block_b_parties, latest_col_cb].sum() if block_b_parties else 0.0

    st.markdown("---")
    m1, m2 = st.columns(2)
    m1.metric(f"{block_a_name} — opinionsstöd ({latest_col_cb})", f"{a_pct:.1f} %")
    m2.metric(f"{block_b_name} — opinionsstöd ({latest_col_cb})", f"{b_pct:.1f} %")

    if block_a_parties or block_b_parties:
        custom_block_data = pd.DataFrame(index=timeline_cols)
        if block_a_parties:
            custom_block_data[block_a_name] = df_novus.loc[block_a_parties].sum()
        if block_b_parties:
            custom_block_data[block_b_name] = df_novus.loc[block_b_parties].sum()

        fig_custom = px.line(
            custom_block_data.reset_index(), x="index", y=list(custom_block_data.columns),
            color_discrete_sequence=["#6f42c1", "#fd7e14"],
        )
        fig_custom.update_layout(
            hovermode="x unified", legend=dict(orientation="h", y=-0.2, yanchor="top"),
            margin=dict(l=0, r=0, t=10, b=0), xaxis_title="", yaxis_title="%",
        )
        st.plotly_chart(fig_custom, width='stretch')
    else:
        st.info("Lägg minst ett parti i något av blocken ovan för att se en tidslinje.")

    st.markdown("---")
    st.subheader("Uppskattat mandatstöd för blocken")
    st.caption(
        "Baseras på senaste Novus-mätningen och jämkade uddatalsmetoden "
        "(samma förenklade nationella modell som i fliken Mandatkollen)."
    )
    poll_for_mandates = df_novus[latest_col_cb].drop("Annat")
    valid_for_mandates = poll_for_mandates[poll_for_mandates >= 4.0]

    if valid_for_mandates.empty:
        st.warning("Inget parti klarar 4%-spärren med senaste mätningen.")
    else:
        mandates_cb = sainte_lague_modified(valid_for_mandates, 349)
        a_mandates = mandates_cb.loc[mandates_cb.index.intersection(block_a_parties)].sum()
        b_mandates = mandates_cb.loc[mandates_cb.index.intersection(block_b_parties)].sum()
        c1, c2 = st.columns(2)
        c1.metric(f"{block_a_name} — mandat", f"{a_mandates}")
        c2.metric(f"{block_b_name} — mandat", f"{b_mandates}")


with tab4:
    st.subheader("🔴 Valmyndigheten API — teknisk status")
    st.markdown(f"Testar mot: `{st.session_state.get('api_url_override', DEFAULT_VALMYNDIGHETEN_URL)}`")
    st.caption(
        "Samma anrop som i fliken Valnatt, men här utan grafik — bra för att "
        "felsöka URL och JSON-struktur innan valnatten."
    )

    if st.button("🔄 Testa anrop nu"):
        df_test, status_test = fetch_valmyndigheten_data(
            st.session_state.get("api_url_override", DEFAULT_VALMYNDIGHETEN_URL), force=True
        )
        if df_test is not None and not df_test.empty:
            st.success(f"✅ Lyckades — status: {status_test}")
            st.dataframe(
                df_test.style.format({"Procent": "{:.1f} %", "Röster": "{:,}"}),
                width='stretch',
            )
        else:
            st.warning(f"⚠️ Ingen giltig data ännu. Status: **{status_test}**")
            st.info(
                "Helt normalt innan valet dragit igång på riktigt. Kontrollera "
                "URL:en och fältnamnen (`förkortning`/`antalRöster`/`andelRöster` "
                "eller motsvarande) mot Valmyndighetens faktiska JSON-schema."
            )
