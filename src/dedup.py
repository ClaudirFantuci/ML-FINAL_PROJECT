"""Deduplicacao — a etapa que decide se o modelo presta.

Dois niveis:
1. Mesmo anuncio recoletado (mesmo listing_id em dias diferentes) -> fica o
   registro mais recente, mas guardamos quantas vezes foi visto e a variacao
   de preco (vira feature).
2. Mesmo IMOVEL anunciado por imobiliarias diferentes / nos dois portais.
   Sem isso o mesmo sobrado entra varias vezes no dataset, cai no treino E na
   validacao, e a metrica fica otimista e mentirosa.
"""
import hashlib
import re
import unicodedata
import pandas as pd


def collapse_snapshots(df):
    """Nivel 1: colapsa recoletas do mesmo listing_id."""
    df = df[df["listing_id"].notna()].copy()
    df = df.sort_values("collected_at")
    grp = df.groupby("listing_id", sort=False)
    agg = grp.agg(times_seen=("listing_id", "size"),
                  first_seen=("collected_at", "first"),
                  last_seen=("collected_at", "last"),
                  first_price=("price", "first"),
                  price_min_seen=("price", "min"),
                  price_max_seen=("price", "max"))
    out = grp.tail(1).set_index("listing_id").join(agg).reset_index()
    out["price_changed"] = (out["price_max_seen"] != out["price_min_seen"]).astype(int)
    out["price_delta_pct"] = ((out["price"] - out["first_price"])
                              / out["first_price"].replace(0, pd.NA) * 100).round(2)
    print("dedup L1: %d linhas -> %d anuncios unicos" % (len(df), len(out)))
    return out


def normalized(value):
    if pd.isna(value):
        return ""
    plain = unicodedata.normalize("NFKD", str(value).casefold()).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def property_key(row):
    # Agrupamento conservador para avaliação: o mesmo endereço permanece no mesmo conjunto.
    street, number = normalized(row.get("street")), normalized(row.get("street_number"))
    if street and number and number not in {"0", "sn", "s n"}:
        identity = ("address", normalized(row.get("city")), street, number)
    elif pd.notna(row.get("lat")) and pd.notna(row.get("lon")):
        identity = ("location", round(float(row.lat), 4), round(float(row.lon), 4),
                    str(row.get("usable_area")), str(row.get("bedrooms")))
    else:
        identity = ("id", str(row.listing_id))
    return hashlib.sha256(repr(identity).encode()).hexdigest()[:24]


def collapse_duplicates(df, audit_path=None):
    df = df.copy()
    df["property_group"] = df.apply(property_key, axis=1)
    # Endereço completo, ponto exato, atributos e descrição coincidentes são
    # evidências de cópia. Um centroide de bairro sozinho nunca elimina uma linha.
    desc = df.description.map(normalized)
    number = df.street_number.map(normalized)
    reliable = (~df.is_approximate_location.fillna(True).astype(bool)
                & df.street.map(normalized).ne("") & ~number.isin(["", "0", "sn", "s n"])
                & desc.str.len().ge(40)
                & df[["lat", "lon", "usable_area", "bedrooms", "bathrooms"]].notna().all(axis=1))
    df["_description_hash"] = desc.map(lambda s: hashlib.sha256(s.encode()).hexdigest())
    cols = ["property_group", "_description_hash", "usable_area", "bedrooms", "bathrooms"]
    precise = df.loc[reliable].sort_values(["last_seen", "listing_id"], ascending=[False, True]).copy()
    grp = precise.groupby(cols, sort=False)
    precise["_kept"] = grp.listing_id.transform("first")
    precise["n_duplicate_ads"] = grp.listing_id.transform("size")
    precise["first_seen"] = grp.first_seen.transform("min")
    removed = precise.loc[precise.listing_id != precise._kept, ["listing_id", "_kept", "property_group"]]
    if audit_path is not None:
        audit = removed.rename(columns={"_kept": "kept_listing_id"}).copy()
        audit["reason"] = "endereço, descrição e características coincidentes"
        audit.to_csv(audit_path, index=False)
    keep = precise.loc[precise.listing_id == precise._kept]
    out = pd.concat([keep, df.loc[~reliable].assign(n_duplicate_ads=1)], ignore_index=True)
    return out.drop(columns=["_description_hash", "_kept"])
