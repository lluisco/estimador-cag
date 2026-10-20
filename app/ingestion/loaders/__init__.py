"""Loaders: productores de bytes.

Un loader enumera ficheros (o URLs, o filas) y entrega pares ``(nombre, bytes)``.
Nunca mira dentro de los bytes: eso es trabajo del parser.
"""

from app.ingestion.loaders.filesystem import FileSystemLoader, LoadedBlob

__all__ = ["FileSystemLoader", "LoadedBlob"]
