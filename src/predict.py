"""Estimativa de preco para um imovel descrito pelo usuario."""
import json
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import config
from src.features import haversine_km
from src.geocode import geocode
from src.model import infer

class ModelUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=2)
def _load_release(path):
    meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    return {"bundle": joblib.load(path / "modelo.joblib"), "meta": meta,
            "pontos": pd.read_parquet(path / "pontos.parquet")}


def load_artifacts(model_dir=None):
    root = Path(model_dir or config.MODEL_DIR).resolve()
    try:
        release = (root / "CURRENT").read_text(encoding="utf-8").strip()
        return _load_release(root / release)
    except FileNotFoundError as exc:
        raise ModelUnavailable("Para habilitar as estimativas, gere a base e execute train.py.") from exc


def estimar_preco(endereco=None, lat=None, lon=None, usable_area=100,
                  bedrooms=3, bathrooms=2, suites=1, parking_spaces=1,
                  n_amenities=0, in_condominium=0):
    """Estima o preco. Aceita endereco (sera geocodificado) ou lat/lon direto."""
    art = load_artifacts()
    bundle, meta, pontos = art["bundle"], art["meta"], art["pontos"]

    label = None
    if lat is None or lon is None:
        if not endereco:
            return {"erro": "informe um endereço ou coordenadas"}
        hit = geocode(endereco)
        if not hit:
            return {"erro": "não consegui localizar '%s' em %s" % (endereco, config.CITY_NAME)}
        lat, lon, label = hit

    clat, clon = config.CITY_CENTER
    dist = float(haversine_km(np.array([lat]), np.array([lon]), clat, clon)[0])
    if dist > config.MAX_DIST_CENTER_KM:
        return {"erro": "esse endereço está a %.0f km do centro — fora de %s"
                        % (dist, config.CITY_NAME)}

    row = pd.DataFrame([{
        "lat": lat, "lon": lon, "usable_area": float(usable_area),
        "bedrooms": bedrooms, "bathrooms": bathrooms, "suites": suites,
        "parking_spaces": parking_spaces, "dist_center_km": round(dist, 3),
        "n_selected_amenities": n_amenities, "in_condominium": in_condominium,
    }])
    logs, zones = infer(bundle, row)
    zone = int(zones[0])
    preco = float(np.exp(logs[0]))
    p10 = float(np.exp(logs[0] - bundle["log_radius"]))
    p90 = float(np.exp(logs[0] + bundle["log_radius"]))

    # quantos imoveis reais existem perto? pouco = extrapolacao, aviso obrigatorio
    d = haversine_km(pontos["lat"].to_numpy(), pontos["lon"].to_numpy(), lat, lon)
    vizinhos_1km = int((d <= 1.0).sum())
    vizinhos_2km = int((d <= 2.0).sum())

    if vizinhos_1km >= 30:
        confianca, aviso = "alta", None
    elif vizinhos_2km >= 20:
        confianca, aviso = "média", "Poucos imóveis num raio de 1 km; a estimativa apoia-se na região."
    else:
        confianca = "baixa"
        aviso = ("Só %d imóveis num raio de 2 km deste ponto. O modelo está "
                 "extrapolando — trate o valor como ordem de grandeza." % vizinhos_2km)

    zinfo = next((z for z in meta["zone_stats"] if z["zone"] == zone), {})
    return {
        "preco": preco, "p10": p10, "p90": p90,  # aliases históricos da API
        "intervalo_min": p10, "intervalo_max": p90,
        "preco_m2": preco / float(usable_area),
        "lat": lat, "lon": lon, "endereco_encontrado": label,
        "zona": zone,
        "zona_bairros": zinfo.get("top_neighborhoods", []),
        "zona_mediana": zinfo.get("median_price"),
        "zona_ppsm": zinfo.get("median_ppsm"),
        "vizinhos_1km": vizinhos_1km, "vizinhos_2km": vizinhos_2km,
        "confianca": confianca, "aviso": aviso,
    }
