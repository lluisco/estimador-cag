"""Sesión 7 — pipeline de embeddings.

Convierte los presupuestos históricos (JSON normalizado) en vectores: un chunker
estructural (un componente del presupuesto = un chunk) más un embedder de OpenAI.
Los vectores se generan en memoria y se devuelven por HTTP; la persistencia en una
base vectorial llega en la sesión 8.
"""
