"""raw/ -> staged/: achata o JSON do portal num schema tabular unico."""
import glob
import json
import os
import re

import pandas as pd


_RSC_REF = re.compile(r"^\$[0-9a-f]{1,4}$")


def sanitize_rsc(node):
    """Remove os sentinelas do protocolo RSC do payload.

    O flight payload do Next.js nao e JSON puro: ele codifica `undefined` do
    JavaScript como a string "$undefined", e usa "$2e", "$1f" etc. como
    REFERENCIAS a outros chunks. Nenhum dos dois e dado. Sem essa limpeza,
    campos vem como a string "$undefined" em vez de nulo — e um `.get()` em
    cima disso estoura.
    """
    if isinstance(node, dict):
        return {k: sanitize_rsc(v) for k, v in node.items()}
    if isinstance(node, list):
        return [sanitize_rsc(v) for v in node]
    if isinstance(node, str) and (node == "$undefined" or _RSC_REF.match(node)):
        return None
    return node


def _first(seq):
    """amenities vem como lista (ex.: usableAreas: [100]). Pega o 1o valor util."""
    if isinstance(seq, list):
        return seq[0] if seq else None
    return seq


def flatten(listing, meta):
    listing = sanitize_rsc(listing)
    prices = listing.get("prices") or {}
    sale = prices.get("sale") or {}
    addr = listing.get("address") or {}
    coords = addr.get("coordinates") or {}
    am = listing.get("amenities") or {}
    adv = listing.get("advertiser") or {}

    return {
        "listing_id": listing.get("id"),
        "portal": meta["portal"],
        "external_id": listing.get("externalId"),
        "collected_at": meta["collected_at"],
        "url": listing.get("href"),

        "price": sale.get("value"),
        "iptu": sale.get("iptu"),
        "condo_fee": sale.get("condominium"),

        "usable_area": _first(am.get("usableAreas")),
        "total_area": _first(am.get("totalAreas")),
        "bedrooms": _first(am.get("bedrooms")),
        "bathrooms": _first(am.get("bathrooms")),
        "suites": _first(am.get("suites")),
        "parking_spaces": _first(am.get("parkingSpaces")),
        "floors": _first(am.get("floors")),
        "amenities": sorted(am.get("values") or []),

        "street": addr.get("street") or None,
        "street_number": addr.get("streetNumber") or None,
        "neighborhood": addr.get("neighborhood") or None,
        "city": addr.get("city"),
        "state": addr.get("stateAcronym"),
        "lat": coords.get("latitude"),
        "lon": coords.get("longitude"),
        "is_approximate_location": addr.get("isApproximateLocation"),
        "location_id": addr.get("locationId"),

        "unit_type": listing.get("unitType"),
        "listing_type": listing.get("listingType"),
        "construction_status": listing.get("constructionStatus"),
        "publication_type": listing.get("publicationType"),
        "condominium_name": listing.get("condominiumName") or None,
        "display_address_type": listing.get("displayAddressType"),

        "advertiser_id": adv.get("id"),
        "advertiser_name": adv.get("name"),
        "advertiser_tier": adv.get("tier"),

        "title": listing.get("title"),
        "description": listing.get("description"),
    }


def load_raw(raw_root="raw"):
    rows = []
    files = sorted(glob.glob(os.path.join(raw_root, "*", "*", "*.json")))
    for path in files:
        with open(path, encoding="utf-8") as fh:
            blob = json.load(fh)
        meta = {"portal": blob["portal"], "collected_at": blob["collected_at"]}
        rows.extend(flatten(x, meta) for x in blob["listings"])
    print("normalize: %d arquivos -> %d linhas brutas" % (len(files), len(rows)))
    return pd.DataFrame(rows)
