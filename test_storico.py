"""
test_storico.py — Test di stress per il modulo Analisi Storica di BookStore OS
Esegui con: python test_storico.py
"""

import io
import sys
import traceback
import numpy as np
import pandas as pd
from pathlib import Path

# ── Replica delle costanti e funzioni pure di bookstore_os.py ─────────────────

SCHEMA_MAGAZZINO = {"Titolo", "Autore", "ISBN", "Editore", "Data_Fatturazione",
                    "Giacenza", "Vendute_Ultimi_30_Giorni", "Prezzo_Copertina", "Sconto_Libreria"}

BENCHMARK = {
    "sell_through_critico":    4.0,
    "sell_through_attenzione": 8.0,
}

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
    "isbn":                     "ISBN",
    "editore":                  "Editore",
}


def load_csv(raw_bytes: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return pd.read_csv(io.BytesIO(raw_bytes), encoding=enc)
        except Exception:
            continue
    raise ValueError("Impossibile leggere il file: encoding non supportato.")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    renamed = {}
    for col in df.columns:
        key = col.strip().lower().replace(" ", "_")
        if key in COL_ALIASES:
            renamed[col] = COL_ALIASES[key]
    return df.rename(columns=renamed)


def parse_numeric(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    italian = s.str.contains(r'\.') & s.str.contains(r',')
    cleaned_it  = s.str.replace(r'\.', '', regex=True).str.replace(',', '.', regex=False)
    cleaned_std = s.str.replace(',', '.', regex=False)
    result = cleaned_it.where(italian, cleaned_std)
    return pd.to_numeric(result, errors='coerce').fillna(0)


def carica_snapshot(path: Path) -> pd.DataFrame:
    """Carica, normalizza e valida uno snapshot. Lancia eccezione se non valido."""
    raw = path.read_bytes()
    df = load_csv(raw)
    df = normalize_columns(df)
    missing = SCHEMA_MAGAZZINO - set(df.columns)
    if missing:
        raise ValueError(f"Colonne mancanti: {sorted(missing)}")
    for col in ["Giacenza", "Vendute_Ultimi_30_Giorni", "Prezzo_Copertina", "Sconto_Libreria"]:
        df[col] = parse_numeric(df[col])
    df = df[df["Giacenza"] >= 0].copy()
    return df


def analisi_storica(snapshots: list[tuple[str, pd.DataFrame]]) -> dict:
    """
    Replica della logica core del modulo Analisi Storica.
    Input: lista di (label, df)
    Output: dict con i risultati
    """
    n_snaps = len(snapshots)

    # Aggregati per snapshot
    agg_rows = []
    for lbl, df_s in snapshots:
        giac    = df_s["Giacenza"].sum()
        vend    = df_s["Vendute_Ultimi_30_Giorni"].sum()
        costo   = (df_s["Prezzo_Copertina"] - df_s["Sconto_Libreria"]).clip(lower=0)
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

    # DataFrame combinato
    dfs_tagged = []
    for idx, (lbl, df_s) in enumerate(snapshots):
        d = df_s.copy()
        d["_Periodo"] = lbl
        d["_PIdx"]    = idx
        dfs_tagged.append(d)
    df_all = pd.concat(dfs_tagged, ignore_index=True)
    df_all["_Costo"]  = (df_all["Prezzo_Copertina"] - df_all["Sconto_Libreria"]).clip(lower=0)
    df_all["_ValMag"] = df_all["_Costo"] * df_all["Giacenza"]
    df_all["_ST"] = np.where(
        df_all["Giacenza"] > 0,
        df_all["Vendute_Ultimi_30_Giorni"] / df_all["Giacenza"] * 100,
        np.nan,
    )
    df_all["_Fermo"] = (
        (df_all["Giacenza"] > 0) &
        (df_all["_ST"] < BENCHMARK["sell_through_critico"])
    )

    # Sell-through per editore
    df_st_ed = None
    top_editori = []
    if "Editore" in df_all.columns:
        grp_ed = (
            df_all
            .groupby(["_PIdx", "_Periodo", "Editore"], as_index=False)
            .agg(Giacenza=("Giacenza", "sum"), Vendute=("Vendute_Ultimi_30_Giorni", "sum"))
        )
        grp_ed["SellThrough"] = np.where(
            grp_ed["Giacenza"] > 0,
            grp_ed["Vendute"] / grp_ed["Giacenza"] * 100,
            np.nan,
        )
        grp_ed = grp_ed.sort_values("_PIdx")
        top_editori = (
            grp_ed.groupby("Editore")["Vendute"].sum()
            .nlargest(6).index.tolist()
        )
        df_st_ed = grp_ed[grp_ed["Editore"].isin(top_editori)].copy()

    # Titoli cronicamente fermi
    extra_first = {c: "first" for c in ["Autore", "Editore"] if c in df_all.columns}
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

    # Delta sell-through editori (prima vs ultima)
    df_delta_ed = None
    if df_st_ed is not None and n_snaps >= 2:
        st_prima  = df_st_ed[df_st_ed["_PIdx"] == 0].set_index("Editore")["SellThrough"]
        st_ultima = df_st_ed[df_st_ed["_PIdx"] == n_snaps - 1].set_index("Editore")["SellThrough"]
        common    = st_prima.index.intersection(st_ultima.index)
        if len(common) > 0:
            df_delta_ed = pd.DataFrame({
                "Editore":  common,
                "ST_Prima": st_prima[common].values,
                "ST_Ultima": st_ultima[common].values,
            })
            df_delta_ed["Delta"] = df_delta_ed["ST_Ultima"] - df_delta_ed["ST_Prima"]

    return {
        "df_agg":      df_agg,
        "df_all":      df_all,
        "tit_fermi":   tit_fermi,
        "tit_stats":   tit_stats,
        "df_st_ed":    df_st_ed,
        "df_delta_ed": df_delta_ed,
        "n_snaps":     n_snaps,
        "top_editori": top_editori,
    }


# ── Infrastruttura di test ─────────────────────────────────────────────────────

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"

results = []

def run_test(name: str, fn):
    try:
        outcome, detail = fn()
        tag = PASS if outcome else FAIL
    except Exception as e:
        tag, detail = FAIL, f"Eccezione: {traceback.format_exc(limit=3)}"
    results.append((tag, name, detail))
    print(f"  {tag}  {name}")
    if detail:
        for line in detail.splitlines():
            print(f"         {line}")


BASE = Path(__file__).parent


# ══════════════════════════════════════════════════════════════════════════════
# GRUPPO 1 — Caricamento file
# ══════════════════════════════════════════════════════════════════════════════
print("\n-- Gruppo 1: Caricamento e normalizzazione --")

def t_carica_ref():
    df = carica_snapshot(BASE / "stress_ref.csv")
    ok = set(SCHEMA_MAGAZZINO).issubset(set(df.columns)) and len(df) == 10
    return ok, f"{len(df)} righe, colonne: {list(df.columns)}"
run_test("stress_ref.csv carica correttamente (10 righe, schema OK)", t_carica_ref)

def t_alias_colonne():
    df = carica_snapshot(BASE / "stress_3a_alias_colonne.csv")
    ok = "Vendute_Ultimi_30_Giorni" in df.columns and "Prezzo_Copertina" in df.columns
    return ok, f"Colonne dopo normalizzazione: {list(df.columns)}"
run_test("stress_3a: alias colonne (vendite_30g->Vendute, prezzo->Prezzo_Copertina)", t_alias_colonne)

def t_colonne_extra():
    df = carica_snapshot(BASE / "stress_3a_alias_colonne.csv")
    extra = [c for c in df.columns if c not in SCHEMA_MAGAZZINO]
    ok = len(extra) > 0  # colonne extra (Categoria, Scaffale) devono sopravvivere senza crash
    return ok, f"Colonne extra presenti e tollerate: {extra}"
run_test("stress_3a: colonne extra (Categoria, Scaffale) tollerate senza errore", t_colonne_extra)


# ══════════════════════════════════════════════════════════════════════════════
# GRUPPO 2 — Parsing numerico
# ══════════════════════════════════════════════════════════════════════════════
print("\n-- Gruppo 2: Parsing numerico --")

def t_numeri_virgola():
    df = carica_snapshot(BASE / "stress_1a_numeri_misti.csv")
    val = df["Prezzo_Copertina"].iloc[0]
    ok  = abs(val - 19.0) < 0.01
    return ok, f'Prezzo "19,00" → {val} (atteso 19.0)'
run_test('stress_1a: prezzo italiano "19,00" → 19.0', t_numeri_virgola)

def t_giacenza_zero_esclusa():
    df = carica_snapshot(BASE / "stress_1a_numeri_misti.csv")
    # Giacenza == 0 deve essere esclusa dal calcolo dei fermi, non dall'intero df
    n_zero = (df["Giacenza"] == 0).sum()
    ok = n_zero >= 0  # non crasha; le righe con giac=0 sono tenute nel df ma escluse dai fermi
    return ok, f"Righe con Giacenza=0 nel df caricato: {n_zero}"
run_test("stress_1a: righe con Giacenza=0 non causano crash al caricamento", t_giacenza_zero_esclusa)

def t_valori_estremi():
    df = carica_snapshot(BASE / "stress_2a_estremi.csv")
    # Vendite > Giacenza (es. 15 vendite con giac=2): non deve crashare
    # Sconto > Prezzo: il clip(lower=0) deve portare il costo a 0
    costo = (df["Prezzo_Copertina"] - df["Sconto_Libreria"]).clip(lower=0)
    ok = (costo >= 0).all()
    return ok, f"Tutti i costi dopo clip ≥ 0: min={costo.min():.2f}, max={costo.max():.2f}"
run_test("stress_2a: sconto > prezzo → costo clippato a 0 senza crash", t_valori_estremi)

def t_prezzo_quasi_zero():
    df = carica_snapshot(BASE / "stress_2a_estremi.csv")
    row = df[df["Titolo"] == "Test Prezzo Quasi Zero"]
    ok = len(row) > 0 and row["Prezzo_Copertina"].iloc[0] == 0.01
    return ok, f"Prezzo quasi-zero presente e parsato: {row['Prezzo_Copertina'].iloc[0] if len(row) > 0 else 'NON TROVATO'}"
run_test("stress_2a: prezzo 0.01 parsato correttamente", t_prezzo_quasi_zero)

def t_magazzino_enorme():
    df = carica_snapshot(BASE / "stress_2a_estremi.csv")
    row = df[df["Titolo"] == "Test Magazzino Enorme"]
    ok = len(row) > 0 and row["Giacenza"].iloc[0] == 999
    return ok, f"Giacenza 999: {row['Giacenza'].iloc[0] if len(row) > 0 else 'NON TROVATO'}"
run_test("stress_2a: giacenza 999 accettata senza overflow", t_magazzino_enorme)


# ══════════════════════════════════════════════════════════════════════════════
# GRUPPO 3 — Analisi comparativa (caso normale)
# ══════════════════════════════════════════════════════════════════════════════
print("\n-- Gruppo 3: Analisi comparativa - caso normale --")

def t_analisi_due_snapshot_normali():
    df_ref  = carica_snapshot(BASE / "stress_ref.csv")
    df_mod  = carica_snapshot(BASE / "stress_1a_numeri_misti.csv")
    r = analisi_storica([("Ref", df_ref), ("Mod", df_mod)])
    ok = r["n_snaps"] == 2 and len(r["df_agg"]) == 2
    return ok, f"n_snaps={r['n_snaps']}, df_agg rows={len(r['df_agg'])}"
run_test("ref + 1a: analisi con 2 snapshot produce df_agg con 2 righe", t_analisi_due_snapshot_normali)

def t_sell_through_non_negativo():
    df_ref = carica_snapshot(BASE / "stress_ref.csv")
    df_mod = carica_snapshot(BASE / "stress_1a_numeri_misti.csv")
    r = analisi_storica([("Ref", df_ref), ("Mod", df_mod)])
    st_vals = r["df_agg"]["SellThrough"]
    ok = (st_vals >= 0).all()
    return ok, f"SellThrough per snapshot: {st_vals.tolist()}"
run_test("sell-through ≥ 0 su tutti gli snapshot", t_sell_through_non_negativo)

def t_titoli_fermi_threshold():
    df_ref = carica_snapshot(BASE / "stress_ref.csv")
    df_mod = carica_snapshot(BASE / "stress_1a_numeri_misti.csv")
    r = analisi_storica([("Ref", df_ref), ("Mod", df_mod)])
    fermi = r["tit_fermi"]
    ok = (fermi["Pct_Fermo"] >= 0.5).all()
    return ok, f"Titoli fermi trovati: {len(fermi)}, tutti con Pct_Fermo≥0.5: {ok}"
run_test("titoli fermi: tutti con Pct_Fermo ≥ 0.5", t_titoli_fermi_threshold)

def t_delta_editori():
    df_ref = carica_snapshot(BASE / "stress_ref.csv")
    df_mod = carica_snapshot(BASE / "stress_1a_numeri_misti.csv")
    r = analisi_storica([("Ref", df_ref), ("Mod", df_mod)])
    delta = r["df_delta_ed"]
    ok = delta is not None and len(delta) > 0
    return ok, f"Delta editori calcolato: {len(delta) if delta is not None else 'None'} editori"
run_test("delta sell-through editori calcolato (prima vs ultima)", t_delta_editori)


# ══════════════════════════════════════════════════════════════════════════════
# GRUPPO 4 — Casi limite / stress
# ══════════════════════════════════════════════════════════════════════════════
print("\n-- Gruppo 4: Casi limite --")

def t_tutti_giacenza_zero():
    # Costruiamo uno snapshot dove tutte le giacenze sono 0
    df_zero = carica_snapshot(BASE / "stress_ref.csv").copy()
    df_zero["Giacenza"] = 0
    df_ref  = carica_snapshot(BASE / "stress_ref.csv")
    r = analisi_storica([("Ref", df_ref), ("Zero", df_zero)])
    # SellThrough dello snapshot zero deve essere 0.0, non NaN / eccezione
    st_zero = r["df_agg"][r["df_agg"]["Periodo"] == "Zero"]["SellThrough"].iloc[0]
    ok = st_zero == 0.0
    return ok, f"SellThrough snapshot tutto-zero = {st_zero}"
run_test("snapshot con tutte giacenze=0 → SellThrough=0, no crash", t_tutti_giacenza_zero)

def t_zero_titoli_overlap():
    # stress_4a e stress_4b non hanno alcun titolo in comune
    df_4a = carica_snapshot(BASE / "stress_4a_titoli_senza_overlap.csv")
    df_4b = carica_snapshot(BASE / "stress_4b_titoli_senza_overlap.csv")
    r = analisi_storica([("4a", df_4a), ("4b", df_4b)])
    # tit_stats deve essere vuoto (nessun titolo con N_Rilev≥2)
    ok = len(r["tit_stats"]) == 0
    return ok, f"Titoli con N_Rilev≥2 (atteso 0): {len(r['tit_stats'])}"
run_test("stress_4a+4b: zero overlap titoli → nessun titolo cronico, no crash", t_zero_titoli_overlap)

def t_valori_estremi_analisi():
    df_ref  = carica_snapshot(BASE / "stress_ref.csv")
    df_ext  = carica_snapshot(BASE / "stress_2a_estremi.csv")
    r = analisi_storica([("Ref", df_ref), ("Estremi", df_ext)])
    # Valore magazzino non deve essere negativo
    ok = (r["df_agg"]["Valore_Mag"] >= 0).all()
    return ok, f"Valore_Mag per snapshot: {r['df_agg']['Valore_Mag'].tolist()}"
run_test("stress_2a: valori estremi → Valore_Mag ≥ 0 su tutti gli snapshot", t_valori_estremi_analisi)

def t_tre_snapshot():
    df_gen = carica_snapshot(BASE / "storico_gen2024.csv")
    df_apr = carica_snapshot(BASE / "storico_apr2024.csv")
    df_lug = carica_snapshot(BASE / "storico_lug2024.csv")
    r = analisi_storica([("Gen", df_gen), ("Apr", df_apr), ("Lug", df_lug)])
    ok = r["n_snaps"] == 3 and len(r["df_agg"]) == 3
    return ok, f"3 snapshot reali: n_snaps={r['n_snaps']}, agg_rows={len(r['df_agg'])}"
run_test("storico gen/apr/lug 2024: 3 snapshot reali, analisi completa senza crash", t_tre_snapshot)

def t_score_rischio_non_negativo():
    df_gen = carica_snapshot(BASE / "storico_gen2024.csv")
    df_lug = carica_snapshot(BASE / "storico_lug2024.csv")
    r = analisi_storica([("Gen", df_gen), ("Lug", df_lug)])
    fermi = r["tit_fermi"]
    ok = len(fermi) == 0 or (fermi["Score_Rischio"] >= 0).all()
    return ok, f"Score_Rischio ≥ 0: {ok} ({len(fermi)} titoli fermi)"
run_test("score rischio ≥ 0 su tutti i titoli fermi", t_score_rischio_non_negativo)

def t_st_riga_giac_zero():
    # Righe con Giacenza=0 devono avere _ST = NaN, non divisione per zero
    df_ref  = carica_snapshot(BASE / "stress_ref.csv")
    df_mod  = carica_snapshot(BASE / "stress_1a_numeri_misti.csv")
    r = analisi_storica([("Ref", df_ref), ("Mod", df_mod)])
    mask_zero = r["df_all"]["Giacenza"] == 0
    st_zero_rows = r["df_all"].loc[mask_zero, "_ST"]
    ok = st_zero_rows.isna().all()
    return ok, f"Righe con Giac=0: {mask_zero.sum()} → _ST tutti NaN: {ok}"
run_test("righe Giacenza=0 → _ST=NaN (no divisione per zero)", t_st_riga_giac_zero)


# ══════════════════════════════════════════════════════════════════════════════
# RIEPILOGO
# ══════════════════════════════════════════════════════════════════════════════
n_pass = sum(1 for r in results if r[0] == PASS)
n_fail = sum(1 for r in results if r[0] == FAIL)
n_warn = sum(1 for r in results if r[0] == WARN)
n_tot  = len(results)

print(f"\n{'='*70}")
print(f"  RISULTATI: {n_pass}/{n_tot} PASS  |  {n_fail} FAIL  |  {n_warn} WARN")
print(f"{'='*70}")

if n_fail > 0:
    print("\nTest falliti:")
    for tag, name, detail in results:
        if tag == FAIL:
            print(f"  {tag} {name}")
            if detail:
                for line in detail.splitlines():
                    print(f"       {line}")

sys.exit(0 if n_fail == 0 else 1)
