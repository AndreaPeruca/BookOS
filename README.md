# BookStore OS

Toolkit completo per librai indipendenti. Gestione intelligente del magazzino con analisi predittiva e simulazione ordini.

## 🚀 Features

### 📦 Radar Salva-Cassa
Analizza il tuo magazzino per identificare libri invenduti e con rotazione critica. Calcola il valore bloccato in giacenza e ottimizza le decisioni di resa.

### 🧮 Calcolatore Margine
Stima il margine lordo reale di un ordine considerando costi operativi (affitto, utenze, personale, altri). Valuta la convenienza di ogni acquisizione.

### 📚 Gestione Usato
Gestisci il tuo inventario di libri usati con sistema "conto vendita". Traccia prezzi, rotazione e marginalità con semplicità.

### 📊 Analisi Storica
Confronta snapshot storici del tuo magazzino per monitorare trend di vendita e giacenza. Identifica pattern stagionali e opportunità.

### 📈 Simulatore Ordine
Stima quante copie ordinare di un titolo nuovo, basandosi sulla rotazione storica di titoli dello stesso editore.

## 📋 Requisiti Dati

I CSV devono contenere queste colonne:
- **Titolo** - Nome del libro
- **Autore** - Autore del libro
- **Editore** - Casa editrice
- **ISBN** - Codice ISBN
- **Data_Fatturazione** - Data di acquisto (gg/mm/aaaa)
- **Giacenza** - Copie in magazzino
- **Vendute_Ultimi_30_Giorni** - Vendite ultimi 30 giorni
- **Prezzo_Copertina** - Prezzo di listino (€)
- **Sconto_Libreria** - Sconto editore applicato (€)

## 🔧 Installazione

```bash
pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

## 📦 Dipendenze

- streamlit >= 1.32.0
- pandas >= 2.2.0
- plotly >= 5.22.0
- anthropic >= 0.25.0

## 🎯 Utilizzo Rapido

1. **Carica il CSV** dal tuo gestionale (Radar Salva-Cassa)
2. **Seleziona la sezione** dal dropdown in alto a sinistra
3. **Analizza i dati** e prendi decisioni informate
4. **Esporta i risultati** se necessario

## 🚀 Deploy su Streamlit Cloud

```bash
git push origin main
```

L'app si deploya automaticamente su: https://share.streamlit.io

## 📝 Note Tecniche

- **Cache dati** per performance ottimale
- **Validazione robusta** dei file CSV
- **Grafici interattivi** con Plotly (stile Economist)
- **Responsive design** per desktop

## 📧 Support

Per problemi o suggerimenti, consulta la documentazione del codice o contatta lo sviluppatore.

---

**BookStore OS v3.1** - Toolkit per librai indipendenti
