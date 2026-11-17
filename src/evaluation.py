"""Separação independente por imóvel, com teste temporal quando há histórico."""
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

import config
from src.dedup import property_key


def groups(df):
    if "property_group" in df and df.property_group.notna().all():
        return df.property_group.astype(str)
    return df.apply(property_key, axis=1)


def holdout(df, fraction):
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=fraction,
                  random_state=config.RANDOM_STATE).split(df, groups=groups(df)))
    return df.iloc[tr], df.iloc[te]


def evaluation_split(df):
    ids = groups(df)
    if "collected_at" in df:
        first = pd.to_datetime(df.get("first_seen", df.collected_at), utc=True, errors="coerce")
        last = pd.to_datetime(df.get("last_seen", df.collected_at), utc=True, errors="coerce")
        if first.notna().all() and last.notna().all():
            first = first.groupby(ids).transform("min").dt.floor("D")
            last = last.groupby(ids).transform("max").dt.floor("D")
            dates = first.drop_duplicates().sort_values()
            if len(dates) > 1:
                cutoff = max(first.sort_values().iloc[int(.8 * len(first))], dates.iloc[1])
                tr, te = df.loc[last < cutoff], df.loc[first >= cutoff]
                if ids.loc[tr.index].nunique() >= 12 and ids.loc[te.index].nunique() >= 2:
                    return tr, te, {"tipo": "temporal", "corte": cutoff.isoformat(),
                                    "expurgados": len(df) - len(tr) - len(te)}
    tr, te = holdout(df, .2)
    return tr, te, {"tipo": "por imóvel", "temporal": "histórico insuficiente"}


def spatial_blocks(df):
    coords = df[["lat", "lon"]].groupby(groups(df)).transform("median")
    cells = np.floor(coords / .02).astype(int)
    return cells.lat.astype(str) + "/" + cells.lon.astype(str)
