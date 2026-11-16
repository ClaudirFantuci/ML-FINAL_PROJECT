"""Views do estimador. Front-end simples: um formulario + uma chamada AJAX."""
import json
import time

from django.http import JsonResponse
from django.shortcuts import render
from django import forms
from django.core.cache import cache
from django.core.exceptions import RequestDataTooBig
from django.views.decorators.http import require_GET, require_POST

import config
from src.geocode import GeocoderUnavailable
from src.predict import ModelUnavailable, estimar_preco, load_artifacts


@require_GET
def index(request):
    try:
        meta = load_artifacts()["meta"]
    except ModelUnavailable:
        meta = None
    return render(request, "predictor/index.html", {
        "meta": meta,
        "amenidades": config.AMENIDADES,
        "city_name": config.CITY_NAME,
    })


@require_GET
def pontos(request):
    """Imoveis do dataset para desenhar o mapa de zonas do K-Means."""
    try:
        df = load_artifacts()["pontos"]
    except ModelUnavailable as exc:
        return JsonResponse({"erro": str(exc)}, status=503)
    if len(df) > 1500:
        df = df.sample(1500, random_state=config.RANDOM_STATE)
    data = [
        {"lat": round(r.lat, 5), "lon": round(r.lon, 5), "z": int(r.zone),
         "p": int(r.price), "a": int(r.usable_area), "b": str(r.neighborhood or "")}
        for r in df.itertuples()
    ]
    return JsonResponse(data, safe=False)


class EstimateForm(forms.Form):
    endereco = forms.CharField(min_length=2, max_length=200)
    area = forms.FloatField(min_value=config.CLEAN_LIMITS["usable_area"][0], max_value=config.CLEAN_LIMITS["usable_area"][1])
    quartos = forms.IntegerField(min_value=0, max_value=12)
    banheiros = forms.IntegerField(min_value=0, max_value=12)
    suites = forms.IntegerField(min_value=0, max_value=8)
    vagas = forms.IntegerField(min_value=0, max_value=10)
    n_amenities = forms.IntegerField(min_value=0, max_value=len(config.AMENIDADES))

    def clean(self):
        data = super().clean()
        if data.get("suites", 0) > min(data.get("quartos", 0), data.get("banheiros", 0)):
            self.add_error("suites", "Suítes devem caber no total de quartos e banheiros.")
        return data


@require_POST
def estimar(request):
    try:
        data = json.loads(request.body)
    except (ValueError, RequestDataTooBig):
        return JsonResponse({"erro": "Corpo da requisição inválido."}, status=400)
    if not isinstance(data, dict) or not isinstance(data.get("endereco"), str):
        return JsonResponse({"erro": "Informe o endereço."}, status=400)
    condo = data.get("condominio", False)
    if not isinstance(condo, bool):
        return JsonResponse({"erro": "Valor inválido para condomínio."}, status=400)
    for key in ("quartos", "banheiros", "suites", "vagas", "n_amenities"):
        data.setdefault(key, 0)
    form = EstimateForm(data)
    if not form.is_valid():
        msg = " ".join(f"{field}: {errors[0]}" for field, errors in form.errors.items())
        return JsonResponse({"erro": msg}, status=400)
    key = "estimar:%s:%d" % (request.META.get("REMOTE_ADDR", ""), time.time() // 60)
    cache.add(key, 0, timeout=75)
    if cache.incr(key) > 10:
        return JsonResponse({"erro": "Aguarde um minuto para consultar novamente."}, status=429)
    d = form.cleaned_data
    try:
        resultado = estimar_preco(endereco=d["endereco"], usable_area=d["area"], bedrooms=d["quartos"],
                                  bathrooms=d["banheiros"], suites=d["suites"], parking_spaces=d["vagas"],
                                  n_amenities=d["n_amenities"], in_condominium=int(condo))
    except (ModelUnavailable, GeocoderUnavailable) as exc:
        return JsonResponse({"erro": str(exc)}, status=503)
    return JsonResponse(resultado, status=404 if "erro" in resultado else 200)
