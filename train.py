"""Treina e registra a proveniência do dataset usado."""
import hashlib
import json
from pathlib import Path

import pandas as pd
from src.model import train

if __name__ == "__main__":
    data = Path("final/imoveis_londrina.parquet")
    if not data.exists():
        raise SystemExit("Falta o dataset final. Execute run_build.py com anúncios locais.")
    report = data.with_name("qualidade.json")
    quality = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
    with data.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    train(pd.read_parquet(data), dataset_sha256=digest, quality=quality)
