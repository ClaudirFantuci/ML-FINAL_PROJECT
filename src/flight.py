"""Parser do payload RSC (React Server Components) do Next.js App Router.

O portal e uma app Next.js: o HTML entregue ja contem os anuncios serializados
em varios `self.__next_f.push([1,"<json escapado>"])`. Concatenando os pedacos
obtemos o "flight payload", de onde extraimos o array `listings` — os mesmos
objetos que a API interna devolveria, sem precisar parsear HTML nem rodar
navegador.
"""
import json
import re

_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,(".*?")\]\)', re.S)
_META_COUNT = re.compile(r'<meta name="description" content="[^"]*?([\d.]+)\s+(?:an[^"]*?ncios|Casas)')
_TOTAL_KEY = re.compile(r'"total"\s*:\s*(\d+)')


def decode_payload(html):
    """Junta e desescapa todos os chunks do flight payload."""
    chunks = _CHUNK.findall(html)
    if not chunks:
        return ""
    return "".join(json.loads(c) for c in chunks)


def _match_bracket(text, start):
    """Devolve o indice de fechamento do array/objeto que comeca em `start`."""
    open_ch = text[start]
    close_ch = "]" if open_ch == "[" else "}"
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("delimitador nao fechado")


def extract_listings(html):
    """Lista de dicts de anuncios contidos na pagina (ate 30)."""
    payload = decode_payload(html)
    idx = payload.find('"listings"')
    if idx < 0:
        raise ValueError("Página sem o campo listings.")
    start = payload.index("[", idx)
    end = _match_bracket(payload, start)
    return json.loads(payload[start:end + 1])


def extract_total(html):
    """Quantos anuncios a busca inteira tem (nao so a pagina). None se ilegivel."""
    m = _META_COUNT.search(html)
    if m:
        return int(m.group(1).replace(".", ""))
    m = _TOTAL_KEY.search(decode_payload(html))
    return int(m.group(1)) if m else None
