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
    costo_spedizione: float = 0.0,
    costo_per_copia: float = 0.0,
) -> dict:
    """
    Classifica i titoli del magazzino in tre categorie:
    - rendere:  nella finestra di resa (finestra_start–finestra_end) con vendite < rot_min
    - tenere:   nella finestra di resa con vendite >= rot_min
    - scaduto:  fatturati prima di soglia_invenduto

    costo_spedizione: costo fisso per spedizione dell'intera partita di resa (€)
    costo_per_copia:  costo variabile per ogni copia resa (€/copia, es. imballaggio)

    Restituisce un dict con chiavi: df, scaduto, tenere, rendere, warnings, auto_corrections,
    costo_spedizione, costo_per_copia.
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

    oggi_ts  = pd.Timestamp(date.today())
    n_future = (df["Data_Fatturazione"] > oggi_ts).sum()
    if n_future > 0:
        warnings_list.append(
            f"{n_future} riga/e ha una Data_Fatturazione nel futuro — verifica i dati del gestionale."
        )

    for col in ["Giacenza", "Vendute_Ultimi_30_Giorni", "Prezzo_Copertina", "Sconto_Libreria"]:
        df[col] = parse_numeric(df[col])

    auto_corrections: list[str] = []

    if len(df) > 0:
        median_sconto = df["Sconto_Libreria"].median()
        if median_sconto > 5:
            # I valori sembrano percentuali (es. 18 invece di 3.42).
            # Convertiamo automaticamente: sconto_euro = prezzo_copertina × sconto% / 100
            df["Sconto_Libreria"] = df["Prezzo_Copertina"] * df["Sconto_Libreria"] / 100
            new_median = df["Sconto_Libreria"].median()
            auto_corrections.append(
                f"Sconto_Libreria: rilevati valori in percentuale (mediana: {median_sconto:.1f}%) — "
                f"convertiti automaticamente in euro (mediana risultante: €{new_median:.2f}). "
                "Verifica che i calcoli siano corretti."
            )

    ts_soglia_inv = pd.Timestamp(soglia_invenduto)
    ts_fs         = pd.Timestamp(finestra_start)
    ts_fe         = pd.Timestamp(finestra_end)
    fat           = df["Data_Fatturazione"]
    df_scaduto  = df[fat < ts_soglia_inv].copy()
    df_finestra = df[(fat >= ts_fs) & (fat <= ts_fe)].copy()
    df_finestra = df_finestra[df_finestra["Giacenza"] > 0]
    df_tenere  = df_finestra[df_finestra["Vendute_Ultimi_30_Giorni"] >= rot_min].copy()
    df_rendere = df_finestra[df_finestra["Vendute_Ultimi_30_Giorni"] < rot_min].copy()
    df_rendere["Valore_Recuperabile"] = (
        (df_rendere["Prezzo_Copertina"] - df_rendere["Sconto_Libreria"]) * df_rendere["Giacenza"]
    )
    # Valore netto per riga: deduce il costo variabile (imballaggio, handling)
    df_rendere["Valore_Recuperabile_Netto"] = (
        df_rendere["Valore_Recuperabile"] - costo_per_copia * df_rendere["Giacenza"]
    ).clip(lower=0)

    return {
        "df": df,
        "scaduto": df_scaduto,
        "tenere": df_tenere,
        "rendere": df_rendere,
        "warnings": warnings_list,
        "auto_corrections": auto_corrections,
        "costo_spedizione": costo_spedizione,
        "costo_per_copia": costo_per_copia,
    }
