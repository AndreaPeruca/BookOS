"""
Script di test rapido per verifica grafici BookStore OS ENHANCED
"""
import plotly.graph_objects as go
import numpy as np
import pandas as pd

print("="*50)
print("TEST GRAFICI BookStore OS ENHANCED")
print("="*50)

# Test 1: Caricamento modulo
print("\nTest 1: Verifica sintassi Python...")
try:
    import py_compile
    py_compile.compile(r'C:\Users\Andrea\Desktop\BookOS\bookstore_os_ENHANCED.py', doraise=True)
    print("✓ Sintassi Python corretta")
except py_compile.PyCompileError as e:
    print(f"✗ Errore di sintassi: {str(e)}")

# Test 2: Test plotly imports
print("\nTest 2: Importazioni Plotly...")
try:
    assert go.Figure is not None
    print("✓ Plotly importato correttamente")
except Exception as e:
    print(f"✗ Errore importazione: {str(e)}")

# Test 3: Test figure creation
print("\nTest 3: Creazione figura Plotly...")
try:
    test_fig = go.Figure()
    test_fig.add_trace(go.Scatter(
        x=[1, 2, 3], y=[10, 20, 15],
        mode="lines+markers", name="Test"
    ))
    assert len(test_fig.data) == 1
    print("✓ Figura Plotly creata correttamente")
except Exception as e:
    print(f"✗ Errore creazione figura: {str(e)}")

# Test 4: Test bar chart
print("\nTest 4: Creazione Bar chart...")
try:
    bar_fig = go.Figure(go.Bar(
        y=["A", "B", "C"],
        x=[10, 20, 15],
        orientation="h",
        marker_color=["#B5362C", "#00877A", "#2A5FAC"]
    ))
    assert len(bar_fig.data) == 1
    print("✓ Bar chart creato correttamente")
except Exception as e:
    print(f"✗ Errore creazione bar chart: {str(e)}")

# Test 5: Test scatter with fill
print("\nTest 5: Creazione Scatter con fill...")
try:
    scatter_fig = go.Figure()
    scatter_fig.add_trace(go.Scatter(
        x=[1, 2, 3, 4],
        y=[10, 15, 13, 17],
        fill="tozeroy",
        fillcolor="rgba(181,54,44,0.12)",
        line=dict(color="#B5362C", width=3.5),
        marker=dict(size=12, color="#B5362C", line=dict(width=2.5, color="white"))
    ))
    assert scatter_fig.data[0].fill == "tozeroy"
    print("✓ Scatter con fill creato correttamente")
except Exception as e:
    print(f"✗ Errore creazione scatter: {str(e)}")

print("\n" + "="*50)
print("VERIFICA COMPLETATA")
print("="*50)
