"""Prepara o CSV do ZAP, treina e abre o servidor Django para uso local."""
import argparse
import hashlib
import json
import os
import runpy
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from django.core.management import execute_from_command_line

from src.dedup import property_key
from src.features import build_features, clean


def prepare_csv(csv_path, dest):
    fields = dict(id="listing_id", cidade="city", estado="state", bairro="neighborhood",
                  rua="street", numero="street_number", tipo_unidade="unit_type", latitude="lat",
                  longitude="lon", preco_venda="price", area_util_m2="usable_area", area_total_m2="total_area",
                  quartos="bedrooms", banheiros="bathrooms", suites="suites", vagas="parking_spaces",
                  condominio="condo_fee", iptu="iptu", amenidades="amenities")
    raw = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, usecols=list(fields)).rename(columns=fields)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    df = raw.copy()
    removed = {}


    def discard(label, mask):
        nonlocal df
        removed[label] = int(mask.sum())
        df = df.loc[~mask].copy()


    discard("fora de Londrina/PR", ~(df.city.str.strip().str.casefold().eq("londrina")
            & df.state.str.strip().str.casefold().isin(["pr", "paraná", "parana"])))
    discard("tipo fora de HOME/CONDOMINIUM", ~df.unit_type.isin(["HOME", "CONDOMINIUM"]))
    discard("ID ausente ou repetido", df.listing_id.isna() | df.listing_id.duplicated())
    for col in ["lat", "lon", "price", "usable_area", "total_area", "bedrooms", "bathrooms",
                "suites", "parking_spaces", "condo_fee", "iptu"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
    discard("coordenadas ausentes ou inválidas", ~(df.lat.between(-90, 90) & df.lon.between(-180, 180)))
    counts = ["bedrooms", "bathrooms", "suites", "parking_spaces"]
    discard("contagens ausentes ou fracionárias", df[counts].isna().any(axis=1) | df[counts].mod(1).ne(0).any(axis=1))
    discard("suítes excedem quartos ou banheiros informados", (df.suites > df.bedrooms) | (df.suites > df.bathrooms))
    before = len(df)
    df = clean(df)
    removed["demais limites do projeto (preço, área, preço/m², cômodos, distância)"] = before - len(df)
    df["property_group"] = df.apply(property_key, axis=1)
    df["portal"] = "zap"
    df["state"] = "PR"


    def amenity_list(value):
        codes = {item.strip().upper() for item in value.split(",") if item.strip()}
        if "POOL" in codes:
            codes.remove("POOL")
            codes.add("SWIMMING_POOL")
        return sorted(codes)


    df["amenities"] = df.amenities.fillna("").map(amenity_list)
    # Somente as colunas sustentadas pela fonte são exportadas.
    for col in ["is_approximate_location", "description", "condominium_name", "floors"]:
        df[col] = None
    df = build_features(df)
    df["in_condominium"] = (df.unit_type.eq("CONDOMINIUM") | df.condo_fee.gt(0)
                            | df.amenities.map(lambda codes: "GATED_COMMUNITY" in codes)).astype(int)
    df.drop(columns=["street", "street_number", "description", "description_len", "condominium_name",
                     "is_approximate_location", "has_exact_address", "floors"], inplace=True)
    df = df.reset_index(drop=True)
    assert len(raw) == sum(removed.values()) + len(df)
    assert df.listing_id.is_unique and df.property_group.nunique() >= 16
    assert "advertiser_name" not in df and "description" not in df
    dest.mkdir(exist_ok=True, parents=True)
    out = dest / "imoveis_londrina"
    df.to_parquet(out.with_suffix(".parquet"), index=False)
    export = df.copy()
    export["amenities"] = export.amenities.map("|".join)
    export.to_csv(out.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    reopened = pd.read_parquet(out.with_suffix(".parquet"))
    equivalent = pd.read_csv(out.with_suffix(".csv"), dtype={"listing_id": str})
    assert list(equivalent.listing_id) == list(reopened.listing_id)
    np.testing.assert_allclose(equivalent.price, reopened.price)
    np.testing.assert_allclose(reopened.price, raw.set_index("listing_id").loc[reopened.listing_id, "price"].astype(float))
    report = {"arquivo_fonte": csv_path.name, "sha256_csv_original": digest,
              "linhas_brutas": len(raw), "tipos_origem": raw.unit_type.value_counts().to_dict(),
              "descartes_sequenciais": removed, "linhas_finais": len(df), "grupos": df.property_group.nunique(),
              "tipos_finais": df.unit_type.value_counts().to_dict(), "bairros": df.neighborhood.nunique(),
              "data_coleta": None, "origem": "ZAP, exportação CSV fornecida pelo usuário",
              "observacoes": ["HOME e CONDOMINIUM interpretados como casas e casas em condomínio.",
                              "A exportação não indica precisão das coordenadas nem data da coleta.",
                              "Comodidades refletem apenas itens declarados. POOL equivale a SWIMMING_POOL.",
                              "A origem pode registrar características não informadas como zero.",
                              "O agrupamento por endereço ou coordenadas limita sobreposição na avaliação."]}
    (dest / "qualidade.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Base preparada: {len(raw)} anúncios lidos, {len(df)} casas válidas.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="CSV original de anúncios do ZAP")
    args = parser.parse_args()
    source = args.csv.resolve(strict=True)
    project = Path(__file__).resolve().parent
    os.chdir(project)
    target = project / "final"
    target.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=target) as tmp:
        prepare_csv(source, Path(tmp))
        for name in ("imoveis_londrina.csv", "imoveis_londrina.parquet", "qualidade.json"):
            os.replace(Path(tmp) / name, target / name)
    runpy.run_path(str(project / "train.py"), run_name="__main__")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ml_final_project.settings")
    execute_from_command_line(["manage.py", "runserver", "127.0.0.1:8000", "--noreload"])


if __name__ == "__main__":
    main()
