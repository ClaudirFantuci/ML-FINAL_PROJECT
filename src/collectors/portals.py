"""Definicao dos portais.

ZAP e VivaReal pertencem ao mesmo grupo e rodam o MESMO backend: estrutura de
payload identica e os totais batem entre os dois. Colete apenas o ZAP; o
VivaReal so serve para validacao pontual, coleta-lo tambem so gera quase 100%
de duplicata sobre o mesmo estoque de casas em Londrina.
"""
import config


class Portal:
    def __init__(self, name, base, city_slug):
        self.name = name
        self.base = base
        self.city_slug = city_slug

    def url(self, page=1, price_min=None, price_max=None):
        u = "%s/venda/%s/" % (self.base, self.city_slug) if self.name == "vivareal" \
            else "%s/venda/casas/%s/" % (self.base, self.city_slug)
        params = []
        if price_min is not None:
            params.append("precoMinimo=%d" % price_min)
        if price_max is not None:
            params.append("precoMaximo=%d" % price_max)
        if page > 1:
            params.append("pagina=%d" % page)
        return u + ("?" + "&".join(params) if params else "")


ZAP = Portal("zap", "https://www.zapimoveis.com.br", config.CITY_SLUG_ZAP)
VIVAREAL = Portal("vivareal", "https://www.vivareal.com.br", config.CITY_SLUG_VR)

PORTALS = {"zap": ZAP, "vivareal": VIVAREAL}
