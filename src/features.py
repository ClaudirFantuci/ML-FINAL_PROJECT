"""Limpeza + engenharia de atributos para regressao e clustering."""
import numpy as np
import pandas as pd

import config

AMENITY_WHITELIST = [
    "BARBECUE_GRILL", "SWIMMING_POOL", "AIR_CONDITIONING", "FURNISHED",
    "BACKYARD", "GARDEN", "GOURMET_SPACE", "BALCONY", "CLOSET", "LAUNDRY",
    "SERVICE_AREA", "ELECTRIC_GENERATOR", "NEAR_SCHOOL", "NEAR_SHOPPING_CENTER",
    "NEAR_PUBLIC_TRANSPORT", "PETS_ALLOWED",
]


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def clean(df):
    """Remove o que nao e observacao valida de preco de casa."""
    n0 = len(df)
    df = df[df["price"].notna() & (df["price"] > 0)]              # "sob consulta"
    df = df[df["usable_area"].notna() & (df["usable_area"] > 0)]
    df = df[df["lat"].notna() & df["lon"].notna()]
    df = df[df.price.between(*config.CLEAN_LIMITS["price"])]
    df = df[df.usable_area.between(*config.CLEAN_LIMITS["usable_area"])]

    ppsm = df["price"] / df["usable_area"]
    df = df[ppsm.between(*config.CLEAN_LIMITS["price_per_sqm"])]

    for col in ("bedrooms", "bathrooms", "suites", "parking_spaces"):
        df = df[df[col].fillna(0).between(*config.CLEAN_LIMITS[col])]

    clat, clon = config.CITY_CENTER
    df = df[haversine_km(df["lat"], df["lon"], clat, clon) <= config.MAX_DIST_CENTER_KM]
    print("clean: %d -> %d linhas (%d descartadas)" % (n0, len(df), n0 - len(df)))
    return df.copy()


def build_features(df):
    df = df.copy()

    # --- alvo -----------------------------------------------------------
    df["price_per_sqm"] = (df["price"] / df["usable_area"]).round(2)
    df["log_price"] = np.log(df["price"])          # alvo preferido: cauda longa

    # --- geografia -------------------------------------------------------
    clat, clon = config.CITY_CENTER
    df["dist_center_km"] = haversine_km(df["lat"], df["lon"], clat, clon).round(3)
    df["has_exact_address"] = (~df["is_approximate_location"].fillna(True)).astype(int)
    df["has_street"] = df["street"].notna().astype(int)

    # --- estrutura -------------------------------------------------------
    for c in ["bedrooms", "bathrooms", "suites", "parking_spaces", "floors"]:
        df[c] = df[c].fillna(0).astype(int)
    df["rooms_total"] = df["bedrooms"] + df["bathrooms"]
    df["bath_per_bed"] = (df["bathrooms"] / df["bedrooms"].replace(0, np.nan)).round(3)
    df["area_per_bedroom"] = (df["usable_area"] / df["bedrooms"].replace(0, np.nan)).round(2)
    df["has_suite"] = (df["suites"] > 0).astype(int)

    # --- custos recorrentes ---------------------------------------------
    # CUIDADO: o portal manda 0 quando o anunciante nao informou, nao quando o
    # imovel e isento. Tratar isso como zero real puxaria a media para baixo e
    # criaria um preditor falso. Guardamos o valor como NaN + uma flag de
    # "informado".
    iptu = pd.to_numeric(df["iptu"], errors="coerce")
    condo = pd.to_numeric(df["condo_fee"], errors="coerce")
    df["iptu_informed"] = (iptu > 0).astype(int)
    df["condo_informed"] = (condo > 0).astype(int)
    df["iptu"] = iptu.where(iptu > 0)
    df["condo_fee"] = condo.where(condo > 0)
    df["in_condominium"] = ((condo > 0) | df["condominium_name"].notna()).astype(int)

    # --- comodidades ------------------------------------------------------
    am = df["amenities"].apply(lambda v: v if isinstance(v, (list, tuple)) else [])
    df["n_amenities"] = am.apply(len)
    for a in AMENITY_WHITELIST:
        df["am_" + a.lower()] = am.apply(lambda v, a=a: int(a in v))

    # --- bairro ------------------------------------------------------------
    # Estatistica por bairro e o preditor mais forte num modelo hedonico, mas
    # e calculada aqui sobre o dataset todo -> use apenas para EDA e
    # clustering. Para a regressao, quem entra no modelo e a zona do K-Means
    # (one-hot), nao a mediana do bairro, para nao vazar o alvo.
    nb = df.groupby("neighborhood")["price_per_sqm"]
    df["nb_listings"] = nb.transform("size")
    df["nb_median_ppsm"] = nb.transform("median").round(2)
    df["nb_is_rare"] = (df["nb_listings"] < 5).astype(int)

    df["description_len"] = df["description"].fillna("").str.len()
    return df


CLUSTER_FEATURES = [
    "log_price", "price_per_sqm", "usable_area", "bedrooms", "bathrooms",
    "suites", "parking_spaces", "dist_center_km", "n_amenities", "in_condominium",
]
