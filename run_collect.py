"""Coleta os anuncios. Uso: python run_collect.py [zap|vivareal|todos]

Recomendado: apenas 'zap'. ZAP e VivaReal usam o mesmo backend (ver
src/collectors/portals.py) — coletar os dois so duplica trabalho.
"""
import sys

from src.collect import collect_portal

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "zap"
    targets = ["zap", "vivareal"] if which == "todos" else [which]
    for t in targets:
        collect_portal(t)
