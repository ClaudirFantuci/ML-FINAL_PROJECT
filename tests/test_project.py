import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import django
import pandas as pd
from django.core.cache import cache
from django.test import Client, SimpleTestCase, override_settings

import config
from src.build import build
from src.evaluation import evaluation_split, groups, holdout
from src.features import haversine_km
from src.flight import extract_listings
from src.model import train
from src.normalize import sanitize_rsc
from src.predict import estimar_preco, load_artifacts

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ml_final_project.settings")
django.setup()


def listing(i):
    return {"id": str(i), "prices": {"sale": {"value": 120000 + 3000*i}},
            "address": {"street": "Rua de teste", "streetNumber": str(i+1), "city": "Londrina",
                        "neighborhood": "Bairro simulado", "isApproximateLocation": False,
                        "coordinates": {"latitude": -23.30 + i%7 * .009, "longitude": -51.16 + i%5 * .011}},
            "amenities": {"usableAreas": [60+i], "bedrooms": [3], "bathrooms": [2],
                          "values": ["GARDEN", "LAUNDRY"]},
            "description": "Descrição inteiramente fictícia para confirmar a regra de duplicação.",
            "advertiser": {"name": "Anunciante de teste", "id": "id-teste"}}


class PipelineTests(unittest.TestCase):
    def test_parser(self):
        payload = json.dumps({"listings": [{"id": "abc", "title": "casa [2]"}]})
        html = "".join("self.__next_f.push([1," + json.dumps(s) + "])" for s in [payload[:8], payload[8:]])
        self.assertEqual(extract_listings(html)[0]["id"], "abc")
        with self.assertRaises(ValueError):
            extract_listings("<html/>")
        self.assertEqual(sanitize_rsc(["$undefined", "$2e", "texto"]), [None, None, "texto"])
        self.assertAlmostEqual(haversine_km(-23., -51., -23., -51.), 0.)

    def test_splits(self):
        df = pd.DataFrame({"property_group": [str(i//2) for i in range(60)],
                           "collected_at": pd.date_range("2025-01-01", periods=60, tz="UTC")})
        dev, test, info = evaluation_split(df)
        fit, cal = holdout(dev, .25)
        self.assertEqual(info["tipo"], "temporal")
        self.assertLess(dev.collected_at.max(), test.collected_at.min())
        for a, b in [(fit, cal), (fit, test), (cal, test)]:
            self.assertFalse(set(groups(a)) & set(groups(b)))

    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_build_train_serve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "raw" / "zap" / "2025-01-01"
            pages.mkdir(parents=True)
            rows = [listing(i) for i in range(50)]
            exact = dict(listing(1), id="copy")
            approx = listing(1)
            approx["id"] = "approx"
            approx["address"]["isApproximateLocation"] = True
            invalid = listing(60)
            invalid["address"]["coordinates"] = {}
            rows.extend([exact, approx, invalid, listing(1)])
            (pages / "page.json").write_text(json.dumps({"portal": "zap",
                "collected_at": "2025-01-01T00:00:00Z", "listings": rows}), encoding="utf-8")
            df = build(root / "raw", root / "staged", root / "final")
            self.assertEqual(len(df), 51)
            self.assertEqual(len(pd.read_csv(root / "staged/auditoria_duplicatas.csv")), 1)
            self.assertFalse(set(["advertiser_name", "description", "street_number"]) & set(df.columns))
            self.assertTrue((df.dist_center_km <= config.MAX_DIST_CENTER_KM).all())
            with patch.object(config, "MODEL_DIR", str(root / "models")):
                meta = train(pd.read_parquet(root / "final/imoveis_londrina.parquet"))
                self.assertEqual(len(meta["comparacao_teste"]), 5)
                self.assertEqual(meta["n_train"] + meta["n_calibration"] + meta["n_test"], len(df))
                self.assertEqual(len(load_artifacts()["pontos"]), meta["n_train"])
                result = estimar_preco(lat=-23.31, lon=-51.16)
                self.assertLessEqual(result["intervalo_min"], result["preco"])
                self.assertLessEqual(result["preco"], result["intervalo_max"])
                cache.clear()
                client = Client(enforce_csrf_checks=True)
                page = client.get("/")
                html = page.content.decode()
                self.assertIn('id="resultado"', html)
                self.assertIn('id="form"', html)
                self.assertNotIn("leaflet", html.lower())
                self.assertNotIn("tile.openstreetmap.org", html)
                self.assertNotIn("/api/pontos/", html)
                self.assertEqual(len(client.get("/api/pontos/").json()), meta["n_train"])
                payload = {"endereco": "Rua A", "area": "80"}
                self.assertEqual(client.post("/api/estimar/", payload, content_type="application/json").status_code, 403)
                with patch("src.predict.geocode", return_value=(-23.31, -51.16, "Rua A")):
                    response = client.post("/api/estimar/", payload, content_type="application/json",
                                           HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
                    self.assertEqual(response.status_code, 200)
                    self.assertGreater(response.json()["preco"], 0)


@override_settings(ALLOWED_HOSTS=["testserver"])
class ApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

    def test_invalid_inputs(self):
        payload = {"area": 100, "endereco": "Rua A"}
        for extra in [{"quartos": -1}, {"area": "nan"}, {"area": 2100}, {"suites": 4},
                      {"banheiros": 1.5}, {"condominio": "false"}, {"endereco": {}}]:
            with self.subTest(extra=extra):
                r = self.client.post("/api/estimar/", {**payload, **extra}, content_type="application/json")
                self.assertEqual(r.status_code, 400)

    def test_absent_model(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(config, "MODEL_DIR", tmp):
            body = self.client.get("/").content.decode()
            self.assertIn("Modelo ainda indisponível", body)
            self.assertEqual(self.client.get("/api/pontos/").status_code, 503)

    def test_quota(self):
        with patch("predictor.views.estimar_preco", return_value={"preco": 10}):
            for _ in range(10):
                self.assertEqual(self.client.post("/api/estimar/", {"area": 80, "endereco": "Rua A"},
                                 content_type="application/json").status_code, 200)
            self.assertEqual(self.client.post("/api/estimar/", {"area": 80, "endereco": "Rua A"},
                             content_type="application/json").status_code, 429)
