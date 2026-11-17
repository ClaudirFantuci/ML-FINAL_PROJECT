"""Coleta bruta: particiona a busca, pagina cada faixa e grava JSON cru.

Estrategia obrigatoria por causa do teto de paginacao (pagina 50 = 1500
anuncios). Londrina tem um estoque de casas bem acima disso, entao uma unica
query NAO alcanca tudo. Solucao: dividir por faixa de preco recursivamente ate
cada faixa caber no teto, e so entao paginar.

A camada `raw/` guarda o JSON exatamente como veio. Se depois voce perceber
que esqueceu um campo, reprocessa o disco em segundos em vez de recoletar
tudo.
"""
import json
import math
import os
from datetime import datetime, timezone

import config
from src.collectors.portals import PORTALS
from src.flight import extract_listings, extract_total
from src.http_client import Fetcher


def plan_partitions(fetcher, portal, lo=0, hi=None, depth=0):
    """Divide a faixa de preco ate cada pedaco caber sob PARTITION_CAP.

    Devolve [(preco_min, preco_max, total_estimado), ...]. O corte usa a media
    geometrica, nao a aritmetica: preco de imovel e distribuicao assimetrica e
    um corte no meio aritmetico deixaria um lado gigante e outro vazio.
    """
    hi = config.PRICE_CEILING if hi is None else hi
    indent = "  " * depth
    html = fetcher.get(portal.url(price_min=lo or None, price_max=hi))
    if html is None:
        raise ValueError("Página de planejamento indisponível.")
    total = extract_total(html)
    if total is None:
        raise ValueError("Página sem contagem de anúncios.")
    print("%s[%s] R$ %s..%s -> %d anuncios" % (indent, portal.name, f"{lo:,}", f"{hi:,}", total))

    if total == 0:
        return []
    if total <= config.PARTITION_CAP or depth >= config.MAX_SPLIT_DEPTH:
        if total > config.PARTITION_CAP:
            print("%s  ! faixa indivisivel acima do teto; %d anuncios ficarao de fora"
                  % (indent, total - config.PARTITION_CAP))
        return [(lo, hi, total)]

    mid = int(math.sqrt(max(lo, 1) * hi))
    if mid <= lo or mid >= hi:
        mid = (lo + hi) // 2
    return (plan_partitions(fetcher, portal, lo, mid, depth + 1)
            + plan_partitions(fetcher, portal, mid + 1, hi, depth + 1))


def collect_portal(portal_name, out_root="raw"):
    portal = PORTALS[portal_name]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = os.path.join(out_root, portal.name, stamp)
    os.makedirs(out_dir, exist_ok=True)

    fetcher = Fetcher(referer=portal.base + "/")
    summary = {"faixas": [], "unicos": 0, "status": "em andamento"}
    report_path = os.path.join(out_root, portal.name, stamp + "-relatorio.json")
    try:
        count = _collect(fetcher, portal, out_dir, summary)
        summary["status"] = "parcial" if summary.get("divergencias") else "concluída"
        return count
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        summary.update(status="interrompida", erro=str(exc))
        raise
    finally:
        summary.update(requisicoes=fetcher.n_requests, falhas_http=fetcher.failures)
        with open(report_path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
        os.replace(report_path + ".tmp", report_path)


def _collect(fetcher, portal, out_dir, summary):
    print("== planejando particoes (%s) ==" % portal.name)
    partitions = plan_partitions(fetcher, portal)
    planned = sum(p[2] for p in partitions)
    print("== %d particoes, ~%d anuncios ==" % (len(partitions), planned))

    seen = set()
    report = summary["faixas"]
    for lo, hi, total in partitions:
        pages = min(config.MAX_PAGE, math.ceil(total / config.PAGE_SIZE))
        tag = "%09d-%09d" % (lo, hi)
        print("-- faixa %s: %d anuncios em %d paginas" % (tag, total, pages))
        partition = {"min": lo, "max": hi, "previstos": total, "obtidos": 0}
        report.append(partition)
        for page in range(1, pages + 1):
            path = os.path.join(out_dir, "%s__p%03d.json" % (tag, page))
            if os.path.exists(path):          # retomada: nao refaz o que ja baixou
                with open(path, encoding="utf-8") as fh:
                    saved = json.load(fh)["listings"]
                    partition["obtidos"] += len(saved)
                    seen.update(x["id"] for x in saved)
                    summary["unicos"] = len(seen)
                continue

            html = fetcher.get(portal.url(page=page, price_min=lo or None, price_max=hi))
            if html is None:
                print("   pagina %d indisponivel, encerrando faixa" % page)
                break
            listings = extract_listings(html)
            if not listings:
                print("   pagina %d vazia, encerrando faixa" % page)
                break

            with open(path + ".tmp", "w", encoding="utf-8") as fh:
                json.dump({
                    "portal": portal.name,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "url": portal.url(page=page, price_min=lo or None, price_max=hi),
                    "price_min": lo, "price_max": hi, "page": page,
                    "listings": listings,
                }, fh, ensure_ascii=False)

            os.replace(path + ".tmp", path)
            partition["obtidos"] += len(listings)
            new = {x["id"] for x in listings} - seen
            seen.update(x["id"] for x in listings)
            summary["unicos"] = len(seen)
            print("   p%03d  %2d anuncios (%d novos)  | unicos ate agora: %d"
                  % (page, len(listings), len(new), len(seen)))

    summary["divergencias"] = sum(r["previstos"] != r["obtidos"] for r in report)
    if summary["divergencias"]:
        print("Atenção: totais divergentes em", summary["divergencias"], "faixa(s).")
    print("== %s: %d anúncios únicos em %d requisições ==" % (portal.name, len(seen), fetcher.n_requests))
    return len(seen)
