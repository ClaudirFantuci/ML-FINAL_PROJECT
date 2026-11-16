"""Geocodificação limitada ao município com cache local de resultados verificados."""
import json
import logging
import os
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import config

_LOCK = threading.Lock()
_last_call = 0.


class GeocoderUnavailable(RuntimeError):
    pass


def geocode(street, city=None, state=None, country="Brasil"):
    global _last_call
    city = city or config.CITY_NAME
    state = state or config.STATE
    query = ", ".join([street, city, state, country])
    key = query.casefold().strip()
    path = Path(config.MODEL_DIR) / "geocode_municipio.json"
    with _LOCK:
        cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if key in cache:
            return cache[key]
        time.sleep(max(0, 1.05 - (time.monotonic() - _last_call)))
        _last_call = time.monotonic()
        params = urlencode({"q": query, "format": "json", "addressdetails": 1,
                            "limit": 1, "countrycodes": "br"})
        req = Request("https://nominatim.openstreetmap.org/search?" + params,
                      headers={"User-Agent": "ML-FINAL_PROJECT/2.0"})
        try:
            with urlopen(req, timeout=15) as response:
                data = json.load(response)
            if not isinstance(data, list):
                raise ValueError("formato inesperado")
            if not data:
                return None
            hit = data[0]
            addr = hit["address"]
            names = [str(addr.get(k, "")).casefold() for k in ("city", "municipality", "town")]
            if city.casefold() not in names or addr.get("ISO3166-2-lvl4") != "BR-" + state:
                return None
            result = (float(hit["lat"]), float(hit["lon"]), hit["display_name"])
        except (URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            logging.getLogger(__name__).warning("geocode_falhou erro=%s", type(exc).__name__)
            raise GeocoderUnavailable("Serviço de endereços temporariamente indisponível.") from exc
        cache[key] = result
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        return result
