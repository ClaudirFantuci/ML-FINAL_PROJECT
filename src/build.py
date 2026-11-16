"""Gera as tabelas locais e o relatório de qualidade."""
import json
import numpy as np
import pandas as pd
from pathlib import Path

from src.dedup import collapse_duplicates, collapse_snapshots
from src.features import build_features, clean
from src.normalize import load_raw


def build(raw_root="raw", staged="staged", final="final"):
    staged, final = Path(staged), Path(final)
    staged.mkdir(parents=True, exist_ok=True)
    final.mkdir(parents=True, exist_ok=True)
    raw = load_raw(raw_root)
    if raw.empty:
        print("Nenhuma página encontrada em raw/.")
        return None
    for col in ["price", "usable_area", "lat", "lon", "bedrooms", "bathrooms", "suites", "parking_spaces", "floors"]:
        raw[col] = pd.to_numeric(raw[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
    essential = ["listing_id", "price", "usable_area", "lat", "lon"]
    quality = {"linhas_brutas": len(raw), "origens": raw.portal.value_counts().to_dict(),
               "inicio_coleta": raw.collected_at.min(), "fim_coleta": raw.collected_at.max(),
               "fracao_nula": raw[essential].isna().mean().to_dict()}
    quality["alertas"] = [f"{name}: mais de 10% de valores ausentes"
                          for name, rate in quality["fracao_nula"].items() if rate > .1]
    df = collapse_snapshots(raw)
    quality["anuncios_unicos"] = len(df)
    if df.empty:
        raise ValueError("Nenhum anúncio com identificador utilizável nas páginas locais.")
    df = collapse_duplicates(df, staged / "auditoria_duplicatas.csv")
    quality["apos_deduplicacao"] = len(df)
    df.drop(columns=["advertiser_name", "advertiser_id", "advertiser_tier"], inplace=True, errors="ignore")
    df.to_parquet(staged / "listings.parquet", index=False)
    df = build_features(clean(df))
    # Texto livre pode incluir telefones. Mantemos atributos derivados e o grupo anonimizado.
    df.drop(columns=["description", "title", "url", "street", "street_number", "external_id",
                     "condominium_name"], errors="ignore", inplace=True)
    quality["linhas_finais"] = len(df)
    (final / "qualidade.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    df.to_parquet(final / "imoveis_londrina.parquet", index=False)
    csv = df.copy()
    csv["amenities"] = csv.amenities.map(lambda v: "|".join(v) if isinstance(v, list) else "")
    csv.to_csv(final / "imoveis_londrina.csv", index=False, encoding="utf-8-sig")
    for alert in quality["alertas"]:
        print("Atenção:", alert)
    print(f"{len(df)} imóveis em {final}")
    return df
