# BookStore OS

Toolkit per librai indipendenti italiani. Gestione magazzino, analisi resi, costo scaffale, calcolatore margini, storico comparativo e simulatore ordini.

## Sezioni

### Analisi Resi
Identifica i titoli da rendere al distributore prima che la finestra di resa si chiuda. Classifica il magazzino in *da rendere*, *da tenere* e *invenduto scaduto* in base a soglie configurabili. Calcola il valore recuperabile lordo e netto (al netto dei costi di spedizione). Esclude automaticamente titoli scolastici o stagionali tramite filtro per editore e parole chiave.

### Costo Scaffale
Calcola il costo reale di tenere un libro in magazzino — affitto, utenze, personale — ripartito per copia. Evidenzia i titoli che costano più di quanto rendono.

### Calcolatore Margine
Stima il margine lordo reale di un ordine considerando costi operativi. Valuta la convenienza di ogni acquisizione prima di ordinarla.

### Gestione Usato
Inventario per libri usati in conto vendita. Traccia prezzi, rotazione e marginalità.

### Analisi Storica
Confronta 2 o più snapshot del gestionale per monitorare l'andamento del magazzino nel tempo. Identifica titoli cronicamente fermi, variazioni per editore e proiezione della tendenza in linguaggio semplice.

### Simulatore Ordine
Stima quante copie ordinare di un titolo nuovo basandosi sulla rotazione storica di titoli dello stesso editore.

---

## Formato CSV richiesto

Colonne richieste (i nomi esatti possono variare — l'app include una UI di mappatura):

| Campo canonico | Esempi di nomi alternativi accettati |
|---|---|
| Titolo | titolo |
| Autore | autore, autori |
| Editore | editore |
| ISBN | isbn, ean, codice_isbn |
| Data_Fatturazione | data_acquisto, data_carico, data_ordine |
| Giacenza | stock, quantita, copie |
| Vendute_Ultimi_30_Giorni | vendite, vendite_mese, pezzi_venduti |
| Prezzo_Copertina | prezzo, pvc, listino |
| Sconto_Libreria | sconto, sconto_lib |

Se il gestionale usa nomi diversi da quelli riconosciuti automaticamente, l'app mostra una schermata di abbinamento manuale.

---

## Architettura

```
streamlit_app.py   — UI Streamlit
bookos_core.py     — logica di business pura (senza dipendenze Streamlit)
styles.css         — design system
tests/
  test_core.py     — 27 test unitari per bookos_core
requirements.txt
```

La separazione tra `bookos_core.py` e `streamlit_app.py` permette di testare la logica di classificazione magazzino indipendentemente dalla UI.

---

## Installazione locale

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Test

```bash
pytest tests/
```

## Deploy

L'app è deployata su Streamlit Cloud. Ogni push su `main` triggera il deploy automatico.

---

Fatto da [Andrea Peruca](https://www.linkedin.com/in/andreaperuca) — per feedback o collaborazioni, scrivimi su LinkedIn.
