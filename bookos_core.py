"""
BookStore OS — logica di business pura, senza dipendenze Streamlit.
Importato da streamlit_app.py e dai test unitari.
"""
from __future__ import annotations

from datetime import date

import pandas as pd


def parse_numeric(series: pd.Series) -> pd.Series:
    """Converte una colonna in float gestendo separatori italiani (1.234,56) e standard (1234.56)."""
    s = series.astype(str).str.strip()
    italian = s.str.contains(r'\.') & s.str.contains(r',')
    cleaned_it  = s.str.replace(r'\.', '', regex=True).str.replace(',', '.', regex=False)
    cleaned_std = s.str.replace(',', '.', regex=False)
    result = cleaned_it.where(italian, cleaned_std)
    return pd.to_numeric(result, errors='coerce').fillna(0)


def processa_magazzino(
    df_raw: pd.DataFrame,
    soglia_invenduto: date,
    finestra_start: date,
    finestra_end: date,
    rot_min: int,
) -> dict:
    """
    Classifica i titoli del magazzino in tre categorie:
    - rendere:  nella finestra di resa (finestra_start–finestra_end) con vendite < rot_min
    - tenere:   nella finestra di resa con vendite >= rot_min
    - scaduto:  fatturati prima di soglia_invenduto

    Restituisce un dict con chiavi: df, scaduto, tenere, rendere, warnings.
    """
    df = df_raw.copy()
    n_totale = len(df)

    # Parsing robusto: accetta dd/mm/yyyy, yyyy-mm-dd, dd-mm-yyyy
    _raw = df["Data_Fatturazione"].astype(str).str.strip()
    try:
        # pandas >= 2.0
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

    fat        = df["Data_Fatturazione"].dt.date
    df_scaduto = df[fat < soglia_invenduto].copy()
    df_finestra = df[(fat >= finestra_start) & (fat <= finestra_end)].copy()
    df_finestra = df_finestra[df_finestra["Giacenza"] > 0]
    df_tenere  = df_finestra[df_finestra["Vendute_Ultimi_30_Giorni"] >= rot_min].copy()
    df_rendere = df_finestra[df_finestra["Vendute_Ultimi_30_Giorni"] < rot_min].copy()
    df_rendere["Valore_Recuperabile"] = (
        (df_rendere["Prezzo_Copertina"] - df_rendere["Sconto_Libreria"]) * df_rendere["Giacenza"]
    )
    return {
        "df": df,
        "scaduto": df_scaduto,
        "tenere": df_tenere,
        "rendere": df_rendere,
        "warnings": warnings_list,
    }
