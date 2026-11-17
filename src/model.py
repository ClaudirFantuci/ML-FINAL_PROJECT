"""Treinamento, calibração conformal e avaliação do preço anunciado."""
import hashlib
import json
import math
import os
import platform
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score, silhouette_score
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import KNeighborsRegressor
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

import config
from src.evaluation import evaluation_split, groups, holdout, spatial_blocks

FEATURES = ["usable_area", "bedrooms", "bathrooms", "suites", "parking_spaces",
            "dist_center_km", "n_selected_amenities", "in_condominium"]


def coordinates(df):
    # Projeção local em km preserva a escala relativa dos eixos.
    factors = [111.2, 111.2 * np.cos(np.radians(config.CITY_CENTER[0]))]
    return (df[["lat", "lon"]].to_numpy() - config.CITY_CENTER) * factors


def prepare(df):
    xy = coordinates(df)
    distinct = len(np.unique(xy, axis=0))
    best, best_score = None, -np.inf
    sample = np.random.default_rng(config.RANDOM_STATE).choice(len(xy), min(2000, len(xy)), replace=False)
    for k in config.N_CLUSTERS_RANGE:
        if k > distinct or k >= len(df):
            continue
        km = KMeans(k, n_init=5, random_state=config.RANDOM_STATE).fit(xy)
        labels = km.labels_[sample]
        if 1 < len(np.unique(labels)) < len(sample):
            score = silhouette_score(xy[sample], labels)
            if score > best_score:
                best, best_score = km, score
    if best is None:
        best = KMeans(1, n_init=1, random_state=config.RANDOM_STATE).fit(xy)
    return {"km": best, "scale": StandardScaler().fit(df[FEATURES])}


def matrices(prep, df):
    numeric = prep["scale"].transform(df[FEATURES])
    zone = prep["km"].predict(coordinates(df))
    return numeric, np.eye(prep["km"].n_clusters)[zone], zone


def design(parts, zone_weight):
    if zone_weight == 0:
        return parts[0]
    return np.column_stack((parts[0], parts[1] * zone_weight))


def metrics(truth, pred):
    return {"mae": float(mean_absolute_error(truth, pred)),
            "mape": float(np.mean(np.abs(pred - truth) / truth) * 100),
            "r2": float(r2_score(truth, pred)) if len(truth) > 1 else None}


def tune_knn(train):
    blocks = spatial_blocks(train)
    spatial = blocks.nunique() >= 2
    ids = blocks if spatial else groups(train)
    folds = list(GroupKFold(min(5, ids.nunique())).split(train, groups=ids))
    smallest = min(len(tr) for tr, _ in folds)
    ks = [k for k in config.KNN_K_GRID if k <= smallest] or [1]
    errors = {}
    for tr, va in folds:
        fit, val = train.iloc[tr], train.iloc[va]
        prep = prepare(fit)
        a, b = matrices(prep, fit), matrices(prep, val)
        for w in (0., .5, 1.):
            x, xv = design(a, w), design(b, w)
            for k in ks:
                for weights in ("distance", "uniform"):
                    spec = (k, weights, w)
                    model = KNeighborsRegressor(k, weights=weights).fit(x, np.log(fit.price))
                    pred = np.exp(model.predict(xv))
                    errors[spec] = errors.get(spec, 0.) + float(np.abs(val.price - pred).sum())
    scores = [{"k": k, "pesos": weights, "peso_zona": w, "mae": err / len(train)}
              for (k, weights, w), err in errors.items()]
    return min(errors, key=errors.get), {"tipo": "blocos espaciais" if spatial else "por imóvel",
                                         "folds": len(folds), "resultados": scores}


def infer(bundle, df):
    parts = matrices(bundle["prep"], df)
    return bundle["knn"].predict(design(parts, bundle["zone_weight"])), parts[2]


def code_hash():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted([root / "config.py", root / "train.py", *(root / "src").rglob("*.py")]):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


@threadpool_limits.wrap(limits=1)
def train(df, model_dir=None, dataset_sha256=None, quality=None):
    df = df.reset_index(drop=True).copy()
    cols = ["am_" + code.lower() for code, _ in config.AMENIDADES]
    df["n_selected_amenities"] = df[cols].sum(axis=1)
    if groups(df).nunique() < 16:
        raise ValueError("São necessários ao menos 16 grupos de imóveis para treino, calibração e teste.")
    dev, test, split = evaluation_split(df)
    fit, cal = holdout(dev, max(.2, 4 / groups(dev).nunique()))
    (k, weights, zone_weight), cv = tune_knn(fit)
    prep = prepare(fit)
    a, b = matrices(prep, fit), matrices(prep, test)
    knn = KNeighborsRegressor(k, weights=weights).fit(design(a, zone_weight), np.log(fit.price))
    bundle = {"prep": prep, "knn": knn, "zone_weight": zone_weight}
    cal_logs, _ = infer(bundle, cal)
    residuals = (np.log(cal.price) - cal_logs).abs().groupby(groups(cal)).max()
    rank = math.ceil(.8 * (len(residuals) + 1))
    radius = float(np.sort(residuals)[rank - 1])
    bundle["log_radius"] = radius
    logs, _ = infer(bundle, test)
    comparisons = {
        "KNN": metrics(test.price, np.exp(logs)),
        "Mediana": metrics(test.price, np.full(len(test), fit.price.median())),
        "Mediana por m²": metrics(test.price, test.usable_area * (fit.price / fit.usable_area).median()),
    }
    for name, model in [("Ridge", Ridge()), ("HistGradientBoosting", HistGradientBoostingRegressor(
            random_state=config.RANDOM_STATE, early_stopping=False))]:
        model.fit(design(a, 1), np.log(fit.price))
        comparisons[name] = metrics(test.price, np.exp(model.predict(design(b, 1))))
    points = fit[["lat", "lon", "price", "usable_area", "neighborhood"]].copy()
    points["zone"] = a[2]
    stats = []
    for zone, rows in points.groupby("zone"):
        stats.append({"zone": int(zone), "median_price": float(rows.price.median()),
                      "median_ppsm": float((rows.price / rows.usable_area).median()),
                      "top_neighborhoods": rows.neighborhood.value_counts().head(3).index.tolist()})
    lower, upper = np.exp(logs - radius), np.exp(logs + radius)
    meta = {"schema": 2, "projeto": "ML-FINAL_PROJECT", "algorithm": "KNN",
            "alvo": "preço anunciado", "created_at": datetime.now(timezone.utc).isoformat(),
            "n_train": len(fit), "n_calibration": len(cal), "n_test": len(test), "split": split,
            "k": int(prep["km"].n_clusters), "knn_best_k": k, "weights": weights, "zone_weight": zone_weight,
            "zone_stats": stats, "metrics": comparisons["KNN"], "comparacao_teste": comparisons,
            "validacao_interna": cv, "intervalo": {"alvo_pct": 80,
            "cobertura_teste_pct": float(test.price.between(lower, upper).mean() * 100),
            "largura_media_reais": float(np.mean(upper - lower))},
            "limites_limpeza": config.CLEAN_LIMITS, "raio_km": config.MAX_DIST_CENTER_KM,
            "features": FEATURES, "resumo_treino": fit[FEATURES].describe().to_dict(),
            "semente": config.RANDOM_STATE, "dataset_sha256": dataset_sha256,
            "codigo_sha256": code_hash(), "qualidade_dados": quality, "python": platform.python_version(),
            "versoes": {p: version(p) for p in ["numpy", "pandas", "scikit-learn", "pyarrow", "joblib"]}}
    root = Path(model_dir or config.MODEL_DIR)
    root.mkdir(parents=True, exist_ok=True)
    release = Path(tempfile.mkdtemp(prefix="treino-", dir=root))
    joblib.dump(bundle, release / "modelo.joblib")
    points.to_parquet(release / "pontos.parquet", index=False)
    (release / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    pointer = root / (release.name + ".tmp")
    pointer.write_text(release.name, encoding="utf-8")
    os.replace(pointer, root / "CURRENT")
    print(f"Treino {release.name} | {len(test)} imóveis de teste | MAE KNN R$ {comparisons['KNN']['mae']:,.0f}")
    return meta
