"""
Unit test per bookos_core.py — logica di classificazione magazzino.
Esegui con: pytest tests/
"""
import sys
import os
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from bookos_core import parse_numeric, processa_magazzino


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TODAY = date.today()

def d(days_ago: int) -> str:
    """Restituisce una data in formato dd/mm/yyyy relativa a oggi."""
    return (TODAY - timedelta(days=days_ago)).strftime("%d/%m/%Y")

def default_params():
    """Parametri di default dell'app (finestra 152–182 giorni fa)."""
    soglia_inv = TODAY - timedelta(days=182)
    fs         = TODAY - timedelta(days=182)
    fe         = fs + timedelta(days=30)
    return soglia_inv, fs, fe, 3   # rot_min = 3

def make_df(rows: list[dict]) -> pd.DataFrame:
    """Costruisce un DataFrame con le colonne richieste da processa_magazzino."""
    defaults = {
        "Titolo": "Test",
        "ISBN": "0000000000000",
        "Autore": "Autore",
        "Editore": "Editore",
        "Data_Fatturazione": d(160),
        "Giacenza": 5,
        "Vendute_Ultimi_30_Giorni": 0,
        "Prezzo_Copertina": 20.0,
        "Sconto_Libreria": 3.6,
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


# ---------------------------------------------------------------------------
# parse_numeric
# ---------------------------------------------------------------------------

class TestParseNumeric:
    def test_integer_string(self):
        assert parse_numeric(pd.Series(["5"])).iloc[0] == 5.0

    def test_standard_decimal(self):
        assert parse_numeric(pd.Series(["19.50"])).iloc[0] == pytest.approx(19.50)

    def test_comma_decimal(self):
        # "19,50" → 19.50
        assert parse_numeric(pd.Series(["19,50"])).iloc[0] == pytest.approx(19.50)

    def test_italian_thousands(self):
        # "1.234,56" → 1234.56
        assert parse_numeric(pd.Series(["1.234,56"])).iloc[0] == pytest.approx(1234.56)

    def test_non_numeric_becomes_zero(self):
        assert parse_numeric(pd.Series(["n/d"])).iloc[0] == 0.0

    def test_empty_string_becomes_zero(self):
        assert parse_numeric(pd.Series([""])).iloc[0] == 0.0

    def test_mixed_series(self):
        result = parse_numeric(pd.Series(["10", "3,50", "n/d"]))
        assert list(result) == pytest.approx([10.0, 3.5, 0.0])


# ---------------------------------------------------------------------------
# processa_magazzino — classificazione
# ---------------------------------------------------------------------------

class TestClassificazione:
    def test_libro_da_rendere(self):
        """Fatturato nella finestra, vendite < rot_min → rendere."""
        df = make_df([{"Data_Fatturazione": d(160), "Vendute_Ultimi_30_Giorni": 1, "Giacenza": 5}])
        res = processa_magazzino(df, *default_params())
        assert len(res["rendere"]) == 1
        assert len(res["tenere"])  == 0

    def test_libro_da_tenere(self):
        """Fatturato nella finestra, vendite >= rot_min → tenere."""
        df = make_df([{"Data_Fatturazione": d(160), "Vendute_Ultimi_30_Giorni": 5, "Giacenza": 5}])
        res = processa_magazzino(df, *default_params())
        assert len(res["tenere"])  == 1
        assert len(res["rendere"]) == 0

    def test_libro_scaduto(self):
        """Fatturato prima della soglia_invenduto → scaduto."""
        df = make_df([{"Data_Fatturazione": d(250), "Vendute_Ultimi_30_Giorni": 0, "Giacenza": 10}])
        res = processa_magazzino(df, *default_params())
        assert len(res["scaduto"]) == 1

    def test_libro_recente_non_classificato(self):
        """Fatturato dopo la finestra (< 152 giorni fa) → non in nessuna categoria."""
        df = make_df([{"Data_Fatturazione": d(30), "Vendute_Ultimi_30_Giorni": 0, "Giacenza": 5}])
        res = processa_magazzino(df, *default_params())
        assert len(res["rendere"]) == 0
        assert len(res["tenere"])  == 0
        assert len(res["scaduto"]) == 0

    def test_giacenza_zero_escluso_da_finestra(self):
        """Libro nella finestra ma giacenza 0 → escluso da rendere e tenere."""
        df = make_df([{"Data_Fatturazione": d(160), "Vendute_Ultimi_30_Giorni": 0, "Giacenza": 0}])
        res = processa_magazzino(df, *default_params())
        assert len(res["rendere"]) == 0
        assert len(res["tenere"])  == 0

    def test_mix_rendere_tenere_scaduto(self):
        """Dataset misto: verifica conteggi corretti su più righe."""
        df = make_df([
            {"Data_Fatturazione": d(160), "Vendute_Ultimi_30_Giorni": 1, "Giacenza": 5},   # rendere
            {"Data_Fatturazione": d(170), "Vendute_Ultimi_30_Giorni": 4, "Giacenza": 3},   # tenere
            {"Data_Fatturazione": d(250), "Vendute_Ultimi_30_Giorni": 0, "Giacenza": 8},   # scaduto
            {"Data_Fatturazione": d(30),  "Vendute_Ultimi_30_Giorni": 2, "Giacenza": 5},   # recente
        ])
        res = processa_magazzino(df, *default_params())
        assert len(res["rendere"]) == 1
        assert len(res["tenere"])  == 1
        assert len(res["scaduto"]) == 1


# ---------------------------------------------------------------------------
# processa_magazzino — Valore_Recuperabile
# ---------------------------------------------------------------------------

class TestValoreRecuperabile:
    def test_calcolo_corretto(self):
        """Valore_Recuperabile = (Prezzo_Copertina - Sconto_Libreria) * Giacenza."""
        df = make_df([{
            "Data_Fatturazione": d(160),
            "Vendute_Ultimi_30_Giorni": 0,
            "Giacenza": 10,
            "Prezzo_Copertina": 20.0,
            "Sconto_Libreria": 3.6,
        }])
        res = processa_magazzino(df, *default_params())
        expected = (20.0 - 3.6) * 10   # 164.0
        assert res["rendere"]["Valore_Recuperabile"].iloc[0] == pytest.approx(expected)

    def test_valore_recuperabile_assente_in_tenere(self):
        """I libri 'da tenere' non hanno colonna Valore_Recuperabile."""
        df = make_df([{"Data_Fatturazione": d(160), "Vendute_Ultimi_30_Giorni": 5, "Giacenza": 5}])
        res = processa_magazzino(df, *default_params())
        assert "Valore_Recuperabile" not in res["tenere"].columns


# ---------------------------------------------------------------------------
# processa_magazzino — parsing date
# ---------------------------------------------------------------------------

class TestParsingDate:
    def _run(self, date_str: str):
        df = make_df([{"Data_Fatturazione": date_str, "Vendute_Ultimi_30_Giorni": 0, "Giacenza": 5}])
        return processa_magazzino(df, *default_params())

    def test_formato_italiano(self):
        dt = (TODAY - timedelta(days=160)).strftime("%d/%m/%Y")
        res = self._run(dt)
        assert len(res["rendere"]) == 1

    def test_formato_iso(self):
        dt = (TODAY - timedelta(days=160)).strftime("%Y-%m-%d")
        res = self._run(dt)
        assert len(res["rendere"]) == 1

    def test_formato_trattino(self):
        dt = (TODAY - timedelta(days=160)).strftime("%d-%m-%Y")
        res = self._run(dt)
        assert len(res["rendere"]) == 1

    def test_data_invalida_esclusa_con_warning(self):
        res = self._run("non-una-data")
        assert len(res["warnings"]) >= 1
        assert "non riconoscibile" in res["warnings"][0]
        assert len(res["df"]) == 0

    def test_data_futura_genera_warning(self):
        dt = (TODAY + timedelta(days=30)).strftime("%d/%m/%Y")
        res = self._run(dt)
        assert any("futuro" in w for w in res["warnings"])


# ---------------------------------------------------------------------------
# processa_magazzino — auto-correzione sconto come percentuale
# ---------------------------------------------------------------------------

class TestAutoCorrezioneSconto:
    def test_sconto_percentuale_viene_autocorretto(self):
        """Sconto_Libreria > 5 (mediana) → auto-convertito in euro, segnalato in auto_corrections."""
        df = make_df([{
            "Data_Fatturazione": d(160),
            "Sconto_Libreria": 18,       # 18% — valore tipico da gestionale errato
            "Prezzo_Copertina": 20.0,
        }])
        res = processa_magazzino(df, *default_params())
        assert len(res["auto_corrections"]) == 1
        assert "convertiti automaticamente" in res["auto_corrections"][0]

    def test_valore_recuperabile_corretto_dopo_autocorrezione(self):
        """Dopo auto-correzione, Valore_Recuperabile usa lo sconto convertito in euro."""
        df = make_df([{
            "Data_Fatturazione": d(160),
            "Sconto_Libreria": 18,       # 18%
            "Prezzo_Copertina": 20.0,
            "Giacenza": 10,
            "Vendute_Ultimi_30_Giorni": 0,
        }])
        res = processa_magazzino(df, *default_params())
        # sconto_euro = 20.0 * 18 / 100 = 3.60
        # valore = (20.0 - 3.60) * 10 = 164.0
        assert res["rendere"]["Valore_Recuperabile"].iloc[0] == pytest.approx(164.0)

    def test_sconto_corretto_nessuna_autocorrezione(self):
        """Sconto già in euro (mediana ≤ 5) → nessuna auto-correzione."""
        df = make_df([{"Data_Fatturazione": d(160), "Sconto_Libreria": 3.6}])
        res = processa_magazzino(df, *default_params())
        assert len(res["auto_corrections"]) == 0
        assert not any("percentuale" in w for w in res["warnings"])
