"""Requisições identificadas, com espera entre páginas e tentativas limitadas."""
import logging
import random
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config

logger = logging.getLogger(__name__)


class Fetcher:
    def __init__(self, referer=None):
        self.headers = {"User-Agent": "ML-FINAL_PROJECT/2.0", "Accept-Language": "pt-BR,pt;q=0.9"}
        self.n_requests = 0
        self.failures = 0

    def get(self, url):
        for attempt in range(config.MAX_RETRIES):
            time.sleep(config.DELAY_SECONDS + random.random() * config.JITTER_SECONDS)
            self.n_requests += 1
            try:
                with urlopen(Request(url, headers=self.headers), timeout=config.TIMEOUT) as response:
                    return response.read().decode("utf-8")
            except HTTPError as exc:
                self.failures += 1
                if exc.code == 404:
                    return None
                if exc.code < 500:
                    raise RuntimeError(f"Coleta interrompida: HTTP {exc.code}.") from exc
                logger.warning("http_error status=%d tentativa=%d", exc.code, attempt + 1)
            except (URLError, TimeoutError) as exc:
                self.failures += 1
                logger.warning("network_error tentativa=%d erro=%s", attempt + 1, type(exc).__name__)
            if attempt + 1 < config.MAX_RETRIES:
                time.sleep(config.BACKOFF_BASE * 2 ** attempt)
        raise RuntimeError(f"Sem resposta após {config.MAX_RETRIES} tentativas.")
