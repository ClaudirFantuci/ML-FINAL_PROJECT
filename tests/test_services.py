"""Serviços externos exercitados com respostas locais."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import config
from src.collect import collect_portal
from src.geocode import GeocoderUnavailable, geocode


class ServiceTests(unittest.TestCase):
    def test_partial_collection_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp, patch("src.collect.Fetcher") as factory:
            fetcher = factory.return_value
            fetcher.n_requests, fetcher.failures = 2, 0
            fetcher.get.side_effect = ['<meta name="description" content="2 Casas">', "<html/>"]
            with self.assertRaisesRegex(ValueError, "listings"):
                collect_portal("zap", tmp)
            report = json.loads(next(Path(tmp).rglob("*-relatorio.json")).read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "interrompida")
            self.assertEqual(report["faixas"][0]["obtidos"], 0)

    def test_geocoder_checks_city_and_retries_transient_error(self):
        def response(city):
            return io.BytesIO(json.dumps([{"lat": "-23.3", "lon": "-51.16", "display_name": "Rua A",
                "address": {"city": city, "ISO3166-2-lvl4": "BR-PR"}}]).encode())

        with tempfile.TemporaryDirectory() as tmp, patch.object(config, "MODEL_DIR", tmp), \
             patch("src.geocode.time.sleep"), patch("src.geocode.urlopen") as http:
            http.side_effect = [URLError("offline"), response("Cambé"), response("Londrina")]
            with self.assertRaises(GeocoderUnavailable):
                geocode("Rua A")
            self.assertIsNone(geocode("Rua A"))
            self.assertEqual(geocode("Rua A")[0], -23.3)
            self.assertEqual(geocode("Rua A")[0], -23.3)
            self.assertEqual(http.call_count, 3)
