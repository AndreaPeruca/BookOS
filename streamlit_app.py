"""
BookStore OS - Toolkit per Librai Indipendenti
Dipendenze: streamlit, pandas, plotly
Esegui con: streamlit run bookstore_os.py
BUILD: 2026-03-17 18:20
"""

import io
import json
import logging
import pathlib
import re
import urllib.request
import numpy as np
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from urllib.parse import quote_plus

# Configurazione logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY = True
except ImportError:
    PLOTLY = False

# ---------------------------------------------------------------------------
# CONFIGURAZIONE
# ---------------------------------------------------------------------------
st.set_page_config(page_title="BookStore OS", page_icon="📚", layout="wide", initial_sidebar_state="expanded")

DATA_SISTEMA          = date.today()
SOGLIA_INVENDUTO      = DATA_SISTEMA - timedelta(days=182)
SOGLIA_FINESTRA_START = DATA_SISTEMA - timedelta(days=182)
SOGLIA_FINESTRA_END   = SOGLIA_FINESTRA_START + timedelta(days=30)
SOGLIA_ROTAZIONE_MIN  = 3

SCHEMA_MAGAZZINO = {"Titolo", "Autore", "ISBN", "Editore", "Data_Fatturazione",
                    "Giacenza", "Vendute_Ultimi_30_Giorni", "Prezzo_Copertina", "Sconto_Libreria"}

USATO_CONTO_VENDITA = 0.40

PAGINE = ["Dashboard", "Analisi resi", "Calcolatore margine ordine", "Gestione usato", "Analisi storica", "Simulatore ordine"]

# Percorso inventario usato — stessa cartella del file .py
INVENTORY_FILE = pathlib.Path(__file__).parent / "inventario_usato.json"
STORICO_FILE   = pathlib.Path(__file__).parent / "storico_decisioni.json"
PREFERENCES_FILE = pathlib.Path(__file__).parent / "preferenze.json"

# ---------------------------------------------------------------------------
# BENCHMARK DI SETTORE — fonte: AIE / ISTAT 2022
# Dati pubblici aggregati sul mercato librario italiano.
# Il sell-through mensile è derivato dalle statistiche ISTAT sull'invenduto
# (26-59% dei titoli con invenduto alto) → soglia critica ~4%/mese.
# ---------------------------------------------------------------------------
BENCHMARK = {
    "sell_through_critico":    4.0,   # %/mese — sotto questa soglia: situazione critica
    "sell_through_attenzione": 8.0,   # %/mese — tra 4 e 8%: attenzione
    "copertura_critica":      12,     # mesi — sopra questa soglia: critico
    "margine_lordo_min":      25.0,   # % margine lordo tipico libreria indipendente
    "margine_lordo_max":      35.0,
    "sconto_medio_min":       30.0,   # % sconto medio editore
    "sconto_medio_max":       40.0,
}

# Palette Economist-inspired — usata nel modulo Analisi storica
ECON_PAL = ["#B5362C", "#2A5FAC", "#00877A", "#D4693A", "#7B4F9E", "#5C5852", "#C8A951"]

# ---------------------------------------------------------------------------
# ALIAS COLONNE — normalizzazione case-insensitive per gestionali italiani
# ---------------------------------------------------------------------------
COL_ALIASES = {
    "data_fatturazione":        "Data_Fatturazione",
    "data fatturazione":        "Data_Fatturazione",
    "datafatturazione":         "Data_Fatturazione",
    "data_acq":                 "Data_Fatturazione",
    "data_acquisto":            "Data_Fatturazione",
    "data_ordine":              "Data_Fatturazione",
    "data_carico":              "Data_Fatturazione",
    "giacenza":                 "Giacenza",
    "giacenze":                 "Giacenza",
    "stock":                    "Giacenza",
    "quantita":                 "Giacenza",
    "quantità":                 "Giacenza",
    "copie":                    "Giacenza",
    "vendute_ultimi_30_giorni": "Vendute_Ultimi_30_Giorni",
    "vendite_30g":              "Vendute_Ultimi_30_Giorni",
    "vendite_mensili":          "Vendute_Ultimi_30_Giorni",
    "venduto_30g":              "Vendute_Ultimi_30_Giorni",
    "vendite":                  "Vendute_Ultimi_30_Giorni",
    "vendite_mese":             "Vendute_Ultimi_30_Giorni",
    "pezzi_venduti":            "Vendute_Ultimi_30_Giorni",
    "prezzo_copertina":         "Prezzo_Copertina",
    "prezzo_di_copertina":      "Prezzo_Copertina",
    "prezzo":                   "Prezzo_Copertina",
    "pvc":                      "Prezzo_Copertina",
    "prezzo_listino":           "Prezzo_Copertina",
    "listino":                  "Prezzo_Copertina",
    "sconto_libreria":          "Sconto_Libreria",
    "sconto":                   "Sconto_Libreria",
    "sconto_lib":               "Sconto_Libreria",
    "sconto_libr":              "Sconto_Libreria",
    "sc_libreria":              "Sconto_Libreria",
    "titolo":                   "Titolo",
    "autore":                   "Autore",
    "autori":                   "Autore",
    "editore":                  "Editore",
    "isbn":                     "ISBN",
    "codice_isbn":              "ISBN",
    "cod_isbn":                 "ISBN",
    "ean":                      "ISBN",
}

# ---------------------------------------------------------------------------
# PERSISTENZA INVENTARIO USATO
# ---------------------------------------------------------------------------
def load_inventory() -> list:
    try:
        if INVENTORY_FILE.exists():
            return json.loads(INVENTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []

def save_inventory(inv: list) -> None:
    try:
        INVENTORY_FILE.write_text(
            json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def load_preferences() -> dict:
    """Carica le preferenze utente salvate (tema, colonne visibili, etc.)"""
    try:
        if PREFERENCES_FILE.exists():
            data = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
            return data
    except Exception:
        pass
    return {}


def save_preferences(prefs: dict) -> None:
    """Salva le preferenze utente in JSON."""
    try:
        PREFERENCES_FILE.write_text(
            json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


@st.cache_data(show_spinner=False)
def load_storico() -> list:
    try:
        if STORICO_FILE.exists():
            return json.loads(STORICO_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def save_decision_log(action_type: str, titoli: list, n_copie: int, valore: float) -> None:
    """Aggiunge una voce al log delle decisioni (storico esportazioni).

    action_type: "resa" | "analisi_invenduto"
    titoli:      lista di titoli inclusi nell'esportazione
    n_copie:     totale copie
    valore:      valore stimato recuperabile/immobilizzato (€)
    """
    try:
        storico = load_storico()
        storico.append({
            "data":        datetime.now().strftime("%Y-%m-%d %H:%M"),
            "tipo":        action_type,
            "n_titoli":    len(titoli),
            "n_copie":     n_copie,
            "valore_euro": round(valore, 2),
            "titoli":      titoli[:50],   # max 50 titoli per non gonfiare il file
        })
        STORICO_FILE.write_text(
            json.dumps(storico, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

# ---------------------------------------------------------------------------
# ISBN LOOKUP — OpenLibrary (gratuito, no API key)
# ---------------------------------------------------------------------------
def _isbn_fetch_api(isbn_clean: str) -> dict:
    """
    Chiamata grezza alle API — NON decorata con cache per evitare
    che i risultati vuoti vengano memorizzati come falsi negativi permanenti.
    Testa sia il codice originale sia la variante 978+ISBN10 per massimizzare
    la copertura delle edizioni italiane su Google Books.
    """
    # Candidati: codice originale + eventuale variante 978-prefissata (ISBN-10→13 approssimato)
    candidates = [isbn_clean]
    if len(isbn_clean) == 10:
        candidates.append("978" + isbn_clean)   # Google Books accetta questa forma

    # 1. OpenLibrary
    for cand in candidates:
        try:
            url = (f"https://openlibrary.org/api/books"
                   f"?bibkeys=ISBN:{cand}&format=json&jscmd=data")
            req = urllib.request.Request(url, headers={"User-Agent": "BookStoreOS/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            key = f"ISBN:{cand}"
            if key in data:
                book   = data[key]
                titolo = book.get("title", "")
                autori = book.get("authors", [])
                autore = autori[0]["name"] if autori else ""
                if titolo:
                    return {"titolo": titolo, "autore": autore}
        except Exception:
            pass

    # 2. Fallback: Google Books (migliore copertura edizioni italiane)
    for cand in candidates:
        try:
            url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{cand}"
            req = urllib.request.Request(url, headers={"User-Agent": "BookStoreOS/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])
            if items:
                info   = items[0].get("volumeInfo", {})
                titolo = info.get("title", "")
                autori = info.get("authors", [])
                autore = autori[0] if autori else ""
                if titolo:
                    return {"titolo": titolo, "autore": autore}
        except Exception:
            pass

    return {}


def isbn_lookup(isbn: str) -> dict:
    """
    Cerca titolo e autore da ISBN via OpenLibrary → Google Books.
    Ritorna {"titolo": ..., "autore": ...} oppure {"error": "messaggio"}.
    - Rimuove qualsiasi carattere non-cifra (spazi, trattini, Unicode invisibili).
    - Usa la session_state come cache manuale: solo i risultati positivi
      vengono memorizzati, evitando falsi negativi permanenti.
    """
    # Rimuove TUTTO ciò che non è cifra: trattini, spazi, caratteri Unicode
    # invisibili (U+200E, U+200F, U+FEFF…) che compaiono nei copia-incolla
    isbn_clean = re.sub(r"\D", "", isbn)
    if len(isbn_clean) not in (10, 13):
        return {"error": "ISBN non valido — deve essere 10 o 13 cifre numeriche."}

    # Cache manuale: solo hit positivi, nessun falso negativo permanente
    cache = st.session_state.setdefault("_isbn_cache", {})
    if isbn_clean in cache:
        return cache[isbn_clean]

    result = _isbn_fetch_api(isbn_clean)
    if result:
        cache[isbn_clean] = result
        return result
    return {"error": "ISBN non trovato (OpenLibrary + Google Books). Verifica il codice o compila i campi manualmente."}

# ---------------------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------------------
if "inventario_usato" not in st.session_state:
    st.session_state["inventario_usato"] = load_inventory()

# Preferenze persistenti (salvate su file)
PERSISTENT_PREFS = {
    "dark_mode",
    "calc_prezzo",
    "calc_sconto",
    "calc_resa_pct",
    "calc_affitto",
    "calc_utenze",
    "calc_personale",
    "calc_altri",
    "calc_inv_target",
}

defaults = {
    "svuota_confirm":   False,
    "pagina":           "Dashboard",
    "df_mag":           None,
    "df_mag_name":      None,
    "storico_up":       [],
    "dark_mode":        False,  # Dark mode toggle
    # Calcolatore — valori persistono tra navigazioni
    "calc_titolo":      "",
    "calc_prezzo":      18.00,
    "calc_sconto":      30,
    "calc_quantita":    5,
    "calc_resa_pct":    20,
    "calc_affitto":     0.0,
    "calc_utenze":      0.0,
    "calc_personale":   0.0,
    "calc_altri":       0.0,
    "calc_inv_target":  30,
    # Gestione usato — form persiste tra navigazioni
    "u_titolo":         "",
    "u_autore":         "",
    "u_prezzo":         0.00,
    "u_isbn_input":     "",
    "_usato_added":     "",
}

# Carica preferenze salvate
saved_prefs = load_preferences()

for k, v in defaults.items():
    if k not in st.session_state:
        # Se la preferenza è salvata, usala; altrimenti usa il default
        if k in saved_prefs:
            st.session_state[k] = saved_prefs[k]
        else:
            st.session_state[k] = v

# ---------------------------------------------------------------------------
# UTILITY
# ---------------------------------------------------------------------------
def fmt_euro(v: float) -> str:
    return "€ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip spazi + rimappa alias case-insensitive → nomi canonici."""
    df = df.copy()
    df.columns = df.columns.str.strip()
    renamed = {}
    for col in df.columns:
        key = col.strip().lower().replace(" ", "_")
        if key in COL_ALIASES:
            renamed[col] = COL_ALIASES[key]
    return df.rename(columns=renamed)

def validate_schema(df, required, label):
    missing = required - set(df.columns)
    if missing:
        st.error(f"**{label}** — colonne mancanti: `{'`, `'.join(sorted(missing))}`.")
        with st.expander("💡 **Come risolvere?**"):
            st.markdown(f"""
            **Colonne richieste:** `{'` · `'.join(sorted(required))}`

            **Colonne trovate nel file:** {', '.join(f'`{c}`' for c in sorted(df.columns)) or '(nessuna)'}

            **Soluzione:** Assicurati che il file CSV contenga tutte le colonne richieste,
            oppure verifica che il file sia quello corretto dal tuo gestionale.
            """)
        return False
    return True

@st.cache_data(show_spinner=False)
def load_csv(raw_bytes: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return pd.read_csv(io.BytesIO(raw_bytes), encoding=enc)
        except Exception:
            continue
    raise ValueError("Impossibile leggere il file: encoding non supportato.")

def get_or_load(key, uploaded_file, schema, label):
    if uploaded_file is None:
        return st.session_state.get(key)
    name_key = f"{key}_name"
    if st.session_state.get(name_key) != uploaded_file.name:
        with st.status(f"📂 Caricamento di **{label}**…", expanded=False) as status:
            try:
                st.write(f"📖 Lettura file: `{uploaded_file.name}`")
                df = load_csv(uploaded_file.read())
                st.write(f"✓ File letto · {len(df)} righe")

                st.write("🔧 Normalizzazione colonne…")
                df = normalize_columns(df)
                st.write(f"✓ Colonne normalizzate")

                st.write("✓ Validazione schema…")
                if not validate_schema(df, schema, label):
                    status.update(label="❌ Schema non valido", state="error")
                    return None

                st.session_state[key] = df
                st.session_state[name_key] = uploaded_file.name
                status.update(label=f"✓ {label} caricato con successo", state="complete")
                show_toast(f"{label}: {len(df):,} righe caricate", "success", 3000)
                st.success(f"✓ {len(df):,} righe caricate")
            except ValueError as e:
                st.error(f"⚠️ Errore di encoding: {e}")
                st.info("💡 Assicurati che il file sia un CSV valido (utf-8, latin-1, o cp1252).")
                status.update(label="❌ Errore di encoding", state="error")
                return None
            except Exception as e:
                st.error(f"⚠️ Errore nel caricamento: {e}")
                st.info("💡 Contatta il supporto se il problema persiste.")
                status.update(label="❌ Errore sconosciuto", state="error")
                return None
    return st.session_state.get(key)

_TONE = {
    "positive": {"bar": "#22C55E", "val": "#166534"},
    "negative": {"bar": "#F43F5E", "val": "#9F1239"},
    "warning":  {"bar": "#F59E0B", "val": "#78350F"},
    "neutral":  {"bar": "#C8BFB0", "val": "#16130F"},
}

def get_theme_colors():
    """Return theme-aware colors based on dark_mode session state."""
    dark_mode = st.session_state.get("dark_mode", False)
    if dark_mode:
        return {
            "text": "#F5F1EC",
            "text_secondary": "#D4CCC4",
            "text_muted": "#9B9590",
            "bg": "#1A1918",
            "bg_card": "#2D2B28",
            "border": "#3A3835",
            "accent": "#E74C3C",
        }
    else:
        return {
            "text": "#16130F",
            "text_secondary": "#5C5852",
            "text_muted": "#9B9590",
            "bg": "#F5F1EC",
            "bg_card": "#FFFFFF",
            "border": "#E7E3DC",
            "accent": "#B5362C",
        }


def show_toast(message: str, toast_type: str = "info", duration: int = 4000) -> None:
    """Mostra una notifica toast in alto a destra dello schermo.

    Args:
        message: Testo della notifica
        toast_type: Tipo di notifica ('success', 'error', 'warning', 'info')
        duration: Durata in millisecondi prima di scomparire (default 4000 = 4 sec)
    """
    valid_types = {"success", "error", "warning", "info"}
    if toast_type not in valid_types:
        toast_type = "info"

    st.markdown(f"""
    <script>
    if (window.showToast) {{
        window.showToast('{message}', '{toast_type}', {duration});
    }}
    </script>
    """, unsafe_allow_html=True)


def create_help_tooltip(title: str, description: str, examples: str = "", recommended: str = "") -> str:
    """Crea un tooltip HTML formattato per i parametri.

    Args:
        title: Titolo del parametro
        description: Descrizione del parametro
        examples: Esempi di valori (opzionale)
        recommended: Valore consigliato (opzionale)

    Returns:
        Stringa HTML completa del tooltip
    """
    content = description
    if recommended:
        content += f"\n\n📌 **Consigliato:** {recommended}"
    if examples:
        content += f"\n\n💡 **Esempi:** {examples}"
    return content


def get_file_stats(df: pd.DataFrame, schema: set) -> dict:
    """Calcola statistiche dettagliate del file per lo stato display."""
    try:
        total_rows = len(df)

        # Verifica colonne presenti
        present_cols = set(df.columns)
        missing_cols = schema - present_cols
        col_coverage = (len(present_cols & schema) / len(schema)) * 100 if schema else 100

        # Calcola quality score basato su:
        # - Completamento colonne (30%)
        # - Righe non nulle (40%)
        # - Validità date (20%)
        # - Intervallo dati (10%)

        # Non-null coverage
        non_null_pct = (df.notna().sum().sum() / (len(df) * len(df.columns))) * 100

        # Data range per Data_Fatturazione
        date_range = "N/A"
        if "Data_Fatturazione" in df.columns:
            try:
                dates = pd.to_datetime(df["Data_Fatturazione"], errors='coerce')
                valid_dates = dates.dropna()
                if len(valid_dates) > 0:
                    min_date = valid_dates.min()
                    max_date = valid_dates.max()
                    date_range = f"{min_date.strftime('%d/%m/%y')} → {max_date.strftime('%d/%m/%y')}"
            except:
                pass

        # Quality score (0-100)
        quality = (col_coverage * 0.3) + (non_null_pct * 0.4) + ((len(valid_dates) / max(1, len(df))) * 20 if "Data_Fatturazione" in df.columns else 20)
        quality = min(100, max(0, quality))

        # Quality rating
        if quality >= 95:
            rating = "Eccellente"
            rating_icon = "🟢"
        elif quality >= 85:
            rating = "Buona"
            rating_icon = "🟡"
        elif quality >= 70:
            rating = "Accettabile"
            rating_icon = "🟠"
        else:
            rating = "Problematica"
            rating_icon = "🔴"

        return {
            "total_rows": total_rows,
            "col_coverage": col_coverage,
            "non_null_pct": non_null_pct,
            "quality": quality,
            "rating": rating,
            "rating_icon": rating_icon,
            "date_range": date_range,
            "missing_cols": missing_cols,
        }
    except Exception as e:
        logging.error(f"Errore in get_file_stats(): {e}")
        return {
            "total_rows": len(df),
            "col_coverage": 0,
            "non_null_pct": 0,
            "quality": 0,
            "rating": "Errore",
            "rating_icon": "❌",
            "date_range": "N/A",
            "missing_cols": set(),
        }

def metric_card(label, value, tone="neutral", note=""):
    t = _TONE.get(tone, _TONE["neutral"])
    note_html = f'\n        <div class="mc-note">{note}</div>' if note else ""
    st.markdown(f"""<div class="metric-card" style="border-left-color:{t['bar']}">
        <div class="mc-label">{label}</div>
        <div class="mc-value" style="color:{t['val']}">{value}</div>{note_html}
    </div>""", unsafe_allow_html=True)

def empty_state(icon, title, body):
    st.markdown(f"""<div class="empty-state">
        <div class="es-icon">{icon}</div>
        <div class="es-title">{title}</div>
        <div class="es-body">{body}</div>
    </div>""", unsafe_allow_html=True)

def page_header(title, subtitle):
    st.markdown(f"""<div class="page-hero">
        <div class="page-hero-eyebrow">BookStore OS</div>
        <div class="page-hero-title">{title}</div>
        <div class="page-hero-sub">{subtitle}</div>
    </div>""", unsafe_allow_html=True)

def section(title):
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)

def parse_numeric(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    italian = s.str.contains(r'\.') & s.str.contains(r',')
    cleaned_it  = s.str.replace(r'\.', '', regex=True).str.replace(',', '.', regex=False)
    cleaned_std = s.str.replace(',', '.', regex=False)
    result = cleaned_it.where(italian, cleaned_std)
    return pd.to_numeric(result, errors='coerce').fillna(0)

@st.cache_data(show_spinner=False)
def processa_magazzino(df_raw: pd.DataFrame, soglia_invenduto, finestra_start, finestra_end, rot_min) -> dict:
    df = df_raw.copy()
    n_totale = len(df)
    # Parsing robusto: accetta dd/mm/yyyy, yyyy-mm-dd, dd-mm-yyyy (strip spazi)
    _raw = df["Data_Fatturazione"].astype(str).str.strip()
    try:
        # pandas >= 2.0: format="mixed" gestisce formati eterogenei nella stessa colonna
        df["Data_Fatturazione"] = pd.to_datetime(_raw, format="mixed", dayfirst=True, errors="coerce")
    except TypeError:
        # pandas < 2.0: fallback sequenziale
        _parsed = pd.to_datetime(_raw, format="%d/%m/%Y", errors="coerce")
        _mask = _parsed.isna()
        _parsed[_mask] = pd.to_datetime(_raw[_mask], format="%Y-%m-%d", errors="coerce")
        _mask2 = _parsed.isna()
        _parsed[_mask2] = pd.to_datetime(_raw[_mask2], format="%d-%m-%Y", errors="coerce")
        df["Data_Fatturazione"] = _parsed

    warnings_list = []

    n_date_perse = df["Data_Fatturazione"].isna().sum()
    if n_date_perse > 0:
        pct = n_date_perse / n_totale * 100
        warnings_list.append(
            f"{n_date_perse} riga/e su {n_totale} ({pct:.1f}%) ha una data non riconoscibile "
            "ed è stata esclusa dall'analisi."
        )
    df = df.dropna(subset=["Data_Fatturazione"])

    oggi = date.today()
    n_future = (df["Data_Fatturazione"].dt.date > oggi).sum()
    if n_future > 0:
        warnings_list.append(
            f"{n_future} riga/e ha una Data_Fatturazione nel futuro — verifica i dati del gestionale."
        )

    for col in ["Giacenza", "Vendute_Ultimi_30_Giorni", "Prezzo_Copertina", "Sconto_Libreria"]:
        df[col] = parse_numeric(df[col])

    if len(df) > 0:
        median_sconto = df["Sconto_Libreria"].median()
        if median_sconto > 5:
            warnings_list.append(
                f"Sconto_Libreria: i valori sembrano essere in percentuale (mediana: {median_sconto:.1f}). "
                "Questa colonna deve contenere il valore assoluto in euro (es. 3.42, non 19). "
                "Il valore recuperabile calcolato potrebbe essere errato."
            )

    fat         = df["Data_Fatturazione"].dt.date
    df_scaduto  = df[fat < soglia_invenduto].copy()
    df_finestra = df[(fat >= finestra_start) & (fat <= finestra_end)].copy()
    df_finestra = df_finestra[df_finestra["Giacenza"] > 0]
    df_tenere   = df_finestra[df_finestra["Vendute_Ultimi_30_Giorni"] >= rot_min].copy()
    df_rendere  = df_finestra[df_finestra["Vendute_Ultimi_30_Giorni"] < rot_min].copy()
    df_rendere["Valore_Recuperabile"] = (
        (df_rendere["Prezzo_Copertina"] - df_rendere["Sconto_Libreria"]) * df_rendere["Giacenza"]
    )
    return {
        "df": df, "scaduto": df_scaduto, "tenere": df_tenere, "rendere": df_rendere,
        "warnings": warnings_list,
    }

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,600;0,700;1,400&family=Inter:wght@300;400;500;600&display=swap');

/* ── DESIGN SYSTEM ─────────────────────────────────────── */
:root {
    --font-serif: 'EB Garamond', 'Georgia', serif;
    --font-sans:  'Inter', 'Helvetica Neue', sans-serif;

    /* Light Mode (Default) */
    --bg:         #F5F1EC;
    --bg-card:    #FFFFFF;
    --bg-sidebar: #111110;
    --border:     #E7E3DC;
    --text:       #16130F;
    --text-2:     #5C5852;
    --text-muted: #9B9590;
    --accent:     #B5362C;
    --accent-2:   #8F2A22;
    --accent-bg:  rgba(181,54,44,.07);
    --shadow-sm:  0 1px 3px rgba(0,0,0,.06);
    --shadow-md:  0 4px 16px rgba(0,0,0,.09), 0 1px 4px rgba(0,0,0,.04);
    --radius:     10px;
    --radius-sm:  7px;
    --t:          .16s ease;
}

/* Dark Mode */
[data-theme="dark"] {
    --bg:         #1A1918;
    --bg-card:    #2D2B28;
    --bg-sidebar: #121110;
    --border:     #3A3835;
    --text:       #F5F1EC;
    --text-2:     #D4CCC4;
    --text-muted: #9B9590;
    --accent:     #E74C3C;
    --accent-2:   #FF6B5B;
    --accent-bg:  rgba(231,76,60,.15);
    --shadow-sm:  0 1px 3px rgba(0,0,0,.4);
    --shadow-md:  0 4px 16px rgba(0,0,0,.5), 0 1px 4px rgba(0,0,0,.3);
}

/* ── BASE ───────────────────────────────────────────────── */
html, body, .main, [data-testid="stAppViewContainer"] {
    background-color: var(--bg) !important;
    font-family: var(--font-sans) !important;
}
.main .block-container {
    padding-top: 1.75rem !important;
    padding-bottom: 3rem !important;
    max-width: 1200px !important;
}

/* ── SIDEBAR ────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    transform: none !important;
    min-width: 18rem !important;
    display: flex !important;
}
section[data-testid="stSidebar"] > div {
    background-color: var(--bg-sidebar) !important;
    border-right: 1px solid #1E1E1C !important;
    padding-top: 1.25rem !important;
    transition: background-color var(--t), border-color var(--t) !important;
}

[data-theme="dark"] section[data-testid="stSidebar"] > div {
    border-right-color: #3A3835 !important;
}

/* Nasconde il pulsante collapse/expand — sidebar sempre visibile */
button[data-testid="collapsedControl"],
[data-testid="collapsedControl"] {
    display: none !important;
}

/* Blanket: tutto il testo nella sidebar va schiarito — il textColor globale
   (#16130F) dal config.toml altrimenti rende invisibile il testo sul nero */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] small,
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] .stMarkdown p {
    font-family: var(--font-sans) !important;
    color: #8A8784 !important;
    transition: color var(--t) !important;
}

[data-theme="dark"] section[data-testid="stSidebar"],
[data-theme="dark"] section[data-testid="stSidebar"] p,
[data-theme="dark"] section[data-testid="stSidebar"] span,
[data-theme="dark"] section[data-testid="stSidebar"] div,
[data-theme="dark"] section[data-testid="stSidebar"] label,
[data-theme="dark"] section[data-testid="stSidebar"] small,
[data-theme="dark"] section[data-testid="stSidebar"] .stMarkdown,
[data-theme="dark"] section[data-testid="stSidebar"] .stMarkdown p {
    color: #9B9590 !important;
}

.sb-brand {
    display: flex; align-items: center; gap: .7rem;
    padding: .1rem .1rem .6rem .1rem;
}
.sb-brand-icon {
    width: 32px; height: 32px;
    background: linear-gradient(135deg, var(--accent) 0%, #C94A40 100%);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 15px; flex-shrink: 0;
    box-shadow: 0 2px 10px rgba(181,54,44,.4);
}
.sb-brand-name {
    font-size: .95rem; font-weight: 600;
    color: #EDEAE5 !important; letter-spacing: -.01em;
}
.sb-brand-sub { font-size: .67rem; color: #6A6764 !important; margin-top: 1px; }

/* Nav items */
section[data-testid="stSidebar"] [data-testid="stRadio"] label {
    padding: .44rem .7rem !important;
    border-radius: 6px !important;
    transition: background var(--t), color var(--t) !important;
    cursor: pointer !important;
    font-size: .82rem !important;
    color: #8A8784 !important;
    display: block !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: rgba(255,255,255,.07) !important;
    color: #C8C0B8 !important;
}
/* Hide radio indicator dot */
section[data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child {
    display: none !important;
}
section[data-testid="stSidebar"] hr { border-color: #252420 !important; margin: .5rem 0 !important; }

/* Captions e label file uploader */
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] span,
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    color: #6A6764 !important; font-size: .72rem !important;
}

section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
    border-color: #2A2A27 !important;
    background: #191917 !important;
    transition: border-color var(--t), background-color var(--t) !important;
}

[data-theme="dark"] section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
    border-color: #3A3835 !important;
    background: #252420 !important;
}
.sb-version {
    font-size: .67rem; color: #5A5856 !important;
    padding: .4rem .1rem .1rem .1rem;
    font-family: var(--font-sans);
    transition: color var(--t) !important;
}

[data-theme="dark"] .sb-version {
    color: #6A6764 !important;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: rgba(181,54,44,.14) !important;
    color: #D4CCC4 !important;
    border-radius: 6px;
    transition: background-color var(--t), color var(--t) !important;
}

[data-theme="dark"] section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: rgba(231,76,60,.2) !important;
    color: #FF9B85 !important;
}
.market-label {
    font-size: .75rem; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: .08em;
    margin: .5rem 0 .2rem 0;
}

/* ── PAGE HERO ──────────────────────────────────────────── */
.page-hero {
    padding: .2rem 0 1.2rem 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1.75rem;
}
.page-hero-eyebrow {
    font-size: .63rem; font-weight: 600;
    letter-spacing: .14em; text-transform: uppercase;
    color: var(--accent); margin-bottom: .5rem;
    display: flex; align-items: center; gap: .45rem;
}
.page-hero-eyebrow::before {
    content: ''; display: inline-block;
    width: 16px; height: 2px;
    background: var(--accent); border-radius: 1px;
}
.page-hero-title {
    font-family: var(--font-serif);
    font-size: 2.2rem; font-weight: 700;
    color: var(--text); letter-spacing: -.02em; line-height: 1.1;
    margin-bottom: .35rem;
}
.page-hero-sub { font-size: .82rem; color: var(--text); line-height: 1.55; opacity: 0.8; }

/* ── SECTION TITLES ─────────────────────────────────────── */
.section-title {
    font-family: var(--font-serif);
    font-size: 1.05rem; font-weight: 600;
    color: var(--text);
    margin: 1.35rem 0 .3rem 0;
    padding-left: .65rem;
    border-left: 2.5px solid var(--accent);
    line-height: 1.3;
}

/* ── METRIC CARDS ───────────────────────────────────────── */
.metric-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left-width: 3px;
    border-radius: 0 var(--radius) var(--radius) 0;
    padding: .9rem 1.15rem;
    margin-bottom: .6rem;
    box-shadow: var(--shadow-sm);
    transition: box-shadow var(--t), transform var(--t);
}
.metric-card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }
.mc-label {
    font-size: .63rem; font-weight: 600;
    letter-spacing: .1em; text-transform: uppercase;
    color: var(--text-muted); margin-bottom: .3rem;
}
.mc-value {
    font-family: var(--font-serif);
    font-size: 1.8rem; font-weight: 700; line-height: 1.05;
}
.mc-note { font-size: .71rem; color: var(--text-muted); margin-top: .3rem; line-height: 1.45; }

/* ── EMPTY STATE ────────────────────────────────────────── */
.empty-state {
    text-align: center; padding: 3rem 2rem;
    background: var(--bg-card);
    border: 1.5px dashed var(--border);
    border-radius: var(--radius);
}
.es-icon   { font-size: 2rem; margin-bottom: .7rem; opacity: .45; }
.es-title  { font-family: var(--font-serif); font-size: 1.05rem; color: var(--text-2); margin-bottom: .3rem; font-weight: 600; }
.es-body   { font-size: .81rem; color: var(--text-muted); line-height: 1.55; }

/* ── URGENCY BADGE ──────────────────────────────────────── */
.urgency-bar {
    display: inline-flex; align-items: center; gap: .35rem;
    background: linear-gradient(135deg, var(--accent) 0%, #C94A40 100%);
    color: white;
    font-size: .63rem; font-weight: 600;
    letter-spacing: .12em; text-transform: uppercase;
    padding: 3px 11px 3px 8px;
    border-radius: 20px; margin-bottom: .45rem;
    box-shadow: 0 2px 10px rgba(181,54,44,.28);
}
.urgency-bar::before {
    content: ''; width: 5px; height: 5px;
    background: rgba(255,255,255,.9); border-radius: 50%;
    animation: pulse-dot 1.8s ease-in-out infinite;
}
@keyframes pulse-dot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: .45; transform: scale(.7); }
}

/* ── MARKET LINKS ───────────────────────────────────────── */
.market-links { display: flex; gap: .65rem; margin: .5rem 0 .9rem 0; flex-wrap: wrap; }
.market-links a {
    font-size: .76rem; color: var(--accent) !important;
    text-decoration: none;
    border: 1px solid rgba(181,54,44,.2); background: var(--accent-bg);
    padding: 3px 10px; border-radius: 5px;
    font-weight: 500; transition: all var(--t);
}
.market-links a:hover { background: rgba(181,54,44,.14); border-color: var(--accent); }

/* ── STREAMLIT NATIVE OVERRIDES ─────────────────────────── */
hr { border-color: var(--border) !important; opacity: 1 !important; }

[data-testid="stCaptionContainer"] p { color: var(--text-muted) !important; font-size: .78rem !important; }

/* Inputs */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--border) !important;
    background: var(--bg-card) !important;
    font-family: var(--font-sans) !important;
    transition: border-color var(--t), box-shadow var(--t) !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px var(--accent-bg) !important;
    outline: none !important;
}

/* Expanders */
[data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    background: var(--bg-card) !important;
    box-shadow: var(--shadow-sm) !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    font-size: .83rem !important; font-weight: 500 !important; color: var(--text-2) !important;
    padding: .75rem 1rem !important;
}
[data-testid="stExpander"] summary:hover { color: var(--text) !important; }

/* Alerts */
[data-testid="stAlert"] { border-radius: var(--radius-sm) !important; font-size: .82rem !important; }

/* Primary button */
[data-testid="baseButton-primary"] {
    border-radius: var(--radius-sm) !important;
    font-weight: 500 !important; font-size: .85rem !important;
    transition: all var(--t) !important;
    box-shadow: 0 2px 8px rgba(181,54,44,.2) !important;
}
[data-testid="baseButton-primary"]:hover {
    box-shadow: 0 5px 18px rgba(181,54,44,.32) !important;
    transform: translateY(-1px) !important;
}
[data-testid="baseButton-primary"]:active { transform: translateY(0) !important; }

/* Secondary button */
[data-testid="baseButton-secondary"] {
    border-radius: var(--radius-sm) !important;
    font-weight: 500 !important; font-size: .85rem !important;
    border: 1px solid var(--border) !important;
    background: var(--bg-card) !important; color: var(--text-2) !important;
    transition: all var(--t) !important;
}
[data-testid="baseButton-secondary"]:hover {
    border-color: var(--accent) !important;
    color: var(--accent) !important; background: var(--accent-bg) !important;
}

/* Download button */
[data-testid="stDownloadButton"] > button {
    border-radius: var(--radius-sm) !important;
    font-weight: 500 !important; font-size: .82rem !important;
    border: 1px solid var(--border) !important;
    background: var(--bg-card) !important; color: var(--text-2) !important;
    transition: all var(--t) !important;
}
[data-testid="stDownloadButton"] > button:hover {
    border-color: var(--accent) !important;
    color: var(--accent) !important; background: var(--accent-bg) !important;
}

/* File uploader */
[data-testid="stFileUploaderDropzone"] {
    border-radius: var(--radius) !important;
    border: 1.5px dashed var(--border) !important;
    background: var(--bg-card) !important;
    transition: border-color var(--t) !important;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--accent) !important; }

/* Selectbox */
[data-testid="stSelectbox"] > div > div {
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--border) !important;
    background: var(--bg-card) !important;
}

/* DataFrames */
[data-testid="stDataFrame"] {
    border-radius: var(--radius) !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-sm) !important;
    border: 1px solid var(--border) !important;
}

/* Radio in main content */
[data-testid="stRadio"] label { font-size: .85rem !important; }

/* Misc hide — i pulsanti di collapse/expand sidebar NON vanno nascosti */
button[kind="headerNoPadding"] { display: none !important; }
/* Forza visibilità del bottone per riaprire la sidebar collassata */
button[data-testid="collapsedControl"],
[data-testid="collapsedControl"] { display: flex !important; visibility: visible !important; opacity: 1 !important; }

/* ── ANIMATIONS ─────────────────────────────────────────── */
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}
.main > div:first-child { animation: fadeUp .28s ease both; }

@keyframes slideInRight {
    from { opacity: 0; transform: translateX(400px); }
    to   { opacity: 1; transform: translateX(0); }
}

@keyframes slideOutRight {
    from { opacity: 1; transform: translateX(0); }
    to   { opacity: 0; transform: translateX(400px); }
}

/* ── TOAST NOTIFICATIONS ────────────────────────────────── */
.toast-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    pointer-events: none;
}

.toast {
    animation: slideInRight .3s ease both;
    padding: 14px 16px;
    border-radius: 8px;
    margin-bottom: 12px;
    font-size: 14px;
    font-weight: 500;
    box-shadow: 0 8px 24px rgba(0,0,0,.15);
    display: flex;
    align-items: center;
    gap: 10px;
    max-width: 320px;
    pointer-events: auto;
    transition: opacity var(--t);
}

.toast.success {
    background: #ECFDF5;
    color: #065F46;
    border-left: 4px solid #10B981;
}

.toast.warning {
    background: #FFFBEB;
    color: #78350F;
    border-left: 4px solid #F59E0B;
}

.toast.error {
    background: #FEF2F2;
    color: #991B1B;
    border-left: 4px solid #EF4444;
}

.toast.info {
    background: #EFF6FF;
    color: #0C4A6E;
    border-left: 4px solid #0284C7;
}

[data-theme="dark"] .toast.success {
    background: #064E3B;
    color: #DCFCE7;
    border-left-color: #10B981;
}

[data-theme="dark"] .toast.warning {
    background: #78350F;
    color: #FEF3C7;
    border-left-color: #F59E0B;
}

[data-theme="dark"] .toast.error {
    background: #7F1D1D;
    color: #FECACA;
    border-left-color: #EF4444;
}

[data-theme="dark"] .toast.info {
    background: #0C2D48;
    color: #BAE6FD;
    border-left-color: #0284C7;
}

.toast-icon { font-size: 18px; flex-shrink: 0; }
.toast-text { flex: 1; }
.toast.removing { animation: slideOutRight .3s ease forwards; }

/* ── DARK MODE OVERRIDES ────────────────────────────────── */
[data-theme="dark"] {
    color-scheme: dark;
}

[data-theme="dark"] [data-testid="stAlert"] {
    background-color: rgba(100, 100, 100, 0.15) !important;
    border-color: var(--border) !important;
    color: var(--text) !important;
}

[data-theme="dark"] [data-testid="stDataFrame"] {
    background-color: var(--bg-card) !important;
}

[data-theme="dark"] [data-testid="stDataFrame"] tbody {
    background-color: var(--bg) !important;
}

/* ── SCROLLBAR ──────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; transition: background var(--t); }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }
</style>
""", unsafe_allow_html=True)

# Apply dark mode theme based on session_state
dark_mode_enabled = st.session_state.get("dark_mode", False)
theme_attr = 'data-theme="dark"' if dark_mode_enabled else ''
st.markdown(f"""
<script>
document.documentElement.setAttribute("data-theme", {'"dark"' if dark_mode_enabled else '"light"'});

// Toast notification system
window.showToast = function(message, type = 'info', duration = 4000) {{
    // Crea il contenitore toast se non esiste
    let container = document.querySelector('.toast-container');
    if (!container) {{
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }}

    // Mappa icone per tipo di notifica
    const icons = {{
        'success': '✓',
        'error': '✕',
        'warning': '⚠',
        'info': 'ℹ'
    }};

    // Crea elemento toast
    const toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.innerHTML = `
        <div class="toast-icon">${{icons[type] || 'ℹ'}}</div>
        <div class="toast-text">${{message}}</div>
    `;

    // Aggiungi al contenitore
    container.appendChild(toast);

    // Auto-rimuovi dopo duration
    setTimeout(() => {{
        toast.classList.add('removing');
        setTimeout(() => {{
            toast.remove();
        }}, 300);
    }}, duration);
}};
</script>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# ECONOMIST CHART STYLE — usato in Analisi storica e Simulatore ordine
# ---------------------------------------------------------------------------
def _econ(fig, *, title="", subtitle="", ysuffix="", yprefix="", x0=False, src="", show_png=True):
    """Applica lo stile Economist a un oggetto Plotly Figure con animazioni e interattività premium."""
    try:
        # Dark mode support
        dark_mode = st.session_state.get("dark_mode", False)
        if dark_mode:
            # Dark mode colors
            bg_color = "#2D2B28"
            text_color = "#F5F1EC"
            text_secondary = "#D4CCC4"
            grid_color = "#3A3835"
            border_color = "#4A4844"
            hover_bg = "#3A3835"
            hover_text = "#F5F1EC"
        else:
            # Light mode colors
            bg_color = "white"
            text_color = "#16130F"
            text_secondary = "#5C5852"
            grid_color = "#F0EBE5"
            border_color = "#D5D0CB"
            hover_bg = "#16130F"
            hover_text = "#F5F1EC"

        title_html = (f"<b>{title}</b>" if title else "") + (
            f"<br><span style='font-size:12px;color:{text_secondary};font-weight:400;letter-spacing:0.3px'>{subtitle}</span>"
            if subtitle else ""
        )
        fig.update_layout(
            paper_bgcolor=bg_color, plot_bgcolor=bg_color,
            font=dict(family="Inter,'Helvetica Neue',sans-serif", color=text_color, size=12),
            title=dict(
                text=title_html, x=0, xanchor="left",
                font=dict(size=16, color=text_color, family="Inter,'Helvetica Neue',sans-serif", weight="bold"),
                pad=dict(b=12, l=0, t=4),
            ),
            margin=dict(l=12, r=52, t=88 if title else 28, b=80 if src else 56),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.03, xanchor="left", x=0,
                font=dict(size=11, color=text_secondary, family="Inter"),
                bgcolor="rgba(0,0,0,0)", borderwidth=0, itemsizing="constant",
                tracegroupgap=20,
            ),
            xaxis=dict(
                showgrid=False, showline=True, linecolor=border_color, linewidth=1.2,
                tickfont=dict(size=11, color=text_secondary, family="Inter"),
                ticks="outside", ticklen=4, tickcolor=border_color, title=None,
                mirror=False,
            ),
            yaxis=dict(
                showgrid=True, gridcolor=grid_color, gridwidth=0.8,
                showline=False, tickfont=dict(size=11, color=text_secondary, family="Inter"),
                ticksuffix=ysuffix, tickprefix=yprefix, title=None,
                zeroline=x0, zerolinecolor=border_color, zerolinewidth=1.5,
                griddash="solid",
            ),
            hoverlabel=dict(
                bgcolor=hover_bg, font_color=hover_text, font_family="Inter",
                font_size=12, bordercolor=text_secondary, borderwidth=1,
                namelength=-1, align="left",
            ),
            hovermode="x unified",
            dragmode="box",
            transition=dict(duration=500, easing="cubic-in-out"),
            showlegend=True,
        )

        # Aggiorna tutte le tracce con animazioni e stili migliorati
        for trace in fig.data:
            if hasattr(trace, 'line'):
                trace.update(
                    line=dict(width=trace.line.width if trace.line.width else 3),
                    connectgaps=True,
                )
            if hasattr(trace, 'marker'):
                if trace.marker:
                    marker_size = trace.marker.size if trace.marker.size else 10
                    if trace.marker.size:
                        trace.update(marker=dict(
                            size=max(marker_size, 9),
                            line=dict(width=2.5, color="white"),
                        ))

        # Annotazione fonte con migliore formattazione
        if src:
            src_color = "#9B9590" if not dark_mode else "#9B9590"
            fig.add_annotation(
                text=f"<i>Fonte: {src}</i>", xref="paper", yref="paper",
                x=0, y=-0.22, showarrow=False,
                font=dict(size=9, color=src_color, family="Inter"),
                xanchor="left", yanchor="top",
            )

        return fig
    except Exception as e:
        logging.error(f"Errore in _econ(): {str(e)}")
        return fig

# ---------------------------------------------------------------------------
# UTILITÀ VALIDAZIONE DATI PER GRAFICI
# ---------------------------------------------------------------------------
def validate_numeric_data(series, name="dati"):
    """Valida una serie di dati numerici per il plotting.

    Controlla:
    - Presenza di NaN o infiniti
    - Lunghezza minima
    - Presenza di almeno un valore valido

    Returns:
        bool: True se i dati sono validi, False altrimenti
    """
    try:
        if series is None or len(series) == 0:
            logging.warning(f"Serie '{name}' vuota")
            return False
        if np.all(np.isnan(series)):
            logging.warning(f"Serie '{name}' contiene solo NaN")
            return False
        if np.all(np.isinf(series)):
            logging.warning(f"Serie '{name}' contiene solo infiniti")
            return False
        return True
    except Exception as e:
        logging.warning(f"Errore validazione '{name}': {str(e)}")
        return False

def safe_divide(numerator, denominator, default=0):
    """Divisione sicura con protezione da divisioni per zero."""
    try:
        if denominator == 0 or np.isnan(denominator) or np.isinf(denominator):
            return default
        result = numerator / denominator
        return default if (np.isnan(result) or np.isinf(result)) else result
    except Exception:
        return default

def export_to_excel_bytes(dataframes_dict: dict) -> bytes:
    """
    Esporta un dizionario di dataframe in un file Excel (in memoria).
    Ogni dataframe diventa un foglio separato.

    Args:
        dataframes_dict: dict con {nome_foglio: dataframe}

    Returns:
        bytes: contenuto del file Excel
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from io import BytesIO

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for sheet_name, df in dataframes_dict.items():
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False)  # Excel max 31 chars

                # Formatting
                worksheet = writer.sheets[sheet_name[:31]]
                header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
                header_font = Font(bold=True, color="FFFFFF")

                for cell in worksheet[1]:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal="center", vertical="center")

                # Auto-adjust column widths
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width

        return output.getvalue()
    except Exception as e:
        st.error(f"Errore nel generare l'Excel: {e}")
        return None

# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
mag_ok      = st.session_state["df_mag"] is not None
n_usato     = len(st.session_state["inventario_usato"])
storico_ok  = len(st.session_state.get("storico_up") or []) >= 2
sim_ok      = mag_ok
storico_files_sb = []

with st.sidebar:
    st.markdown("""<div class="sb-brand">
        <div class="sb-brand-icon">📚</div>
        <div>
            <div class="sb-brand-name">BookStore OS</div>
            <div class="sb-brand-sub">Toolkit librai indipendenti</div>
        </div>
    </div>""", unsafe_allow_html=True)

    # Dark mode toggle
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown('<span style="font-size: 13px; color: #8A8784;">Tema</span>', unsafe_allow_html=True)
    with col2:
        st.toggle("🌙", value=st.session_state.get("dark_mode", False),
                  key="dark_mode", label_visibility="collapsed")

    st.divider()

    # Navigazione con selectbox - alternativa ai bottoni
    nav_labels = {
        "Dashboard":                  "📊 Dashboard",
        "Analisi resi":               f"Radar Salva-Cassa{'  ✓' if mag_ok else ''}",
        "Calcolatore margine ordine": "Calcolatore margine",
        "Gestione usato":             f"Gestione usato{'  ' + str(n_usato) if n_usato > 0 else ''}",
        "Analisi storica":            f"Analisi storica{'  ✓' if storico_ok else ''}",
        "Simulatore ordine":          f"Simulatore ordine{'  ✓' if sim_ok else ''}",
    }

    # Ottieni la pagina dal session_state, con fallback sicuro
    pagina_salvata = st.session_state.get("pagina", "Dashboard")
    if pagina_salvata not in PAGINE:
        pagina_salvata = "Dashboard"
    idx_current = PAGINE.index(pagina_salvata)

    strumento = st.selectbox(
        "Vai a:",
        PAGINE,
        index=idx_current,
        key="pagina",
        format_func=lambda x: nav_labels[x],
        label_visibility="collapsed"
    )

    if strumento == "Analisi resi":
        st.divider()
        colors = get_theme_colors()
        st.markdown(f'<span style="color: {colors[\"text_secondary\"]}; font-size: 13px; font-weight: 500;">📋 File di lavoro · ✓ = caricato</span>', unsafe_allow_html=True)
        st.markdown("📁 **Trascina il file CSV qui oppure clicca per sfogliare**")
        mag_file_sb = st.file_uploader("Gestionale magazzino", type="csv", key="mag_up", label_visibility="collapsed")
        _bcol1, _bcol2 = st.columns(2)
        with _bcol1:
            if st.button("Carica demo", use_container_width=True, key="load_demo_btn"):
                try:
                    demo_df = pd.read_csv(pathlib.Path(__file__).parent / "storico_apr2024.csv")
                    demo_df = normalize_columns(demo_df)
                    if validate_schema(demo_df, SCHEMA_MAGAZZINO, "Demo"):
                        st.session_state["df_mag"] = demo_df
                        st.session_state["df_mag_name"] = "storico_apr2024.csv [DEMO]"
                        st.success("Demo caricata!")
                except Exception as e:
                    st.error(f"Errore caricamento demo: {e}")
        with _bcol2:
            pass  # Spazio vuoto per simmetria
    elif strumento == "Analisi storica":
        st.divider()
        st.markdown("📊 **Carica 2+ snapshot CSV** · stesso formato del gestionale · ordine cronologico")
        st.markdown("📁 **Trascina i file CSV qui oppure clicca per sfogliare**")
        storico_files_sb = st.file_uploader(
            "Snapshot storici", type="csv",
            accept_multiple_files=True, key="storico_up",
            label_visibility="collapsed",
        ) or []
        mag_file_sb = None
    elif strumento == "Simulatore ordine":
        st.divider()
        st.markdown("📈 **Usa il gestionale già caricato come base** · caricalo nel Radar Salva-Cassa")
        mag_file_sb = None
    else:
        mag_file_sb = None

    get_or_load("df_mag", mag_file_sb, SCHEMA_MAGAZZINO, "Gestionale magazzino")
    st.divider()

    if n_usato > 0:
        st.markdown(f"💾 **Inventario:** {n_usato} libri · `{INVENTORY_FILE.name}`")
        st.divider()

    # Settings & Preferences
    with st.expander("⚙️ Impostazioni"):
        st.markdown("**Preferenze**")
        if st.button("🔄 Ripristina preferenze", use_container_width=True, key="reset_prefs_btn"):
            # Ripristina i valori di default per le preferenze persistenti
            PREFS_DEFAULTS = {
                "dark_mode": False,
                "calc_prezzo": 18.00,
                "calc_sconto": 30,
                "calc_resa_pct": 20,
                "calc_affitto": 0.0,
                "calc_utenze": 0.0,
                "calc_personale": 0.0,
                "calc_altri": 0.0,
                "calc_inv_target": 30,
            }
            for k, v in PREFS_DEFAULTS.items():
                st.session_state[k] = v
            # Elimina il file preferenze
            if PREFERENCES_FILE.exists():
                PREFERENCES_FILE.unlink()
            # Usa sia il toast che il messaggio nativo per massima visibilità
            show_toast("Preferenze ripristinate ai valori di default", "success", 3000)
            st.success("✓ Preferenze ripristinate")
            st.rerun()

        st.markdown(f"""
        **Dati salvati:**
        - 🌙 Tema: {'scuro' if st.session_state.get('dark_mode') else 'chiaro'}
        - 📊 Calcolatore: {len([k for k in PERSISTENT_PREFS if k.startswith('calc_')])} impostazioni
        """)

    st.markdown('<div class="sb-version">v3.1</div>', unsafe_allow_html=True)

# ===========================================================================
# DASHBOARD
# ===========================================================================
if strumento == "Dashboard":
    page_header("Dashboard", "Panoramica della tua libreria e azioni rapide")

    # ── Sezione 1: Stato Magazzino ──────────────────────────────────────────
    if mag_ok:
        df_mag = st.session_state.get("df_mag")

        st.divider()
        section("📦 Stato Magazzino")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            n_titoli = len(df_mag)
            metric_card("Totale titoli", f"{n_titoli:,}", "neutral")
        with col2:
            tot_giacenza = df_mag["Giacenza"].sum()
            metric_card("Copie in stock", f"{tot_giacenza:,}", "positive")
        with col3:
            val_mag = ((df_mag["Prezzo_Copertina"] - df_mag["Sconto_Libreria"]) * df_mag["Giacenza"]).sum()
            metric_card("Valore magazzino", fmt_euro(val_mag), "positive")
        with col4:
            avg_rot = df_mag["Vendute_Ultimi_30_Giorni"].sum() / max(1, n_titoli)
            metric_card("Rotazione media", f"{avg_rot:.1f} copie/mese", "neutral")

        # ── Sezione 2: File caricato ────────────────────────────────────────
        st.divider()
        section("📂 File Caricato")

        # Calcola statistiche file
        file_stats = get_file_stats(df_mag, SCHEMA_MAGAZZINO)
        file_name = st.session_state.get("df_mag_name", "N/A")
        colors = get_theme_colors()

        # Card principale con info file
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.markdown(
                f'<div style="color: {colors[\"text\"]}; font-size: 14px; padding: 14px; background: {colors[\"bg_card\"]}; border-radius: 8px; border: 1px solid {colors[\"border\"]}; border-left: 4px solid {colors[\"accent\"]};">'
                f'<div><strong style="font-size: 15px;">📄 {file_name}</strong></div>'
                f'<div style="margin-top: 8px; font-size: 13px; color: {colors[\"text_secondary\"]};"><strong>{file_stats[\"total_rows\"]:,}</strong> righe</div>'
                f'<div style="margin-top: 4px; font-size: 12px; color: {colors[\"text_muted\"]};"> Dati: {file_stats[\"date_range\"]}</div>'
                f'</div>', unsafe_allow_html=True
            )

        with col2:
            # Quality score
            quality_pct = file_stats["quality"]
            quality_color = "#22C55E" if quality_pct >= 90 else "#F59E0B" if quality_pct >= 70 else "#EF4444"
            st.markdown(
                f'<div style="text-align: center; padding: 14px; background: {colors[\"bg_card\"]}; border-radius: 8px; border: 1px solid {colors[\"border\"]};">'
                f'<div style="font-size: 28px; margin-bottom: 2px;">{file_stats[\"rating_icon\"]}</div>'
                f'<div style="font-size: 11px; color: {colors[\"text_muted\"]}; text-transform: uppercase; letter-spacing: 0.05em;">Qualità</div>'
                f'<div style="font-size: 13px; font-weight: 600; color: {colors[\"text\"]}; margin-top: 4px;">{file_stats[\"rating\"]}</div>'
                f'<div style="font-size: 12px; color: {quality_color}; margin-top: 3px;">{quality_pct:.0f}%</div>'
                f'</div>', unsafe_allow_html=True
            )

        with col3:
            # Coverage info
            col_cov = file_stats["col_coverage"]
            st.markdown(
                f'<div style="text-align: center; padding: 14px; background: {colors[\"bg_card\"]}; border-radius: 8px; border: 1px solid {colors[\"border\"]};">'
                f'<div style="font-size: 28px; margin-bottom: 2px;">📊</div>'
                f'<div style="font-size: 11px; color: {colors[\"text_muted\"]}; text-transform: uppercase; letter-spacing: 0.05em;">Colonne</div>'
                f'<div style="font-size: 13px; font-weight: 600; color: {colors[\"text\"]}; margin-top: 4px;">{col_cov:.0f}%</div>'
                f'<div style="font-size: 11px; color: {colors[\"text_secondary\"]}; margin-top: 3px;">Complete</div>'
                f'</div>', unsafe_allow_html=True
            )

        # Bottone carica nuovo
        if st.button("📥 Carica nuovo file", use_container_width=True, key="dashboard_load_btn"):
            st.info("👈 Usa il file uploader nella barra laterale")

        # Alert se qualità è bassa
        if file_stats["quality"] < 70 and file_stats["missing_cols"]:
            st.warning(f"⚠️ File con possibili problemi. Colonne mancanti: {', '.join(sorted(file_stats['missing_cols']))}")
        elif file_stats["quality"] < 85:
            st.info(f"💡 Qualità file: {file_stats['rating']}. Controlla i dati mancanti.")

        # ── Sezione 3: Azioni rapide ────────────────────────────────────────
        st.divider()
        section("⚡ Azioni Rapide")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🔍 Analiza magazzino", key="dash_radar", use_container_width=True):
                st.session_state["pagina"] = "Analisi resi"
                st.rerun()
        with col2:
            if st.button("📊 Analisi storica", key="dash_storico", use_container_width=True):
                st.session_state["pagina"] = "Analisi storica"
                st.rerun()
        with col3:
            if st.button("🧮 Calcolo margine", key="dash_margine", use_container_width=True):
                st.session_state["pagina"] = "Calcolatore margine ordine"
                st.rerun()

        st.divider()
        st.markdown("""
        <div style="padding: 12px; background: #E8F4F8; border-left: 4px solid #0284C7; border-radius: 4px; color: #0C4A6E;">
        <strong>💡 Consiglio:</strong> Inizia caricando il tuo gestionale dalla barra laterale,
        poi usa il Radar Salva-Cassa per identificare i titoli da rendere e i libri a rotazione lenta.
        </div>
        """, unsafe_allow_html=True)

    else:
        st.divider()
        empty_state("📦", "Nessun file caricato",
                   "Carica il tuo gestionale dalla barra laterale per iniziare l'analisi del magazzino.")
        st.divider()
        st.info("👈 Usa il **file uploader** sulla sinistra per caricare il gestionale in formato CSV")

# ===========================================================================
# ANALISI RESI — Radar Salva-Cassa
# ===========================================================================
if strumento == "Analisi resi":
    page_header("Radar Salva-Cassa", f"Data di sistema: {DATA_SISTEMA.strftime('%d/%m/%Y')}.")
    st.markdown(
        "📋 **Carica il gestionale magazzino dalla barra laterale**\n\n"
        "Colonne richieste: `Titolo` · `Autore` · `Editore` · `ISBN` · "
        "`Data_Fatturazione` (gg/mm/aaaa) · `Giacenza` · "
        "`Vendute_Ultimi_30_Giorni` · `Prezzo_Copertina` · `Sconto_Libreria`"
    )
    df_mag = st.session_state.get("df_mag")

    with st.expander("⚙️ Parametri analisi", expanded=False):
        st.markdown("📋 **Adatta le soglie alle condizioni del tuo distributore.**")
        _c1, _c2, _c3 = st.columns(3)

        help_invenduto = create_help_tooltip(
            "Invenduto dopo",
            "Titoli fatturati prima di questo numero di giorni fa sono considerati invenduto scaduto e disponibili per resa.",
            "90 giorni (3 mesi), 180 giorni (6 mesi), 365 giorni (1 anno)",
            "182 giorni (6 mesi) — equilibrio tra resa tempestiva e rotazione lenta"
        )
        _giorni_invenduto = _c1.number_input(
            "Invenduto dopo (giorni)", min_value=30, max_value=730, value=182, step=30,
            help=help_invenduto)

        help_finestra = create_help_tooltip(
            "Ampiezza finestra resa",
            "Durata della finestra temporale di resa a partire dalla soglia invenduto. Identifica i titoli in scadenza di resa.",
            "7 giorni (una settimana), 15 giorni (due settimane), 30 giorni (un mese)",
            "30 giorni — consente una corretta gestione dei tempi di resa al distributore"
        )
        _giorni_finestra  = _c2.number_input(
            "Ampiezza finestra resa (giorni)", min_value=7, max_value=90, value=30, step=7,
            help=help_finestra)

        help_rotazione = create_help_tooltip(
            "Rotazione minima",
            "Soglia di vendite mensili. Titoli con vendite inferiori sono classificati lenti e candidati a resa.",
            "1-2 copie/mese (titoli molto lenti), 3-5 copie/mese (titoli lenti), 5+ copie/mese (titoli stabili)",
            "3 copie/mese — criterio benchmark per identificare titoli in stallo"
        )
        _rot_min          = _c3.number_input(
            "Rotazione minima (copie/mese)", min_value=1, max_value=20, value=int(SOGLIA_ROTAZIONE_MIN), step=1,
            help=help_rotazione)
        soglia_inv  = DATA_SISTEMA - timedelta(days=int(_giorni_invenduto))
        soglia_fs   = soglia_inv
        soglia_fe   = soglia_fs + timedelta(days=int(_giorni_finestra))
        rot_min_ui  = int(_rot_min)

    if df_mag is not None:
        with st.spinner("🔄 Analisi magazzino in corso…"):
            seg = processa_magazzino(df_mag, soglia_inv, soglia_fs, soglia_fe, rot_min_ui)

        for msg in seg["warnings"]:
            st.warning(f"⚠️ {msg}")

        df, df_scaduto, df_tenere, df_rendere = seg["df"], seg["scaduto"], seg["tenere"], seg["rendere"]
        totale_recuperabile = df_rendere["Valore_Recuperabile"].sum()

        st.divider()
        c1, c2, c3 = st.columns(3)
        with c1:
            metric_card("Liquidità recuperabile", fmt_euro(totale_recuperabile),
                        "positive" if totale_recuperabile > 0 else "neutral",
                        f"{len(df_rendere)} titoli da rendere")
        with c2:
            valore_scaduto = (df_scaduto["Prezzo_Copertina"] - df_scaduto["Sconto_Libreria"]) * df_scaduto["Giacenza"]
            metric_card("Invenduto scaduto", str(len(df_scaduto)),
                        "negative" if len(df_scaduto) > 0 else "neutral",
                        f"valore a costo: {fmt_euro(valore_scaduto.sum())}" if len(df_scaduto) > 0 else "")
        with c3:
            metric_card("In rotazione — da tenere", str(len(df_tenere)),
                        "positive" if len(df_tenere) > 0 else "neutral")
        st.divider()

        # ── Da rendere ──────────────────────────────────────────────────────
        if not df_rendere.empty:
            st.markdown('<span class="urgency-bar">Azione richiesta</span>', unsafe_allow_html=True)
        section("Da rendere oggi")
        st.markdown(
            f'<div style="color: #5C5852; font-size: 13px; line-height: 1.8; padding: 8px 0; margin: -15px 0 15px 0;">'
            f'Fatturati tra <strong>{soglia_fs.strftime("%d/%m/%Y")}</strong> e <strong>{soglia_fe.strftime("%d/%m/%Y")}</strong><br>'
            f'Vendite ultime 30 gg &lt; <strong>{rot_min_ui}</strong> copie/mese · giacenza &gt; 0'
            f'</div>',
            unsafe_allow_html=True
        )
        if df_rendere.empty:
            empty_state("✓", "Nessun titolo da rendere",
                        "Non ci sono titoli in scadenza di resa per questa finestra.")
        else:
            cols_r = [c for c in ["Titolo","Autore","Editore","ISBN","Data_Fatturazione",
                                   "Giacenza","Vendute_Ultimi_30_Giorni",
                                   "Prezzo_Copertina","Sconto_Libreria","Valore_Recuperabile"]
                      if c in df_rendere.columns]
            df_rendere_sorted = df_rendere[cols_r].sort_values("Valore_Recuperabile", ascending=False).copy()
            if "Data_Fatturazione" in df_rendere_sorted.columns:
                df_rendere_sorted["Data_Fatturazione"] = df_rendere_sorted["Data_Fatturazione"].dt.strftime("%d/%m/%Y")
            st.dataframe(df_rendere_sorted, use_container_width=True, hide_index=True,
                         height=max(150, min(400, 45 + len(df_rendere_sorted) * 35)))

            # Export buttons
            col_csv, col_excel = st.columns(2)
            with col_csv:
                _clicked_rendere = st.download_button(
                    label="📥 Esporta CSV",
                    data=df_rendere_sorted.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"da_rendere_{DATA_SISTEMA.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            with col_excel:
                excel_data = export_to_excel_bytes({"Da rendere": df_rendere_sorted})
                st.download_button(
                    label="📊 Esporta Excel",
                    data=excel_data,
                    file_name=f"da_rendere_{DATA_SISTEMA.strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            if _clicked_rendere:
                save_decision_log(
                    action_type="resa",
                    titoli=df_rendere_sorted["Titolo"].tolist() if "Titolo" in df_rendere_sorted.columns else [],
                    n_copie=int(df_rendere_sorted["Giacenza"].sum()) if "Giacenza" in df_rendere_sorted.columns else 0,
                    valore=float(df_rendere_sorted["Valore_Recuperabile"].sum()) if "Valore_Recuperabile" in df_rendere_sorted.columns else 0.0,
                )

            # ── Raggruppamento per editore ───────────────────────────────
            with st.expander("📊 Da rendere per editore — per preparare le distinte di resa"):
                if "Editore" in df_rendere.columns:
                    grp = (
                        df_rendere
                        .groupby("Editore", dropna=False)
                        .agg(
                            Titoli   =("Titolo",             "count"),
                            Copie    =("Giacenza",           "sum"),
                            Valore   =("Valore_Recuperabile","sum"),
                        )
                        .sort_values("Valore", ascending=False)
                        .reset_index()
                    )
                    grp["Valore"] = grp["Valore"].apply(fmt_euro)
                    grp = grp.rename(columns={"Valore": "Valore recuperabile"})
                    st.dataframe(grp, use_container_width=True, hide_index=True)
                    st.caption(
                        f"{len(grp)} editori/distributori · "
                        f"{int(df_rendere['Giacenza'].sum())} copie totali"
                    )
                else:
                    st.info("Colonna 'Editore' non presente nel file.")

        st.divider()

        # ── Da tenere ────────────────────────────────────────────────────────
        section("Da tenere — in rotazione")
        st.markdown(
            f'<div style="color: #5C5852; font-size: 13px; line-height: 1.8; padding: 8px 0; margin: -15px 0 15px 0;">'
            f'Fatturati tra <strong>{soglia_fs.strftime("%d/%m/%Y")}</strong> e <strong>{soglia_fe.strftime("%d/%m/%Y")}</strong><br>'
            f'Vendite ultime 30 gg ≥ <strong>{rot_min_ui}</strong> copie/mese'
            f'</div>',
            unsafe_allow_html=True
        )
        if df_tenere.empty:
            empty_state("—", "Nessun titolo in rotazione attiva", "")
        else:
            cols_t = [c for c in ["Titolo","Autore","Editore","ISBN","Data_Fatturazione",
                                   "Giacenza","Vendute_Ultimi_30_Giorni","Prezzo_Copertina"]
                      if c in df_tenere.columns]
            df_tenere_disp = df_tenere[cols_t].sort_values("Vendute_Ultimi_30_Giorni", ascending=False).copy()
            if "Data_Fatturazione" in df_tenere_disp.columns:
                df_tenere_disp["Data_Fatturazione"] = df_tenere_disp["Data_Fatturazione"].dt.strftime("%d/%m/%Y")
            st.dataframe(df_tenere_disp, use_container_width=True, hide_index=True,
                         height=max(150, min(400, 45 + len(df_tenere_disp) * 35)))
        st.divider()

        # ── Invenduto scaduto ─────────────────────────────────────────────
        section("Invenduto scaduto")
        st.markdown(
            f'<div style="color: #5C5852; font-size: 13px; line-height: 1.8; padding: 8px 0; margin: -15px 0 15px 0;">'
            f'Fatturati prima del <strong>{soglia_inv.strftime("%d/%m/%Y")}</strong><br>'
            f'Fuori dalla finestra di resa'
            f'</div>',
            unsafe_allow_html=True
        )
        if df_scaduto.empty:
            empty_state("✓", "Nessun invenduto scaduto",
                        "Tutti i titoli rientrano nelle finestre temporali attive.")
        else:
            cols_s = [c for c in ["Titolo","Autore","Editore","ISBN","Data_Fatturazione",
                                   "Giacenza","Vendute_Ultimi_30_Giorni","Prezzo_Copertina"]
                      if c in df_scaduto.columns]
            df_scaduto_sorted = df_scaduto[cols_s].sort_values("Data_Fatturazione").copy()
            if "Data_Fatturazione" in df_scaduto_sorted.columns:
                df_scaduto_sorted["Data_Fatturazione"] = df_scaduto_sorted["Data_Fatturazione"].dt.strftime("%d/%m/%Y")
            st.dataframe(df_scaduto_sorted, use_container_width=True, hide_index=True,
                         height=max(150, min(400, 45 + len(df_scaduto_sorted) * 35)))

            # Avviso libri scaduti ma ancora in buona rotazione — non vanno svuotati
            df_scaduto_vendono = df_scaduto[df_scaduto["Vendute_Ultimi_30_Giorni"] >= rot_min_ui]
            if not df_scaduto_vendono.empty:
                titoli_list = df_scaduto_vendono["Titolo"].tolist()
                n_titoli = len(titoli_list)

                # Mostra solo i primi 10 titoli in anteprima
                preview_limit = 10
                titoli_preview = titoli_list[:preview_limit]
                titoli_preview_str = ", ".join(f"«{t}»" for t in titoli_preview)

                if n_titoli <= preview_limit:
                    st.info(
                        f"⚠️ **{n_titoli} titolo/i scaduti vendono ancora bene "
                        f"(≥ {rot_min_ui} copie/mese):** {titoli_preview_str}. "
                        "Fuori dalla finestra di resa, ma conviene tenerli in vetrina."
                    )
                else:
                    st.info(
                        f"⚠️ **{n_titoli} titolo/i scaduti vendono ancora bene "
                        f"(≥ {rot_min_ui} copie/mese)** — Mostrando i primi {preview_limit} di {n_titoli}:"
                    )
                    st.markdown(f"**Titoli:** {titoli_preview_str}")

                    with st.expander(f"📖 Visualizza tutti i {n_titoli} titoli"):
                        # Pagina i titoli in gruppi di 50
                        per_page = 50
                        n_pages = (n_titoli + per_page - 1) // per_page

                        if n_pages <= 3:
                            # Se pochi titoli, mostrali tutti subito
                            all_titoli_str = ", ".join(f"«{t}»" for t in titoli_list)
                            st.markdown(all_titoli_str)
                        else:
                            # Se molti, offri selezione pagina
                            page = st.selectbox(
                                "Pagina",
                                options=range(1, n_pages + 1),
                                key="scaduti_vendono_page"
                            )
                            start_idx = (page - 1) * per_page
                            end_idx = min(start_idx + per_page, n_titoli)
                            page_titoli = titoli_list[start_idx:end_idx]
                            page_titoli_str = ", ".join(f"«{t}»" for t in page_titoli)
                            st.markdown(page_titoli_str)

                    st.caption("💡 Questi titoli sono fuori dalla finestra di resa, ma vendono ancora bene: conviene tenerli in vetrina.")

            _wc1, _wc2 = st.columns([2, 1])
            with _wc1:
                st.warning(
                    f"{len(df_scaduto)} titolo/i fuori dalla finestra di resa. "
                    "Valuta promozioni mirate o contatti con il distributore."
                )
            with _wc2:
                _clicked_scaduto = st.download_button(
                    label="📥 Esporta invenduto (CSV)",
                    data=df_scaduto_sorted.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"invenduto_scaduto_{DATA_SISTEMA.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
                if _clicked_scaduto:
                    save_decision_log(
                        action_type="analisi_invenduto",
                        titoli=df_scaduto_sorted["Titolo"].tolist() if "Titolo" in df_scaduto_sorted.columns else [],
                        n_copie=int(df_scaduto_sorted["Giacenza"].sum()) if "Giacenza" in df_scaduto_sorted.columns else 0,
                        valore=float(df_scaduto_sorted["Prezzo_Copertina"].sum()) if "Prezzo_Copertina" in df_scaduto_sorted.columns else 0.0,
                    )
        # ── Piano d'azione ────────────────────────────────────────────────
        st.divider()
        with st.expander("📊 Piano d'azione — priorità per cassa", expanded=True):
            st.caption(
                "Tutti i titoli con giacenza attiva, ordinati per cassa immobilizzata (€ a costo). "
                "La copertura è calcolata su vendite reali degli ultimi 30 giorni."
            )

            dfs_piano = []
            if not df_rendere.empty:
                r = df_rendere.copy(); r["_Stato"] = "Da rendere"
                dfs_piano.append(r)
            if not df_scaduto.empty:
                s = df_scaduto.copy()
                s["_Stato"] = s["Vendute_Ultimi_30_Giorni"].apply(
                    lambda v: "Scaduto — in vetrina" if v >= rot_min_ui else "Scaduto — fermo"
                )
                dfs_piano.append(s)

            if dfs_piano:
                df_piano = pd.concat(dfs_piano, ignore_index=True)
                df_piano = df_piano[df_piano["Giacenza"] > 0].copy()

                # Metriche
                df_piano["_prezzo_costo"] = (
                    df_piano["Prezzo_Copertina"] - df_piano["Sconto_Libreria"]
                ).clip(lower=0)
                df_piano["_costo_opp"] = (
                    df_piano["_prezzo_costo"] * df_piano["Giacenza"]
                )
                df_piano["_sell_through"] = (
                    df_piano["Vendute_Ultimi_30_Giorni"] / df_piano["Giacenza"] * 100
                ).round(1)
                # Copertura in mesi: Giacenza / vendite mensili
                # Se vendite = 0 → copertura infinita (simbolo ∞)
                def _copertura(row):
                    if row["Vendute_Ultimi_30_Giorni"] <= 0:
                        return None
                    return round(row["Giacenza"] / row["Vendute_Ultimi_30_Giorni"], 1)
                df_piano["_copertura"] = df_piano.apply(_copertura, axis=1)

                # Riclassifica "fermo" con sell-through alto e giacenza bassa
                def _stato_finale(row):
                    if row["_Stato"] != "Scaduto — fermo":
                        return row["_Stato"]
                    if row["_sell_through"] >= 50 and row["Giacenza"] <= 3:
                        return "Scaduto — esaurimento"
                    return row["_Stato"]
                df_piano["_Stato"] = df_piano.apply(_stato_finale, axis=1)

                # Azione suggerita — formulazione quantitativa
                def _azione(row):
                    if row["_Stato"] == "Da rendere":
                        return (
                            f"Rendi {int(row['Giacenza'])} cop. "
                            f"→ recuperi {fmt_euro(row['_costo_opp'])}"
                        )
                    elif row["_Stato"] == "Scaduto — in vetrina":
                        return (
                            f"Tieni in vetrina "
                            f"({int(row['Vendute_Ultimi_30_Giorni'])} cop./mese)"
                        )
                    elif row["_Stato"] == "Scaduto — esaurimento":
                        return (
                            f"Valuta riordino — sell-through {row['_sell_through']:.0f}%, "
                            f"solo {int(row['Giacenza'])} cop. rimanenti"
                        )
                    else:
                        cop = row["_copertura"]
                        cop_s = f"{cop:.0f} mesi" if pd.notna(cop) else "∞"
                        return (
                            f"Promo o contatto distributore "
                            f"— {cop_s} di scorte, "
                            f"{fmt_euro(row['_costo_opp'])} immobilizzati"
                        )

                df_piano["Azione suggerita"] = df_piano.apply(_azione, axis=1)
                df_piano["Copertura scorte"] = df_piano["_copertura"].apply(
                    lambda x: f"{x:.0f} mesi" if pd.notna(x) else "∞"
                )
                df_piano["Sell-through"] = df_piano["_sell_through"].apply(
                    lambda x: f"{x:.1f}%"
                )
                df_piano["Cassa immobilizzata"] = df_piano["_costo_opp"].apply(fmt_euro)

                # Vs. benchmark AIE/ISTAT
                def _benchmark(row):
                    st_val  = row["_sell_through"]   # %/mese
                    cop_val = row["_copertura"]       # mesi (None = ∞)
                    flags = []
                    if st_val < BENCHMARK["sell_through_critico"]:
                        flags.append("❌ Sell-through critico")
                    elif st_val < BENCHMARK["sell_through_attenzione"]:
                        flags.append("⚠️ Sell-through basso")
                    else:
                        flags.append("✅ Sell-through OK")
                    if pd.notna(cop_val) and cop_val > BENCHMARK["copertura_critica"]:
                        flags.append(f"❌ Copertura {cop_val:.0f}m > 12m")
                    elif not pd.notna(cop_val):
                        flags.append("❌ Nessuna vendita")
                    return " · ".join(flags)

                df_piano["Vs. benchmark"] = df_piano.apply(_benchmark, axis=1)

                disp = (
                    df_piano
                    .sort_values("_costo_opp", ascending=False)
                    [["Titolo", "_Stato", "Giacenza",
                      "Copertura scorte", "Sell-through",
                      "Cassa immobilizzata", "Vs. benchmark", "Azione suggerita"]]
                    .rename(columns={"_Stato": "Stato"})
                    .reset_index(drop=True)
                )

                st.dataframe(disp, use_container_width=True, hide_index=True,
                             height=max(150, min(500, 45 + len(disp) * 35)))

                st.caption(
                    "**Vs. benchmark** — soglie settore: sell-through < 4%/mese = critico, "
                    "4–8%/mese = attenzione, copertura > 12 mesi = critico. "
                    "Fonte: AIE / ISTAT 2022 (dati pubblici aggregati mercato librario italiano)."
                )

                # Riepilogo numerico
                rec  = df_piano[df_piano["_Stato"] == "Da rendere"]["_costo_opp"].sum()
                imm  = df_piano[df_piano["_Stato"] == "Scaduto — fermo"]["_costo_opp"].sum()
                rc1, rc2 = st.columns(2)
                rc1.metric("Cassa recuperabile da rese", fmt_euro(rec))
                rc2.metric("Cassa immobilizzata in invenduto fermo", fmt_euro(imm))
                st.caption(
                    "La **cassa recuperabile** è il valore a costo dei libri ancora rendibili. "
                    "La **cassa immobilizzata** è il costo dei titoli fermi fuori finestra — "
                    "non recuperabile via resa, solo via vendita o promozione."
                )
            else:
                st.info("Nessun titolo con giacenza attiva da analizzare.")

        # ── Storico esportazioni ──────────────────────────────────────────────
        st.divider()
        with st.expander("🗂️ Storico esportazioni", expanded=False):
            _storico = load_storico()
            if not _storico:
                st.info("Nessuna esportazione registrata. "
                        "Lo storico si aggiorna automaticamente ogni volta che esporti "
                        "la lista da rendere o l'invenduto.")
            else:
                _LABELS = {
                    "resa":              "📤 Esportazione rese",
                    "analisi_invenduto": "📋 Esportazione invenduto",
                }
                _rows = []
                for _e in reversed(_storico):   # più recente prima
                    _rows.append({
                        "Data":           _e.get("data", "—"),
                        "Tipo":           _LABELS.get(_e.get("tipo", ""), _e.get("tipo", "—")),
                        "Titoli":         _e.get("n_titoli", 0),
                        "Copie":          _e.get("n_copie", 0),
                        "Valore stimato": fmt_euro(_e.get("valore_euro", 0.0)),
                    })
                st.dataframe(
                    pd.DataFrame(_rows),
                    use_container_width=True,
                    hide_index=True,
                    height=max(150, min(400, 45 + len(_rows) * 35)),
                )
                st.caption(
                    f"{len(_storico)} esportazioni registrate. "
                    "Il log è salvato in **storico_decisioni.json** nella stessa cartella dell'app."
                )
                # Scarica log completo come CSV
                _storico_df = pd.DataFrame([{
                    "Data":           _e.get("data", ""),
                    "Tipo":           _LABELS.get(_e.get("tipo", ""), _e.get("tipo", "")),
                    "N_Titoli":       _e.get("n_titoli", 0),
                    "N_Copie":        _e.get("n_copie", 0),
                    "Valore_Euro":    _e.get("valore_euro", 0.0),
                    "Titoli":         ", ".join(_e.get("titoli", [])),
                } for _e in _storico])
                st.download_button(
                    label="📥 Scarica storico completo (CSV)",
                    data=_storico_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"storico_decisioni_{DATA_SISTEMA.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )

    else:
        empty_state("", "Pronto per analizzare il magazzino",
                    "Carica un file CSV dalla barra laterale oppure clicca 'Carica demo' per provare con dati di esempio.")
        st.divider()
        section("CSV di esempio")
        _w = lambda n: (DATA_SISTEMA - timedelta(days=n)).strftime("%d/%m/%Y")
        sample_csv = (
            "Titolo,Autore,Editore,ISBN,Data_Fatturazione,Giacenza,Vendute_Ultimi_30_Giorni,Prezzo_Copertina,Sconto_Libreria\n"
            f"Il nome della rosa,Umberto Eco,Bompiani,9788845292613,{_w(30)},4,1,19.00,3.42\n"
            f"I promessi sposi,Alessandro Manzoni,Mondadori,9788811360353,{_w(45)},5,5,12.00,2.16\n"
            f"Le cosmicomiche,Italo Calvino,Einaudi,9788804668367,{_w(60)},1,6,13.00,2.34\n"
            f"Il pendolo di Foucault,Umberto Eco,Bompiani,9788845232152,{_w(90)},3,7,18.00,3.24\n"
            f"La variante di Lüneburg,Paolo Maurensig,Adelphi,9788845285745,{_w(110)},5,3,13.00,2.34\n"
            f"Sostiene Pereira,Antonio Tabucchi,Feltrinelli,9788807883866,{_w(130)},2,4,13.00,2.34\n"
            f"La coscienza di Zeno,Italo Svevo,Einaudi,9788804668416,{_w(158)},3,4,13.00,2.34\n"
            f"Lessico famigliare,Natalia Ginzburg,Einaudi,9788806220495,{_w(162)},2,3,12.00,2.16\n"
            f"Il giorno della civetta,Leonardo Sciascia,Adelphi,9788845265716,{_w(170)},3,5,12.00,2.16\n"
            f"Cent'anni di solitudine,Gabriel García Márquez,Mondadori,9788806226480,{_w(155)},6,0,14.00,2.52\n"
            f"Pinocchio,Carlo Collodi,Einaudi,9788811810000,{_w(160)},7,0,9.90,1.78\n"
            f"Il gattopardo,Giuseppe Tomasi di Lampedusa,Feltrinelli,9788845274893,{_w(165)},4,1,14.00,2.52\n"
            f"Se questo è un uomo,Primo Levi,Einaudi,9788806219390,{_w(168)},2,1,13.50,2.43\n"
            f"Dissolvenze,Donatella Di Pietrantonio,Einaudi,9788806258001,{_w(172)},8,2,17.00,3.06\n"
            f"L'amica geniale,Elena Ferrante,e/o,9788866325772,{_w(178)},6,1,19.00,3.42\n"
            f"Storia di chi fugge,Elena Ferrante,e/o,9788866325789,{_w(180)},4,0,19.00,3.42\n"
            f"La luna e i falò,Cesare Pavese,Einaudi,9788806220500,{_w(220)},3,0,12.50,2.25\n"
            f"Gomorra,Roberto Saviano,Mondadori,9788817003735,{_w(240)},2,1,14.00,2.52\n"
            f"Ferite a morte,Serena Dandini,Rizzoli,9788842821345,{_w(260)},5,0,14.50,2.61\n"
            f"Baol,Stefano Benni,Feltrinelli,9788807880018,{_w(300)},3,0,11.00,1.98\n"
        )
        st.download_button(
            label="Scarica CSV di esempio",
            data=sample_csv,
            file_name="Gestionale_Magazzino.csv",
            mime="text/csv"
        )

# ===========================================================================
# CALCOLATORE MARGINE ORDINE
# ===========================================================================
elif strumento == "Calcolatore margine ordine":
    page_header("Calcolatore margine ordine",
                "Simula il margine reale prima di fare un ordine. I valori persistono tra una navigazione e l'altra.")

    col_form, col_results = st.columns([1, 1.1], gap="large")

    with col_form:
        section("Parametri ordine")
        st.text_input("Titolo (opzionale)", placeholder="es. Il nome della rosa", key="calc_titolo")

        help_prezzo = create_help_tooltip(
            "Prezzo di copertina",
            "Prezzo al pubblico stampato sulla copertina del libro.",
            "15,99 € (narrativa), 24,90 € (saggistica), 12,50 € (tascabile)",
            "Dipende dal genere — verificare il prezzo sulla copertina"
        )
        prezzo   = st.number_input("Prezzo di copertina (€)", min_value=0.01, value=st.session_state["calc_prezzo"],
                                   step=0.50, format="%.2f", key="calc_prezzo", help=help_prezzo)

        help_sconto = create_help_tooltip(
            "Sconto editore",
            "Percentuale di sconto applicata dall'editore sul prezzo di copertina.",
            "30% (sconto standard), 35% (titoli bestseller), 40% (ordini grandi)",
            "30-35% — sconto medio per librerie indipendenti"
        )
        sconto   = st.slider("Sconto editore (%)", min_value=0, max_value=60,
                             value=st.session_state["calc_sconto"], key="calc_sconto", help=help_sconto)

        help_quantita = create_help_tooltip(
            "Copie ordinate",
            "Numero di copie che intendi ordinare in questo ordine.",
            "5 copie (titolo nuovo), 15 copie (bestseller), 50 copie (ordine grande)",
            "Dipende dalla rotazione prevista — considerare lo spazio disponibile"
        )
        quantita = st.number_input("Copie ordinate", min_value=1, value=st.session_state["calc_quantita"],
                                   step=1, key="calc_quantita", help=help_quantita)

        if st.session_state["calc_resa_pct"] > 80:
            st.session_state["calc_resa_pct"] = 80

        help_resa = create_help_tooltip(
            "Resa stimata",
            "Percentuale di copie che prevedi di rendere al distributore (non vendute).",
            "10% (titolo popolare), 25% (titolo medio), 50% (esperimento rischio)",
            "20-30% — media del settore per titoli nuovi"
        )
        resa_pct = st.slider("Resa stimata (%)", min_value=0, max_value=80,
                             value=st.session_state["calc_resa_pct"], step=5, key="calc_resa_pct", help=help_resa)

        st.divider()
        section("Costi fissi mensili")
        st.caption("Inserisci i costi fissi per calcolare il break-even reale della libreria.")

        help_affitto = create_help_tooltip(
            "Affitto",
            "Canone mensile di affitto dei locali della libreria.",
            "500 € (piccolo spazio), 1500 € (spazio medio), 3000 € (grande negozio)",
            "Inserisci il valore reale per la tua libreria"
        )
        affitto   = st.number_input("Affitto (€/mese)", min_value=0.0,
                                    value=st.session_state["calc_affitto"],   step=50.0,  format="%.0f", key="calc_affitto", help=help_affitto)

        help_utenze = create_help_tooltip(
            "Utenze",
            "Costi mensili di elettricità, gas, acqua e internet.",
            "100 € (piccolo), 300 € (medio), 500 € (grande con riscaldamento)",
            "Calcola dalla media annuale"
        )
        utenze    = st.number_input("Utenze (€/mese)", min_value=0.0,
                                    value=st.session_state["calc_utenze"],    step=10.0,  format="%.0f", key="calc_utenze", help=help_utenze)

        help_personale = create_help_tooltip(
            "Personale",
            "Costo fisso mensile per retribuzione del personale (stipendi netti).",
            "1000 € (proprietario part-time), 2500 € (un dipendente), 5000 € (due dipendenti)",
            "Non includere contributi — solo il netto"
        )
        personale = st.number_input("Personale (€/mese)", min_value=0.0,
                                    value=st.session_state["calc_personale"], step=50.0,  format="%.0f", key="calc_personale", help=help_personale)

        help_altri = create_help_tooltip(
            "Altri costi",
            "Costi fissi rimanenti: assicurazioni, manutenzione, forniture, tasse, software.",
            "200 € (base minima), 500 € (copertura completa)",
            "Sommare: assicurazione (~50€) + manutenzione (~30€) + forniture (~50€) + altri"
        )
        altri     = st.number_input("Altri costi fissi (€/mese)", min_value=0.0,
                                    value=st.session_state["calc_altri"],     step=10.0,  format="%.0f", key="calc_altri", help=help_altri)
        costi_fissi_totali = affitto + utenze + personale + altri

    with col_results:
        section("Risultati")

        costo_u           = prezzo * (1 - sconto / 100)
        margine_u         = prezzo - costo_u
        margine_pct_lordo = (margine_u / prezzo) * 100
        copie_vend        = quantita * (1 - resa_pct / 100)
        copie_resa        = quantita * (resa_pct / 100)
        valore_ord        = costo_u * quantita
        ricavo            = prezzo * copie_vend
        margine_netto     = ricavo - costo_u * copie_vend
        margine_pct_netto = (margine_netto / ricavo * 100) if ricavo > 0 else 0
        valore_rischio    = costo_u * copie_resa

        # Break-even: copie da vendere per coprire il costo netto (solo copie tenute, resa rimborsata)
        net_cost_order     = costo_u * copie_vend
        be_ordine_copie    = net_cost_order / prezzo if prezzo > 0 else float("inf")
        be_pct_vendibili   = (be_ordine_copie / copie_vend * 100) if copie_vend > 0 else float("inf")
        be_ordine_pct      = (be_ordine_copie / quantita) * 100
        ordini_per_coprire = (costi_fissi_totali / margine_netto) if margine_netto > 0 else float("inf")

        tone_m  = "positive" if margine_pct_netto >= 25 else ("negative" if margine_pct_netto < 15 else "warning")
        tone_be = "positive" if be_pct_vendibili <= 70 else ("warning" if be_pct_vendibili <= 90 else "negative")

        r1, r2 = st.columns(2)
        with r1: metric_card("Margine netto ordine", fmt_euro(margine_netto),
                              "positive" if margine_netto >= 0 else "negative")
        with r2: metric_card("Margine % netto", f"{margine_pct_netto:.1f}%", tone_m)

        metric_card(
            "Break-even ordine", f"{be_ordine_copie:.1f} copie", tone_be,
            f"{be_pct_vendibili:.0f}% delle {int(copie_vend)} vendibili · "
            "quante copie devi vendere per coprire il costo netto (dopo resa)"
        )

        if margine_netto > 0:
            tone_reale = "positive" if ordini_per_coprire <= 20 else ("warning" if ordini_per_coprire <= 50 else "negative")
            metric_card(
                "Ordini mensili per coprire i costi fissi",
                f"{ordini_per_coprire:.0f}" if ordini_per_coprire < 9999 else "∞",
                tone_reale,
                f"con costi fissi di {fmt_euro(costi_fissi_totali)}/mese"
            )
        else:
            metric_card("Ordini mensili per coprire i costi fissi", "∞", "negative",
                        "questo ordine non genera margine")

        st.divider()
        df_riepilogo = pd.DataFrame({
            "Voce": [
                "Costo unitario", "Margine unitario lordo", "Margine % lordo",
                "Copie attese vendute", "Copie attese resa",
                "Cassa impegnata", "Valore a rischio", "Ricavo atteso",
                "Costi fissi mensili",
            ],
            "Valore": [
                fmt_euro(costo_u), fmt_euro(margine_u), f"{margine_pct_lordo:.1f}%",
                f"{copie_vend:.1f}", f"{copie_resa:.1f}",
                fmt_euro(valore_ord), fmt_euro(valore_rischio), fmt_euro(ricavo),
                fmt_euro(costi_fissi_totali),
            ],
        })
        st.dataframe(df_riepilogo, use_container_width=True, hide_index=True, height=350)

        titolo_label = st.session_state.get("calc_titolo", "").strip() or "ordine"
        st.download_button(
            label="📥 Esporta simulazione (CSV)",
            data=df_riepilogo.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"margine_{titolo_label[:30].replace(' ','_')}_{DATA_SISTEMA.strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

        if be_ordine_pct > (100 - resa_pct):
            st.error("Con la resa stimata non raggiungi il break-even sull'ordine. "
                     "Riduci la quantità o rinegozia lo sconto.")
        elif margine_pct_netto < 20:
            st.warning("Margine sotto il 20% — valuta se l'ordine è strategicamente giustificato.")
        else:
            st.success("L'ordine è sostenibile.")

        st.divider()

        # ── Calcolo inverso: da margine target a sconto minimo ────────────
        with st.expander("🎯 Calcolo inverso — da margine target a sconto minimo"):
            st.caption(
                "Parti dal margine che vuoi ottenere e scopri lo sconto minimo da negoziare con l'editore. "
                "Utile per trattative con distributori o per valutare offerte non standard."
            )
            margine_target = st.slider(
                "Margine target (%)", min_value=10, max_value=50,
                value=st.session_state["calc_inv_target"], step=1, key="calc_inv_target"
            )
            # Identità matematica: margine_pct_netto = sconto_editore
            # (il margine % coincide sempre con lo sconto %, a parità di resa)
            sconto_min   = margine_target
            costo_max    = prezzo * (1 - sconto_min / 100)
            delta        = sconto - margine_target   # sconto attuale vs target

            ci1, ci2 = st.columns(2)
            with ci1:
                metric_card(
                    "Sconto minimo da negoziare",
                    f"{sconto_min}%",
                    "positive" if sconto >= sconto_min else "negative",
                    f"Sconto attuale: {sconto}% → delta {'+' if delta >= 0 else ''}{delta}%"
                )
            with ci2:
                metric_card(
                    "Prezzo di costo massimo accettabile",
                    fmt_euro(costo_max),
                    "positive" if costo_u <= costo_max else "negative",
                    f"Costo attuale: {fmt_euro(costo_u)}/copia"
                )

            if sconto < sconto_min:
                st.error(
                    f"Con lo sconto attuale ({sconto}%) non raggiungi il margine target ({margine_target}%). "
                    f"Devi negoziare almeno **{sconto_min - sconto}% in più** con l'editore."
                )
            else:
                st.success(
                    f"Lo sconto attuale ({sconto}%) supera il target ({margine_target}%) "
                    f"di **{delta}%**."
                )

# ===========================================================================
# GESTIONE USATO
# ===========================================================================
elif strumento == "Gestione usato":
    page_header("Gestione usato",
                "Valuta i libri usati in entrata con percentuali modificabili per ogni titolo.")

    if st.session_state.pop("_reset_usato_form", False):
        st.session_state["u_titolo"]     = ""
        st.session_state["u_autore"]     = ""
        st.session_state["u_isbn_input"] = ""
        st.session_state["u_prezzo"]     = 0.00

    if st.session_state.get("_usato_added"):
        st.toast(f"✓ «{st.session_state['_usato_added']}» aggiunto all'inventario", icon="📚")
        st.session_state["_usato_added"] = ""

    col_form, col_inv = st.columns([1, 1.4], gap="large")

    with col_form:
        section("Valuta un libro")

        # ── ISBN Lookup ──────────────────────────────────────────────────
        st.caption("Compila automaticamente da ISBN (opzionale)")
        _ic1, _ic2 = st.columns([3, 1])
        with _ic1:
            isbn_val = st.text_input(
                "ISBN", placeholder="es. 9788806219390",
                key="u_isbn_input", label_visibility="collapsed"
            )
        with _ic2:
            isbn_cerca = st.button("🔍 Cerca", use_container_width=True, key="btn_isbn")

        if isbn_cerca:
            if not isbn_val.strip():
                st.warning("Inserisci un ISBN.")
            else:
                with st.spinner("Ricerca in OpenLibrary…"):
                    res = isbn_lookup(isbn_val.strip())
                if "error" in res:
                    st.error(res["error"])
                else:
                    if res.get("titolo"):
                        st.session_state["u_titolo"] = res["titolo"]
                    if res.get("autore"):
                        st.session_state["u_autore"] = res["autore"]
                    # Prezzo non disponibile via API: ripristina il default
                    st.session_state["u_prezzo"] = 14.00
                    st.session_state["_isbn_price_missing"] = True
                    st.rerun()

        st.divider()

        titolo_u = st.text_input("Titolo",  key="u_titolo", placeholder="es. Cent'anni di solitudine")
        autore_u = st.text_input("Autore",  key="u_autore", placeholder="es. Gabriel García Márquez")
        prezzo_u = st.number_input("Prezzo di copertina (€)", min_value=0.00,
                                   step=0.50, format="%.2f", key="u_prezzo")
        if st.session_state.pop("_isbn_price_missing", False):
            st.caption("⚠️ Prezzo non disponibile via ISBN — verifica e inserisci manualmente.")
        cond_u   = st.radio("Condizione", ["Ottimo", "Buono", "Accettabile"],
                             horizontal=True, key="u_cond")
        modal_u  = st.radio("Acquisizione", ["Conto vendita", "Acquisto diretto"],
                             horizontal=True, key="u_modal")

        st.divider()
        section("Percentuali di valutazione")
        st.caption("Modificale per questo titolo in base alla domanda reale che vedi sul mercato.")

        default_vend = {"Ottimo": 60, "Buono": 45, "Accettabile": 30}
        default_acq  = {"Ottimo": 25, "Buono": 18, "Accettabile": 10}

        pct_vend = st.slider(
            f"Prezzo di vendita — {cond_u} (% del copertina)",
            min_value=10, max_value=90,
            value=default_vend[cond_u], step=5, key=f"pct_vend_{cond_u}"
        )
        if modal_u == "Acquisto diretto":
            pct_acq = st.slider(
                f"Offerta acquisto — {cond_u} (% del copertina)",
                min_value=5, max_value=60,
                value=default_acq[cond_u], step=5, key=f"pct_acq_{cond_u}"
            )

        st.divider()
        prezzo_vend = prezzo_u * (pct_vend / 100)

        if modal_u == "Conto vendita":
            quota_lib    = prezzo_vend * USATO_CONTO_VENDITA
            quota_client = prezzo_vend * (1 - USATO_CONTO_VENDITA)
            quota_num    = quota_lib
            metric_card("Prezzo di vendita",              fmt_euro(prezzo_vend), "neutral",   f"{pct_vend}% del copertina")
            metric_card(f"Tua quota ({int(USATO_CONTO_VENDITA*100)}%)",          fmt_euro(quota_lib),    "positive")
            metric_card(f"Quota lettore ({int((1-USATO_CONTO_VENDITA)*100)}%)",   fmt_euro(quota_client), "neutral")
        else:
            offerta   = prezzo_u * (pct_acq / 100)
            margine_p = prezzo_vend - offerta
            quota_num = margine_p
            metric_card("Prezzo di vendita",        fmt_euro(prezzo_vend), "neutral",   f"{pct_vend}% del copertina")
            metric_card("Offerta acquisto",         fmt_euro(offerta),     "negative",  f"{pct_acq}% del copertina")
            metric_card("Margine lordo potenziale", fmt_euro(margine_p),   "positive",  "al lordo di tempo e costi di gestione")

        if titolo_u.strip():
            q = quote_plus(f"{titolo_u.strip()} {autore_u.strip()}".strip())
            st.markdown(
                f'<div class="market-label">Verifica prezzi di mercato</div>'
                f'<div class="market-links">'
                f'<a href="https://www.maremagnum.com/libri-antichi/ricerca?q={q}" target="_blank">Maremagnum</a>'
                f'<a href="https://www.ebay.it/sch/i.html?_nkw={q}&LH_ItemCondition=3000" target="_blank">eBay usato</a>'
                f'<a href="https://www.abebooks.com/servlet/SearchResults?kn={q}&sts=t" target="_blank">AbeBooks</a>'
                f'</div>', unsafe_allow_html=True
            )

        st.divider()
        if st.button("Aggiungi all'inventario", type="primary", use_container_width=True):
            if not titolo_u.strip():
                st.warning("Inserisci almeno il titolo del libro.")
            elif prezzo_u <= 0:
                st.warning("Inserisci il prezzo di copertina prima di aggiungere.")
            else:
                st.session_state["inventario_usato"].append({
                    "Titolo":       titolo_u.strip(),
                    "Autore":       autore_u.strip() or "—",
                    "Condizione":   cond_u,
                    "Modalità":     modal_u,
                    "Prezzo cov.":  fmt_euro(prezzo_u),
                    "% vendita":    f"{pct_vend}%",
                    "Prezzo vend.": fmt_euro(prezzo_vend),
                    "Tua quota":    fmt_euro(quota_num),
                    "_prezzo_num":  prezzo_vend,
                    "_quota_num":   quota_num,
                })
                save_inventory(st.session_state["inventario_usato"])
                st.session_state["_usato_added"]      = titolo_u.strip()
                st.session_state["_reset_usato_form"] = True
                st.rerun()

    with col_inv:
        inv = st.session_state["inventario_usato"]
        section("Inventario")
        if not inv:
            empty_state("📚", "Inventario vuoto",
                        "Valuta un libro nel pannello a sinistra e aggiungilo qui.")
        else:
            totale_vend  = sum(i["_prezzo_num"] for i in inv)
            totale_quota = sum(i["_quota_num"]  for i in inv)
            n_cv = sum(1 for i in inv if i["Modalità"] == "Conto vendita")
            n_ad = sum(1 for i in inv if i["Modalità"] == "Acquisto diretto")

            m1, m2, m3 = st.columns(3)
            with m1: metric_card("Libri",           str(len(inv)),         "neutral")
            with m2: metric_card("Valore totale",    fmt_euro(totale_vend), "neutral")
            with m3: metric_card("Tua quota totale", fmt_euro(totale_quota),"positive")

            display_keys = ["Titolo","Autore","Condizione","Modalità",
                            "Prezzo cov.","% vendita","Prezzo vend.","Tua quota"]
            df_inv = pd.DataFrame([{k: i[k] for k in display_keys} for i in inv])
            st.dataframe(df_inv, use_container_width=True,
                         height=max(150, min(400, 45 + len(df_inv) * 35)), hide_index=True)

            # ── Azioni ──────────────────────────────────────────────────────
            c_exp, c_del = st.columns([2, 1])
            with c_exp:
                st.download_button("📥 Esporta CSV", df_inv.to_csv(index=False).encode("utf-8-sig"),
                                   "inventario_usato.csv", "text/csv", use_container_width=True)
            with c_del:
                if not st.session_state["svuota_confirm"]:
                    if st.button("Svuota tutto", use_container_width=True):
                        st.session_state["svuota_confirm"] = True
                        st.rerun()
                else:
                    n = len(inv)
                    st.warning(f"Eliminare {n} {'libro' if n == 1 else 'libri'}?")
                    cc1, cc2 = st.columns(2)
                    if cc1.button("Sì", type="primary", use_container_width=True):
                        st.session_state["inventario_usato"] = []
                        st.session_state["svuota_confirm"]   = False
                        save_inventory([])
                        st.rerun()
                    if cc2.button("No", use_container_width=True):
                        st.session_state["svuota_confirm"] = False
                        st.rerun()

            # ── Rimozione singolo libro ──────────────────────────────────
            with st.expander("🗑 Rimuovi un libro dall'inventario"):
                options = [
                    f"{i+1}. {item['Titolo']} — {item['Autore']} ({item['Condizione']}, {item['Modalità']})"
                    for i, item in enumerate(inv)
                ]
                to_remove = st.selectbox("Seleziona il libro da rimuovere", options, key="rm_sel",
                                         label_visibility="collapsed")
                if st.button("Rimuovi selezionato", use_container_width=True):
                    idx = options.index(to_remove)
                    st.session_state["inventario_usato"].pop(idx)
                    save_inventory(st.session_state["inventario_usato"])
                    st.rerun()

            # ── Etichette prezzi ─────────────────────────────────────────
            with st.expander("🏷 Etichette prezzi — per etichettare i libri in vetrina"):
                st.caption("Anteprima delle etichette. Esporta come TXT per stamparle.")

                _cond_col = {"Ottimo": "#2D6A4F", "Buono": "#7A5C00", "Accettabile": "#8B4049"}
                labels_html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem">'
                for item in inv:
                    col_c = _cond_col.get(item["Condizione"], "#888")
                    labels_html += f"""
                    <div style="border:1px solid #E0D8CF;border-radius:6px;padding:.65rem .9rem;
                                background:#fff;display:flex;justify-content:space-between;
                                align-items:center;gap:.5rem">
                        <div style="min-width:0">
                            <div style="font-family:'EB Garamond',serif;font-size:.92rem;
                                        font-weight:600;white-space:nowrap;overflow:hidden;
                                        text-overflow:ellipsis">{item['Titolo']}</div>
                            <div style="font-size:.72rem;color:#888;white-space:nowrap;
                                        overflow:hidden;text-overflow:ellipsis">{item['Autore']}</div>
                        </div>
                        <div style="text-align:right;flex-shrink:0">
                            <div style="font-size:1rem;font-weight:700">{item['Prezzo vend.']}</div>
                            <div style="font-size:.62rem;font-weight:600;color:{col_c};
                                        text-transform:uppercase;letter-spacing:.07em">{item['Condizione']}</div>
                        </div>
                    </div>"""
                labels_html += "</div>"
                st.markdown(labels_html, unsafe_allow_html=True)

                st.divider()
                # Export TXT
                txt_lines = [f"ETICHETTE PREZZI — {DATA_SISTEMA.strftime('%d/%m/%Y')}", "=" * 40, ""]
                for item in inv:
                    txt_lines += [
                        f"{item['Titolo']}",
                        f"{item['Autore']}",
                        f"{item['Prezzo vend.']}  |  {item['Condizione']}  |  {item['Modalità']}",
                        "",
                    ]
                st.download_button(
                    "📥 Scarica etichette (TXT)",
                    data="\n".join(txt_lines).encode("utf-8"),
                    file_name=f"etichette_usato_{DATA_SISTEMA.strftime('%Y%m%d')}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

            st.divider()
            st.caption(
                f"Conto vendita: {n_cv} · Acquisto diretto: {n_ad} · "
                f"💾 salvato in {INVENTORY_FILE.name}"
            )

# ===========================================================================
# ANALISI STORICA
# ===========================================================================
elif strumento == "Analisi storica":

    # ── Economist-style layout helper ────────────────────────────────────────
    def _econ(fig, *, title="", subtitle="", ysuffix="", yprefix="", x0=False, src=""):
        """Applica lo stile Economist a un oggetto Plotly Figure."""
        title_html = (f"<b>{title}</b>" if title else "") + (
            f"<br><span style='font-size:11px;color:#5C5852;font-weight:400'>{subtitle}</span>"
            if subtitle else ""
        )
        fig.update_layout(
            paper_bgcolor="white", plot_bgcolor="white",
            font=dict(family="Inter,'Helvetica Neue',sans-serif", color="#16130F", size=12),
            title=dict(
                text=title_html, x=0, xanchor="left",
                font=dict(size=15, color="#16130F", family="Inter,'Helvetica Neue',sans-serif"),
                pad=dict(b=8, l=0),
            ),
            margin=dict(l=8, r=48, t=84 if title else 24, b=76 if src else 52),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                font=dict(size=11, color="#5C5852"),
                bgcolor="rgba(0,0,0,0)", borderwidth=0, itemsizing="constant",
            ),
            xaxis=dict(
                showgrid=False, showline=True, linecolor="#D5D0CB", linewidth=1,
                tickfont=dict(size=11, color="#5C5852"),
                ticks="outside", ticklen=3, tickcolor="#D5D0CB", title=None,
            ),
            yaxis=dict(
                showgrid=True, gridcolor="#F0EBE5", gridwidth=1,
                showline=False, tickfont=dict(size=11, color="#5C5852"),
                ticksuffix=ysuffix, tickprefix=yprefix, title=None,
                zeroline=x0, zerolinecolor="#C0BBB5", zerolinewidth=1.5,
            ),
            hoverlabel=dict(
                bgcolor="#16130F", font_color="#F5F1EC",
                font_size=11, bordercolor="#16130F",
            ),
            hovermode="x unified",
            # Zoom e pan disabilitati — hover tooltip preservato.
            # L'utente non può bloccarsi in uno stato di zoom senza via d'uscita.
            dragmode=False,
        )
        if src:
            fig.add_annotation(
                text=f"<i>{src}</i>", xref="paper", yref="paper",
                x=0, y=-0.20, showarrow=False,
                font=dict(size=9, color="#9B9590"), xanchor="left",
            )
        return fig

    # ── Page header ──────────────────────────────────────────────────────────
    page_header(
        "Analisi storica",
        "Confronta più snapshot del gestionale per leggere l'evoluzione del magazzino nel tempo.",
    )

    # Ordina per nome file (alfabetico, case-insensitive) — convenzione
    # gen2024/apr2024/lug2024 garantisce l'ordine cronologico automaticamente.
    files_storico = sorted(storico_files_sb, key=lambda f: f.name.lower())

    # ── Guard: file non caricati ─────────────────────────────────────────────
    if not files_storico:
        empty_state(
            "📈", "Nessuno snapshot caricato",
            "Carica 2 o più file CSV dalla barra laterale — stesso formato del gestionale. "
            "Ogni file è una fotografia dello stock in un momento diverso.",
        )
        st.divider()
        st.caption(
            "**Come preparare gli snapshot:** esporta il gestionale ogni mese o trimestre. "
            "Usa lo stesso formato CSV del Radar Salva-Cassa — nessuna colonna aggiuntiva richiesta."
        )

    elif len(files_storico) < 2:
        st.warning(
            "Carica almeno **2 snapshot** per avviare l'analisi comparativa. "
            "Più snapshot carichi, più l'analisi è significativa."
        )

    else:
        # ── Assegnazione etichette periodo ────────────────────────────────────
        section("Configura i periodi")
        st.markdown(
            '<div style="color: #5C5852; font-size: 13px; line-height: 1.5; margin: -15px 0 15px 0;">'
            'I file sono ordinati <strong>alfabeticamente per nome</strong> — '
            'usa nomi come <code>gen2024.csv</code>, <code>apr2024.csv</code>, <code>lug2024.csv</code> '
            'per preservare l\'ordine cronologico senza intervento manuale. '
            'Modifica le etichette se vuoi nomi più leggibili.'
            '</div>',
            unsafe_allow_html=True
        )
        n_files   = len(files_storico)
        cols_lab  = st.columns(min(n_files, 4))
        file_labels = {}
        for i, f in enumerate(files_storico):
            default_lbl = (
                f.name.replace(".csv", "").replace("_", " ").replace("-", " ")
            )
            with cols_lab[i % 4]:
                lbl = st.text_input(
                    f"File {i + 1}",
                    value=st.session_state.get(f"_slbl_{i}", default_lbl),
                    key=f"_slbl_{i}",
                    placeholder=f"es. «Gen {date.today().year}»",
                )
                file_labels[i] = lbl.strip() or f"Snapshot {i + 1}"

        # ── Caricamento e validazione snapshot ───────────────────────────────
        snapshots   = []   # [(label, df), ...]
        load_errors = []

        with st.spinner(f"📂 Caricamento e validazione {len(files_storico)} snapshot…"):
            for i, f in enumerate(files_storico):
                raw = f.read()
                try:
                    df_s = load_csv(raw)
                    df_s = normalize_columns(df_s)
                    missing = SCHEMA_MAGAZZINO - set(df_s.columns)
                    if missing:
                        load_errors.append(
                            f"**{f.name}** — colonne mancanti: "
                            f"`{'`, `'.join(sorted(missing))}`"
                        )
                        continue
                    for col in ["Giacenza", "Vendute_Ultimi_30_Giorni",
                                "Prezzo_Copertina", "Sconto_Libreria"]:
                        df_s[col] = parse_numeric(df_s[col])
                    df_s = df_s[df_s["Giacenza"] >= 0].copy()
                    snapshots.append((file_labels[i], df_s))
                except Exception as exc:
                    load_errors.append(f"**{f.name}** — errore di caricamento: {exc}")

        for err in load_errors:
            st.error(err)

        if len(snapshots) < 2:
            if not load_errors:
                st.warning("Servono almeno 2 snapshot validi per procedere.")

        else:
            periodo_labels = [lbl for lbl, _ in snapshots]
            n_snaps        = len(snapshots)

            # ── Calcolo aggregati per snapshot ───────────────────────────────
            agg_rows = []
            for lbl, df_s in snapshots:
                giac  = df_s["Giacenza"].sum()
                vend  = df_s["Vendute_Ultimi_30_Giorni"].sum()
                costo = (df_s["Prezzo_Copertina"] - df_s["Sconto_Libreria"]).clip(lower=0)
                val_mag = (costo * df_s["Giacenza"]).sum()
                st_med  = round(vend / giac * 100, 2) if giac > 0 else 0.0
                agg_rows.append({
                    "Periodo":    lbl,
                    "Valore_Mag": val_mag,
                    "SellThrough": st_med,
                    "N_Titoli":   len(df_s),
                    "Giacenza":   giac,
                    "Vendute":    vend,
                })
            df_agg = pd.DataFrame(agg_rows)

            # ── DataFrame combinato ──────────────────────────────────────────
            dfs_tagged = []
            for idx, (lbl, df_s) in enumerate(snapshots):
                d = df_s.copy()
                d["_Periodo"] = lbl
                d["_PIdx"]    = idx
                dfs_tagged.append(d)
            df_all = pd.concat(dfs_tagged, ignore_index=True)
            df_all["_Costo"]  = (
                df_all["Prezzo_Copertina"] - df_all["Sconto_Libreria"]
            ).clip(lower=0)
            df_all["_ValMag"] = df_all["_Costo"] * df_all["Giacenza"]
            # Sell-through per riga — np.where per gestire Giacenza == 0 senza divisione per zero
            df_all["_ST"] = np.where(
                df_all["Giacenza"] > 0,
                df_all["Vendute_Ultimi_30_Giorni"] / df_all["Giacenza"] * 100,
                np.nan,
            )
            df_all["_Fermo"] = (
                (df_all["Giacenza"] > 0) &
                (df_all["_ST"] < BENCHMARK["sell_through_critico"])
            )

            # ── Sell-through per editore ─────────────────────────────────────
            df_st_ed    = None
            top_editori = []
            if "Editore" in df_all.columns:
                grp_ed = (
                    df_all
                    .groupby(["_PIdx", "_Periodo", "Editore"], as_index=False)
                    .agg(
                        Giacenza=("Giacenza", "sum"),
                        Vendute=("Vendute_Ultimi_30_Giorni", "sum"),
                    )
                )
                grp_ed["SellThrough"] = np.where(
                    grp_ed["Giacenza"] > 0,
                    grp_ed["Vendute"] / grp_ed["Giacenza"] * 100,
                    np.nan,
                )
                grp_ed = grp_ed.sort_values("_PIdx")
                # Top 6 per volume vendite totale — più rappresentativi
                top_editori = (
                    grp_ed.groupby("Editore")["Vendute"].sum()
                    .nlargest(6).index.tolist()
                )
                df_st_ed = grp_ed[grp_ed["Editore"].isin(top_editori)].copy()

            # ── Titoli cronicamente fermi ────────────────────────────────────
            # Metrica: (% snapshot in cui il titolo è fermo) × (valore medio immobilizzato)
            # Un titolo "conta" solo se appare in ≥ 2 snapshot con giacenza > 0.
            extra_first = {
                c: "first" for c in ["Autore", "Editore"] if c in df_all.columns
            }
            tit_agg = {
                "_Periodo": "nunique",
                "_Fermo":   "sum",
                "Giacenza": "mean",
                "_ST":      "mean",
                "_ValMag":  "mean",
                **extra_first,
            }
            tit_stats = (
                df_all[df_all["Giacenza"] > 0]
                .groupby("Titolo")
                .agg(tit_agg)
                .rename(columns={
                    "_Periodo": "N_Rilev",
                    "_Fermo":   "N_Fermo",
                    "Giacenza": "Giacenza_Media",
                    "_ST":      "ST_Medio",
                    "_ValMag":  "ValMag_Medio",
                })
                .reset_index()
            )
            tit_stats = tit_stats[tit_stats["N_Rilev"] >= 2].copy()
            tit_stats["Pct_Fermo"]     = tit_stats["N_Fermo"] / tit_stats["N_Rilev"]
            tit_stats["Score_Rischio"] = tit_stats["Pct_Fermo"] * tit_stats["ValMag_Medio"]
            tit_fermi = (
                tit_stats[tit_stats["Pct_Fermo"] >= 0.5]
                .sort_values("Score_Rischio", ascending=False)
                .head(15)
            )

            # ── Delta sell-through editori (prima vs ultima) ─────────────────
            df_delta_ed = None
            if df_st_ed is not None and n_snaps >= 2:
                st_prima  = (
                    df_st_ed[df_st_ed["_PIdx"] == 0]
                    .set_index("Editore")["SellThrough"]
                )
                st_ultima = (
                    df_st_ed[df_st_ed["_PIdx"] == n_snaps - 1]
                    .set_index("Editore")["SellThrough"]
                )
                comuni = st_prima.index.intersection(st_ultima.index)
                if len(comuni) > 0:
                    df_delta_ed = pd.DataFrame({
                        "Editore":    comuni,
                        "ST_Prima":   st_prima[comuni].values,
                        "ST_Ultima":  st_ultima[comuni].values,
                        "Delta":      (st_ultima[comuni] - st_prima[comuni]).values,
                    }).sort_values("Delta")

            # ── Panoramica ────────────────────────────────────────────────────
            st.divider()
            section("Panoramica")

            val_prima      = df_agg.iloc[0]["Valore_Mag"]
            val_ultima     = df_agg.iloc[-1]["Valore_Mag"]
            delta_val      = val_ultima - val_prima
            delta_val_pct  = (delta_val / val_prima * 100) if val_prima > 0 else 0.0
            st_prima_val   = df_agg.iloc[0]["SellThrough"]
            st_ultima_val  = df_agg.iloc[-1]["SellThrough"]
            delta_st_val   = st_ultima_val - st_prima_val
            n_fermi_cronici = len(tit_fermi)

            _p1, _p2, _p3, _p4 = st.columns(4)
            with _p1:
                metric_card(
                    "Snapshot analizzati", str(n_snaps), "neutral",
                    f"{periodo_labels[0]} → {periodo_labels[-1]}",
                )
            with _p2:
                # Valore crescente = accumulo invenduto = negativo per la salute della libreria
                tone_vm = (
                    "negative" if delta_val_pct > 5
                    else "positive" if delta_val_pct < -5
                    else "neutral"
                )
                note_vm = (
                    "↑ accumulo scorte" if delta_val_pct > 5
                    else "↓ riduzione scorte" if delta_val_pct < -5
                    else "→ stabile"
                ) + f"  ({'+' if delta_val >= 0 else ''}{delta_val_pct:.1f}%)"
                metric_card("Valore magazzino (ultima)", fmt_euro(val_ultima), tone_vm, note_vm)
            with _p3:
                tone_st_v = (
                    "positive" if delta_st_val > 1
                    else "negative" if delta_st_val < -1
                    else "neutral"
                )
                metric_card(
                    "Sell-through medio (ultima)",
                    f"{st_ultima_val:.1f}%/mese",
                    tone_st_v,
                    f"{'+' if delta_st_val >= 0 else ''}{delta_st_val:.1f}pp vs primo snapshot",
                )
            with _p4:
                tone_fc = (
                    "negative" if n_fermi_cronici >= 10
                    else "warning" if n_fermi_cronici >= 3
                    else "neutral"
                )
                metric_card(
                    "Titoli cronicamente fermi", str(n_fermi_cronici), tone_fc,
                    "fermi in ≥ 50% degli snapshot" if n_fermi_cronici > 0 else "nessun fermo cronico",
                )

            # ── Grafici ───────────────────────────────────────────────────────
            if not PLOTLY:
                st.info("Installa plotly per i grafici: `pip install plotly`")
            else:
                # ── Grafico 1: Andamento valore magazzino ─────────────────────
                st.divider()
                section("Andamento del valore magazzino")
                st.markdown(
                    '<div style="color: #5C5852; font-size: 13px; line-height: 1.5; margin: -15px 0 15px 0;">'
                    'Valore a costo (prezzo copertina − sconto) dei libri in giacenza. '
                    '<strong>Crescita</strong> → accumulo invenduto. '
                    '<strong>Riduzione</strong> → rese o vendite efficaci.'
                    '</div>',
                    unsafe_allow_html=True
                )
                try:
                    # Validazione dati
                    if df_agg.empty or "Valore_Mag" not in df_agg.columns:
                        st.warning("Dati non disponibili per il grafico valore magazzino")
                    else:
                        val_data = df_agg["Valore_Mag"].dropna()
                        if len(val_data) == 0 or np.isinf(val_data).any() or np.isnan(val_data).any():
                            st.info("Dati insufficienti per il grafico")
                        else:
                            fig_val = go.Figure()
                            fig_val.add_trace(go.Scatter(
                                x=df_agg["Periodo"],
                                y=df_agg["Valore_Mag"],
                                mode="lines+markers",
                                name="Valore magazzino",
                                showlegend=False,
                                line=dict(color="#B5362C", width=3.5),
                                marker=dict(
                                    size=12, color="#B5362C",
                                    line=dict(width=2.5, color="white"),
                                    opacity=1,
                                ),
                                fill="tozeroy",
                                fillcolor="rgba(181,54,44,0.12)",
                                hovertemplate=(
                                    "<b>%{x}</b><br>"
                                    "Valore: <b>%{customdata}</b><br>"
                                    "<extra></extra>"
                                ),
                                customdata=[fmt_euro(v) for v in df_agg["Valore_Mag"]],
                                connectgaps=True,
                            ))
                            # Etichette dati ai nodi — stile editoriale migliorato
                            for _, row in df_agg.iterrows():
                                fig_val.add_annotation(
                                    x=row["Periodo"], y=row["Valore_Mag"],
                                    text=f"<b>{fmt_euro(row['Valore_Mag'])}</b>",
                                    yshift=22, showarrow=True,
                                    arrowhead=0, arrowsize=0, arrowwidth=0, arrowcolor="transparent",
                                    font=dict(size=10, color="#16130F", family="Inter"),
                                    xanchor="center", yanchor="bottom",
                                    bgcolor="rgba(255,255,255,0.8)", borderpad=4,
                                )
                            _econ(
                                fig_val,
                                title="Il valore del magazzino nel tempo",
                                subtitle="Valore a costo dei libri in giacenza · € · Crescita = accumulo invenduto",
                                src="Elaborazione su dati del gestionale",
                            )
                            max_val = df_agg["Valore_Mag"].max()
                            fig_val.update_yaxes(
                                tickprefix="€ ", tickformat=",.0f",
                                range=[0, max_val * 1.35] if max_val > 0 else [0, 1000],
                            )
                            fig_val.update_layout(height=420)
                            st.plotly_chart(fig_val, use_container_width=True,
                                            config={"displayModeBar": True, "scrollZoom": True, "displaylogo": False,
                                                    "modeBarButtonsToRemove": ["lasso2d", "select2d"]})
                except Exception as e:
                    st.error(f"Errore nel grafico valore magazzino: {str(e)}")

                # ── Grafico 2: Sell-through per editore ───────────────────────
                if df_st_ed is not None and len(top_editori) > 0:
                    st.divider()
                    section("Sell-through per editore nel tempo")
                    st.caption(
                        "Copie vendute / giacenza × 100, calcolato per i 6 editori "
                        "con il maggior volume di vendite. "
                        "Le linee tratteggiate indicano le soglie di settore AIE/ISTAT 2022."
                    )
                    try:
                        if df_st_ed.empty or len(top_editori) == 0:
                            st.info("Dati insufficienti per il grafico sell-through per editore")
                        else:
                            fig_st = go.Figure()
                            # Soglie benchmark — linee di riferimento migliorati
                            fig_st.add_hline(
                                y=BENCHMARK["sell_through_attenzione"],
                                line=dict(color="#C8A951", width=2, dash="dash"),
                                annotation_text="Attenzione (8%/mese)",
                                annotation_position="top right",
                                annotation_font=dict(size=9, color="#C8A951", family="Inter"),
                                annotation_bgcolor="rgba(200,169,81,0.08)",
                                annotation_bordercolor="#C8A951",
                                annotation_borderwidth=1,
                            )
                            fig_st.add_hline(
                                y=BENCHMARK["sell_through_critico"],
                                line=dict(color="#B5362C", width=2, dash="dash"),
                                annotation_text="Critico (4%/mese)",
                                annotation_position="top right",
                                annotation_font=dict(size=9, color="#B5362C", family="Inter"),
                                annotation_bgcolor="rgba(181,54,44,0.08)",
                                annotation_bordercolor="#B5362C",
                                annotation_borderwidth=1,
                            )
                            for i, editore in enumerate(top_editori):
                                df_ed = df_st_ed[df_st_ed["Editore"] == editore].copy()
                                color = ECON_PAL[i % len(ECON_PAL)]
                                if len(df_ed) > 0:
                                    fig_st.add_trace(go.Scatter(
                                        x=df_ed["_Periodo"],
                                        y=df_ed["SellThrough"],
                                        name=editore,
                                        line=dict(color=color, width=3.5),
                                        mode="lines+markers",
                                        marker=dict(
                                            size=11, color=color,
                                            line=dict(width=2.5, color="white"),
                                            opacity=1,
                                        ),
                                        hovertemplate=(
                                            f"<b>{editore}</b><br>"
                                            "Periodo: <b>%{x}</b><br>"
                                            "Sell-through: <b>%{y:.1f}%</b>/mese<extra></extra>"
                                        ),
                                        connectgaps=True,
                                    ))
                            _econ(
                                fig_st,
                                title="Sell-through mensile per editore",
                                subtitle=(
                                    "Copie vendute / giacenza × 100 · %/mese · "
                                    "Top 6 editori per volume · Linee gialle/rosse = soglie settore"
                                ),
                                ysuffix="%",
                                src="Elaborazione su dati del gestionale · Soglie: AIE/ISTAT 2022",
                            )
                            fig_st.update_yaxes(rangemode="tozero")
                            fig_st.update_layout(height=450)
                            st.plotly_chart(fig_st, use_container_width=True,
                                            config={"displayModeBar": True, "scrollZoom": True, "displaylogo": False,
                                                    "modeBarButtonsToRemove": ["lasso2d", "select2d"]})
                    except Exception as e:
                        st.error(f"Errore nel grafico sell-through: {str(e)}")

                # ── Grafico 3: Titoli cronicamente fermi ──────────────────────
                st.divider()
                section("Titoli a rischio cronico")
                st.caption(
                    f"Titoli con sell-through < {BENCHMARK['sell_through_critico']:.0f}%/mese "
                    "in almeno il 50% degli snapshot e presenti in almeno 2 rilevazioni. "
                    "Ordinati per **valore immobilizzato × persistenza del fermo** — "
                    "i più rischiosi in cima. Intensità del colore = frequenza del fermo."
                )
                if tit_fermi.empty:
                    empty_state(
                        "✓", "Nessun titolo cronicamente fermo",
                        "Non ci sono titoli fermi in ≥ 50% degli snapshot caricati.",
                    )
                else:
                    try:
                        tit_d = tit_fermi.copy()
                        # Validazione dati
                        if tit_d.empty or "ValMag_Medio" not in tit_d.columns:
                            st.warning("Dati incompleti per il grafico titoli fermi")
                        else:
                            # Troncamento etichette per leggibilità
                            tit_d["_Label"] = tit_d["Titolo"].apply(
                                lambda t: t[:45] + "…" if len(t) > 45 else t
                            )
                            tit_d["_RilevStr"] = tit_d.apply(
                                lambda r: f"{int(r['N_Fermo'])}/{int(r['N_Rilev'])} snapshot in fermo",
                                axis=1,
                            )
                            # Colore: rosso con opacità proporzionale alla percentuale di fermo
                            alpha_vals    = 0.35 + 0.65 * tit_d["Pct_Fermo"]
                            marker_colors = [f"rgba(181,54,44,{a:.2f})" for a in alpha_vals]

                            fig_fermi = go.Figure(go.Bar(
                                y=tit_d["_Label"],
                                x=tit_d["ValMag_Medio"],
                                orientation="h",
                                marker_color=marker_colors,
                                marker_line=dict(width=1.5, color="rgba(181,54,44,0.3)"),
                                text=[f"  {fmt_euro(v)}" for v in tit_d["ValMag_Medio"]],
                                textposition="outside",
                                textfont=dict(size=10, color="#16130F", family="Inter"),
                                hovertemplate=(
                                    "<b>%{y}</b><br>"
                                    "Valore imm. medio: <b>€%{x:,.0f}</b><br>"
                                    "Frequenza: <b>%{customdata}</b><br>"
                                    "<extra></extra>"
                                ),
                                customdata=tit_d["_RilevStr"],
                                hoverinfo="text",
                            ))
                            fig_fermi.update_yaxes(autorange="reversed")
                            _econ(
                                fig_fermi,
                                title="Titoli a rischio cronico",
                                subtitle=(
                                    "Valore medio immobilizzato (€ a costo) · Ordinati per impatto economico × persistenza · "
                                    "Intensità colore = frequenza del fermo"
                                ),
                                src="Elaborazione su dati del gestionale",
                            )
                            fig_fermi.update_xaxes(tickprefix="€ ", tickformat=",.0f")
                            fig_fermi.update_layout(
                                height=max(380, 42 * len(tit_d) + 150),
                                margin=dict(l=12, r=140, t=88, b=80),
                                hovermode="y",
                            )
                            st.plotly_chart(fig_fermi, use_container_width=True,
                                            config={"displayModeBar": True, "scrollZoom": False, "displaylogo": False,
                                                    "modeBarButtonsToRemove": ["lasso2d", "select2d", "zoom2d", "pan2d"]})
                    except Exception as e:
                        st.error(f"Errore nel grafico titoli fermi: {str(e)}")

                    with st.expander("📋 Dettaglio titoli fermi"):
                        disp_cols = ["Titolo"]
                        if "Autore"  in tit_fermi.columns: disp_cols.append("Autore")
                        if "Editore" in tit_fermi.columns: disp_cols.append("Editore")
                        disp_cols += [
                            "N_Rilev", "N_Fermo", "Giacenza_Media",
                            "ST_Medio", "ValMag_Medio", "Pct_Fermo",
                        ]
                        tit_show = tit_fermi[disp_cols].copy()
                        tit_show["Giacenza_Media"] = tit_show["Giacenza_Media"].round(1)
                        tit_show["ST_Medio"]       = (
                            tit_show["ST_Medio"].round(1).astype(str) + "%"
                        )
                        tit_show["ValMag_Medio"]   = tit_show["ValMag_Medio"].apply(fmt_euro)
                        tit_show["Pct_Fermo"]      = (
                            (tit_show["Pct_Fermo"] * 100).round(0).astype(int).astype(str) + "%"
                        )
                        tit_show = tit_show.rename(columns={
                            "N_Rilev":        "Snapshot tot.",
                            "N_Fermo":        "Snapshot fermo",
                            "Giacenza_Media": "Giacenza media",
                            "ST_Medio":       "Sell-through medio",
                            "ValMag_Medio":   "Valore imm. medio",
                            "Pct_Fermo":      "% in fermo",
                        })
                        st.dataframe(tit_show, use_container_width=True, hide_index=True)
                        st.download_button(
                            "📥 Esporta titoli fermi (CSV)",
                            data=tit_show.to_csv(index=False).encode("utf-8-sig"),
                            file_name=f"titoli_fermi_{DATA_SISTEMA.strftime('%Y%m%d')}.csv",
                            mime="text/csv",
                        )

                # ── Grafico 4: Delta sell-through editori ─────────────────────
                if df_delta_ed is not None and len(df_delta_ed) > 0:
                    try:
                        if "Delta" not in df_delta_ed.columns or "Editore" not in df_delta_ed.columns:
                            st.warning("Dati incompleti per il grafico variazioni")
                        else:
                            st.divider()
                            section("Chi è migliorato, chi è peggiorato")
                            st.caption(
                                f"Variazione del sell-through mensile per editore: "
                                f"**{periodo_labels[0]}** → **{periodo_labels[-1]}**. "
                                "Verde = miglioramento · Rosso = peggioramento. "
                                "Solo editori presenti in entrambi gli snapshot estremi."
                            )
                            colors_delta = [
                                "#00877A" if d > 0 else "#B5362C"
                                for d in df_delta_ed["Delta"]
                            ]
                            text_delta = [
                                f"{'+' if d > 0 else ''}{d:.1f}pp"
                                for d in df_delta_ed["Delta"]
                            ]
                            fig_delta = go.Figure(go.Bar(
                                y=df_delta_ed["Editore"],
                                x=df_delta_ed["Delta"],
                                orientation="h",
                                marker_color=colors_delta,
                                marker_line=dict(width=1.5, color="rgba(0,0,0,0.1)"),
                                text=text_delta,
                                textposition="outside",
                                textfont=dict(size=10, color="#16130F", family="Inter"),
                                hovertemplate=(
                                    "<b>%{y}</b><br>"
                                    f"Sell-through {periodo_labels[0]}: <b>%{{customdata[0]:.1f}}%</b><br>"
                                    f"Sell-through {periodo_labels[-1]}: <b>%{{customdata[1]:.1f}}%</b><br>"
                                    "Variazione: <b>%{x:+.1f}pp</b><br>"
                                    "<extra></extra>"
                                ),
                                customdata=list(zip(
                                    df_delta_ed["ST_Prima"],
                                    df_delta_ed["ST_Ultima"],
                                )),
                            ))
                            _econ(
                                fig_delta,
                                title="Variazione sell-through per editore",
                                subtitle=(
                                    f"Punti percentuali · "
                                    f"{periodo_labels[0]} → {periodo_labels[-1]} · "
                                    "Barre verso destra = miglioramento, sinistra = peggioramento"
                                ),
                                x0=True,
                                src="Elaborazione su dati del gestionale",
                            )
                            fig_delta.update_xaxes(ticksuffix="pp")
                            fig_delta.update_layout(
                                height=max(340, 42 * len(df_delta_ed) + 150),
                                margin=dict(l=12, r=90, t=88, b=80),
                                hovermode="y",
                            )
                            st.plotly_chart(fig_delta, use_container_width=True,
                                            config={"displayModeBar": True, "scrollZoom": False, "displaylogo": False,
                                                    "modeBarButtonsToRemove": ["lasso2d", "select2d", "zoom2d", "pan2d"]})
                    except Exception as e:
                        st.error(f"Errore nel grafico variazioni: {str(e)}")

            # ── Riepilogo aggregato scaricabile ───────────────────────────────
            st.divider()
            with st.expander("📊 Riepilogo per periodo — dati aggregati"):
                st.caption(
                    "Aggregati per snapshot — base di tutti i calcoli precedenti."
                )
                df_agg_show = df_agg.copy()
                df_agg_show["Valore_Mag"]  = df_agg_show["Valore_Mag"].apply(fmt_euro)
                df_agg_show["SellThrough"] = df_agg_show["SellThrough"].apply(
                    lambda x: f"{x:.1f}%"
                )
                df_agg_show["Giacenza"]    = df_agg_show["Giacenza"].apply(
                    lambda x: f"{x:,.0f}"
                )
                df_agg_show["Vendute"]     = df_agg_show["Vendute"].apply(
                    lambda x: f"{x:,.0f}"
                )
                df_agg_show = df_agg_show.rename(columns={
                    "Valore_Mag":  "Valore magazzino",
                    "SellThrough": "Sell-through medio",
                    "N_Titoli":    "N. titoli",
                    "Giacenza":    "Giacenza totale",
                    "Vendute":     "Vendite (30gg)",
                })
                st.dataframe(df_agg_show, use_container_width=True, hide_index=True)
                st.download_button(
                    "📥 Esporta riepilogo (CSV)",
                    data=df_agg_show.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"storico_riepilogo_{DATA_SISTEMA.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )

            # ── Note metodologiche ────────────────────────────────────────────
            st.divider()
            with st.expander("📌 Note metodologiche — leggere prima di usare i numeri"):
                st.markdown(f"""
**Sell-through mensile** — `Vendute_Ultimi_30_Giorni / Giacenza × 100`.
Misura la rotazione dello stock rispetto alla giacenza corrente.
Riflette le vendite del mese *precedente* la data dello snapshot, non vendite cumulative.
Con giacenza = 0 il valore non è calcolabile e viene escluso dalla media.

**Valore magazzino a costo** — `(Prezzo_Copertina − Sconto_Libreria) × Giacenza`.
Stima il capitale immobilizzato al prezzo d'acquisto.
Non include costi di gestione, affitto o personale.

**Titoli cronicamente fermi** — sell-through < {BENCHMARK['sell_through_critico']:.0f}%/mese
in almeno il 50% degli snapshot, con presenza in almeno 2 rilevazioni.
Il **punteggio di rischio** è `(% snapshot in fermo) × (valore medio immobilizzato)`.
Più alto = più urgente.

**Delta sell-through** — basato esclusivamente sul primo e sull'ultimo snapshot.
Con 2 snapshot è una misura esatta; con più snapshot il grafico 2 mostra l'andamento completo.

**Soglie di settore** — sell-through < 4%/mese = critico, 4–8%/mese = attenzione.
Fonte: AIE / ISTAT 2022 (dati pubblici aggregati, mercato librario italiano).

> ⚠️ Questi modelli descrivono ciò che è successo nel tuo stock, non prevedono il futuro.
> Usali come base per ragionare, non come verdetto definitivo.
""")  # noqa: E501

# ===========================================================================
# SIMULATORE ORDINE NUOVO TITOLO
# ===========================================================================
elif strumento == "Simulatore ordine":

    page_header(
        "Simulatore ordine",
        "Stima quante copie ordinare di un nuovo titolo, "
        "calibrata sulla rotazione storica dei titoli dello stesso editore nel tuo stock.",
    )

    # ── Dati di riferimento ─────────────────────────────────────────────────
    # Usa df_mag già caricato nel Radar Salva-Cassa se disponibile
    df_sim_ref = st.session_state.get("df_mag")

    # ── Form input ──────────────────────────────────────────────────────────
    section("Parametri del nuovo titolo")
    c_left, c_right = st.columns([3, 2], gap="large")

    with c_left:
        st.caption("Informazioni editoriali")
        sim_titolo  = st.text_input(
            "Titolo", placeholder="es. Il nome della rosa", key="sim_titolo",
        )
        sim_editore = st.text_input(
            "Editore / Distributore",
            placeholder="es. Einaudi",
            key="sim_editore",
            help="Verrà usato per filtrare i titoli di confronto nel tuo gestionale.",
        )
        _cp, _cs = st.columns(2)
        sim_prezzo = _cp.number_input(
            "Prezzo copertina (€)",
            min_value=0.01, max_value=999.0,
            value=18.00, step=0.50, format="%.2f", key="sim_prezzo",
        )
        sim_sconto_pct = _cs.number_input(
            "Sconto libreria (%)",
            min_value=0.0, max_value=99.0,
            value=30.0, step=1.0, format="%.1f", key="sim_sconto_pct_val",
            help="Percentuale di sconto applicata dall'editore/distributore.",
        )
        sim_sconto_val = round(sim_prezzo * sim_sconto_pct / 100, 2)
        costo_copia    = max(0.0, round(sim_prezzo - sim_sconto_val, 2))
        if costo_copia <= 0:
            st.warning("⚠️ Costo netto ≤ 0 — verifica prezzo e sconto.")

    with c_right:
        st.caption("Parametri d'ordine")
        sim_target_mesi = st.slider(
            "Copertura desiderata (mesi)",
            min_value=1, max_value=12, value=3, step=1, key="sim_target_mesi",
            help="Quanti mesi vuoi che le copie ordinate durino prima di esaurirsi.",
        )
        sim_safety = st.slider(
            "Scorta di sicurezza (copie extra)",
            min_value=0, max_value=10, value=1, step=1, key="sim_safety",
            help="Copie aggiuntive oltre la stima base, per non arrivare a zero scorte.",
        )
        sim_max_expo = st.number_input(
            "Tetto massimo esposizione (€, 0 = nessun limite)",
            min_value=0.0, max_value=50000.0, value=0.0, step=50.0, format="%.0f",
            key="sim_max_expo",
            help="Limita il valore massimo investito in questo titolo.",
        )

    st.divider()

    # ── Guard: nessun gestionale caricato ───────────────────────────────────
    if df_sim_ref is None:
        empty_state(
            "📊", "Nessun gestionale caricato",
            "Vai al **Radar Salva-Cassa** nella barra di navigazione e carica il tuo "
            "CSV di magazzino — il simulatore lo userà come base di stima.",
        )
    else:
        # ── Costruzione peer group ──────────────────────────────────────────
        # Minimo titoli perché la stima sia statisticamente utile
        MIN_PEERS = 3

        # Solo titoli con giacenza > 0 — gli altri non hanno dati di vendita
        df_pool = df_sim_ref[df_sim_ref["Giacenza"] > 0].copy()

        if df_pool.empty:
            st.warning("Il gestionale non contiene titoli con giacenza > 0. Impossibile stimare.")
        else:
            # 1. Filtra per editore (case-insensitive, match parziale)
            editore_q = sim_editore.strip().lower()
            if editore_q and "Editore" in df_pool.columns:
                df_pub = df_pool[
                    df_pool["Editore"].str.lower().str.contains(editore_q, na=False)
                ].copy()
            else:
                df_pub = df_pool.copy()

            fallback_note = ""
            if editore_q and len(df_pub) < MIN_PEERS:
                fallback_note = (
                    f"Solo {len(df_pub)} titol{'o' if len(df_pub) == 1 else 'i'} trovati "
                    f"per **{sim_editore}** con giacenza > 0. "
                    "La stima è allargata a tutti gli editori per maggiore robustezza statistica."
                )
                df_pub = df_pool.copy()

            # 2. Filtro per fascia di prezzo (±40%) — migliora la comparabilità
            if sim_prezzo > 0 and "Prezzo_Copertina" in df_pub.columns:
                price_lo = sim_prezzo * 0.60
                price_hi = sim_prezzo * 1.40
                df_price = df_pub[df_pub["Prezzo_Copertina"].between(price_lo, price_hi)].copy()
                if len(df_price) >= MIN_PEERS:
                    df_pub = df_price

            n_peers = len(df_pub)
            v       = df_pub["Vendute_Ultimi_30_Giorni"]
            v_p25   = float(np.percentile(v, 25))
            v_p50   = float(np.percentile(v, 50))
            v_p75   = float(np.percentile(v, 75))

            if fallback_note:
                st.info(fallback_note)

            # ── Calcolo scenari ─────────────────────────────────────────────
            def _sim_scenario(vel: float, mesi: int, safety: int,
                               costo: float, max_expo: float) -> dict:
                copie = max(1, round(vel * mesi) + safety)
                if max_expo > 0 and costo > 0:
                    copie = max(1, min(copie, int(max_expo // costo)))
                copertura      = (copie / vel) if vel > 0 else float("inf")
                investimento   = copie * costo
                ricavo_atteso  = copie * sim_prezzo
                margine_totale = copie * (sim_prezzo - costo)
                margine_pct    = ((sim_prezzo - costo) / sim_prezzo * 100) if sim_prezzo > 0 else 0.0
                return {
                    "copie": copie, "vel": vel, "copertura": copertura,
                    "investimento": investimento, "ricavo_atteso": ricavo_atteso,
                    "margine_totale": margine_totale, "margine_pct": margine_pct,
                }

            sc_pru = _sim_scenario(v_p25, sim_target_mesi, sim_safety, costo_copia, float(sim_max_expo))
            sc_bas = _sim_scenario(v_p50, sim_target_mesi, sim_safety, costo_copia, float(sim_max_expo))
            sc_ott = _sim_scenario(v_p75, sim_target_mesi, sim_safety, costo_copia, float(sim_max_expo))

            def _cov_str(c: float) -> str:
                return f"{c:.1f} mesi" if c != float("inf") else "∞ mesi"

            # ── Peer group expander ─────────────────────────────────────────
            section("Dati di riferimento")
            with st.expander(
                f"📋 {n_peers} titoli analizzati come confronto"
                + (f" · editore: {sim_editore}" if editore_q else " · tutti gli editori")
            ):
                _peer_cols = [c for c in [
                    "Titolo", "Autore", "Editore",
                    "Giacenza", "Vendute_Ultimi_30_Giorni", "Prezzo_Copertina",
                ] if c in df_pub.columns]
                df_peer_disp = (
                    df_pub[_peer_cols]
                    .sort_values("Vendute_Ultimi_30_Giorni", ascending=False)
                    .copy()
                )
                st.dataframe(
                    df_peer_disp, use_container_width=True, hide_index=True,
                    height=min(360, 45 + len(df_peer_disp) * 35),
                )
                st.caption(
                    f"Velocità di vendita mensile (copie/30 gg) — "
                    f"Prudente (P25): **{v_p25:.1f}** · "
                    f"Base (P50): **{v_p50:.1f}** · "
                    f"Ottimista (P75): **{v_p75:.1f}**"
                )

            # ── Raccomandazione ─────────────────────────────────────────────
            st.divider()
            section("Raccomandazione d'ordine")
            st.caption(
                f"Basata su {n_peers} titoli di confronto · "
                f"copertura obiettivo: {sim_target_mesi} "
                f"{'mese' if sim_target_mesi == 1 else 'mesi'} · "
                f"scorta sicurezza: {sim_safety} "
                f"{'copia' if sim_safety == 1 else 'copie'}"
            )

            _c1, _c2, _c3 = st.columns(3)
            with _c1:
                metric_card(
                    "Prudente",
                    f"{sc_pru['copie']} copie",
                    "neutral",
                    f"Copertura: {_cov_str(sc_pru['copertura'])} · "
                    f"Investimento: {fmt_euro(sc_pru['investimento'])}",
                )
            with _c2:
                metric_card(
                    "Base  ←  punto di partenza",
                    f"{sc_bas['copie']} copie",
                    "warning",
                    f"Copertura: {_cov_str(sc_bas['copertura'])} · "
                    f"Investimento: {fmt_euro(sc_bas['investimento'])}",
                )
            with _c3:
                metric_card(
                    "Ottimista",
                    f"{sc_ott['copie']} copie",
                    "positive",
                    f"Copertura: {_cov_str(sc_ott['copertura'])} · "
                    f"Investimento: {fmt_euro(sc_ott['investimento'])}",
                )

            # ── Grafico scenari ─────────────────────────────────────────────
            if PLOTLY:
                try:
                    st.divider()
                    section("Scenari a confronto")

                    nomi_sc  = ["Prudente\n(P25)", "Base\n(Mediana)", "Ottimista\n(P75)"]
                    copie_sc = [sc_pru["copie"], sc_bas["copie"], sc_ott["copie"]]
                    cov_sc   = [_cov_str(s["copertura"]) for s in [sc_pru, sc_bas, sc_ott]]
                    inv_sc   = [fmt_euro(s["investimento"]) for s in [sc_pru, sc_bas, sc_ott]]
                    vel_sc   = [s["vel"] for s in [sc_pru, sc_bas, sc_ott]]

                    # Validazione
                    if not copie_sc or all(c == 0 for c in copie_sc):
                        st.warning("Impossibile generare scenari con i dati attuali")
                    else:
                        fig_sim = go.Figure(go.Bar(
                            y=nomi_sc,
                            x=copie_sc,
                            orientation="h",
                            marker_color=["#2A5FAC", "#B5362C", "#00877A"],
                            marker_line=dict(width=1.5, color="rgba(0,0,0,0.1)"),
                            text=[f"  <b>{c}</b> cop.<br>Cov: {cov}" for c, cov in zip(copie_sc, cov_sc)],
                            textposition="outside",
                            textfont=dict(size=11, color="#16130F", family="Inter"),
                            hovertemplate=(
                                "<b>%{y}</b><br>"
                                "Copie consigliate: <b>%{x}</b><br>"
                                "Vel. vendita: <b>%{customdata[0]:.1f}%</b> cop./mese<br>"
                                "Copertura: <b>%{customdata[1]}</b><br>"
                                "Investimento: <b>%{customdata[2]}</b><br>"
                                "<extra></extra>"
                            ),
                            customdata=list(zip(vel_sc, cov_sc, inv_sc)),
                        ))
                        _econ(
                            fig_sim,
                            title=(
                                f"Copie consigliate per «{sim_titolo.strip()}»"
                                if sim_titolo.strip()
                                else "Copie consigliate per il nuovo titolo"
                            ),
                            subtitle=(
                                f"Tre scenari su {n_peers} titoli di confronto · "
                                f"copertura: {sim_target_mesi} mesi · "
                                + (f"editore: {sim_editore}" if sim_editore.strip() else "tutti gli editori")
                            ),
                            src="Elaborazione su dati del gestionale",
                        )
                        max_copie = max(copie_sc) if copie_sc else 1
                        fig_sim.update_xaxes(
                            range=[0, max_copie * 1.65],
                            title=None,
                            dtick=1 if max_copie <= 20 else None,
                        )
                        fig_sim.update_layout(
                            height=380,
                            margin=dict(l=12, r=150, t=88, b=80),
                            hovermode="y",
                        )
                        st.plotly_chart(fig_sim, use_container_width=True,
                                        config={"displayModeBar": True, "scrollZoom": False, "displaylogo": False,
                                                "modeBarButtonsToRemove": ["lasso2d", "select2d", "zoom2d", "pan2d"]})
                except Exception as e:
                    st.error(f"Errore nel grafico scenari: {str(e)}")

            # ── Analisi economica ───────────────────────────────────────────
            st.divider()
            with st.expander("💰 Analisi economica per scenario"):
                econ_rows = []
                for nome, sc in [("Prudente", sc_pru), ("Base", sc_bas), ("Ottimista", sc_ott)]:
                    econ_rows.append({
                        "Scenario":                  nome,
                        "Copie":                     sc["copie"],
                        "Vel. vendita (cop./mese)":  f"{sc['vel']:.1f}",
                        "Copertura stimata":         _cov_str(sc["copertura"]),
                        "Investimento":              fmt_euro(sc["investimento"]),
                        "Ricavo (se tutto venduto)": fmt_euro(sc["ricavo_atteso"]),
                        "Margine lordo":             fmt_euro(sc["margine_totale"]),
                        "Margine %":                 f"{sc['margine_pct']:.1f}%",
                    })
                st.dataframe(pd.DataFrame(econ_rows), use_container_width=True, hide_index=True)
                st.caption(
                    f"Prezzo copertina: **{fmt_euro(sim_prezzo)}** · "
                    f"Sconto: **{fmt_euro(sim_sconto_val)}** ({sim_sconto_pct:.1f}%) · "
                    f"Costo netto/copia: **{fmt_euro(costo_copia)}**"
                )

            # ── Note metodologiche ──────────────────────────────────────────
            st.divider()
            with st.expander("📌 Come funziona la stima — leggere prima di usare i numeri"):
                st.markdown(f"""
**Peer group** — titoli dello stesso editore nel tuo gestionale con giacenza > 0,
nella fascia di prezzo ±40% rispetto al nuovo titolo (se almeno {MIN_PEERS} corrispondenze).
Se l'editore ha meno di {MIN_PEERS} titoli in stock, si usano tutti gli editori presenti.

**Velocità di vendita** — `Vendute_Ultimi_30_Giorni` dei titoli del peer group.
I tre scenari usano il 25°, 50° e 75° percentile di questa distribuzione:
- **Prudente** — vendi come il 25% più lento dei titoli simili (P25)
- **Base** — vendi come la mediana dei titoli simili (P50) · punto di partenza consigliato
- **Ottimista** — vendi come il 25% più rapido dei titoli simili (P75)

**Copie consigliate** — `ceil(velocità × mesi di copertura) + scorta di sicurezza`.
Il tetto di esposizione (se impostato) riduce il numero massimo di copie.

**Margine lordo** — `(Prezzo_Copertina − Sconto) × copie`.
Non include costi indiretti (affitto, personale, costi di reso eventuali).

> ⚠️ Questa stima usa la rotazione di titoli *già sul mercato* nel tuo stock come proxy.
> Un titolo nuovo può vendere diversamente: considera la novità editoriale,
> la stagionalità, le promozioni dell'editore e la fedeltà della tua clientela
> prima di effettuare l'ordine. La stima è un punto di partenza, non un verdetto.
""")


# ===========================================================================
# PREFERENCES PERSISTENCE — salva le preferenze alla fine di ogni sessione
# ===========================================================================
@st.cache_data(show_spinner=False)
def _should_save_prefs():
    """Marker per evitare salvataggio multiplo nella stessa sessione."""
    return True

if _should_save_prefs():
    # Estrai le preferenze persistenti da session_state
    prefs_to_save = {}
    for pref_key in PERSISTENT_PREFS:
        if pref_key in st.session_state:
            prefs_to_save[pref_key] = st.session_state[pref_key]

    # Salva le preferenze
    if prefs_to_save:
        save_preferences(prefs_to_save)

