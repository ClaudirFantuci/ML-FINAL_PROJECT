"""Configuracao central da coleta e do modelo."""

# --- Alvo -------------------------------------------------------------------
CITY_SLUG_ZAP = "pr+londrina"                        # ZAP:      /venda/casas/<slug>/
CITY_SLUG_VR = "parana/londrina/casa_residencial"    # VivaReal: /venda/<slug>/
CITY_NAME = "Londrina"
STATE = "PR"

# --- Limites conhecidos do portal (mesmo grupo/backend do ZAP e VivaReal) ---
# A paginacao trava na pagina 50 (50 x 30 = 1500 anuncios por consulta). Como
# Londrina tem um estoque de casas maior que o teto, e preciso particionar a
# busca por faixa de preco recursivamente ate cada faixa caber no limite.
PAGE_SIZE = 30
MAX_PAGE = 50
PARTITION_CAP = MAX_PAGE * PAGE_SIZE   # 1500

PRICE_CEILING = 50_000_000
MAX_SPLIT_DEPTH = 8

# --- Educacao com o servidor ------------------------------------------------
DELAY_SECONDS = 2.0
JITTER_SECONDS = 1.0
MAX_RETRIES = 4
BACKOFF_BASE = 5.0
TIMEOUT = 45

CLEAN_LIMITS = {"price": (50_000, 20_000_000), "usable_area": (20, 2000),
                "price_per_sqm": (500, 40_000), "bedrooms": (0, 12), "bathrooms": (0, 12),
                "suites": (0, 8), "parking_spaces": (0, 10)}

# --- Centro de Londrina (Catedral Metropolitana, Centro) --------------------
CITY_CENTER = (-23.3122, -51.1597)

# Londrina tem area urbana maior que Maringa; o municipio cobre ~1.650 km2,
# mas o tecido urbano contiguo fica bem mais perto do centro. 35 km cobre a
# mancha urbana e distritos proximos (Warta, Guaravera, Espirito Santo) sem
# deixar passar cadastro errado de outra cidade.
MAX_DIST_CENTER_KM = 35

# --- Modelo -------------------------------------------------------------
N_CLUSTERS_RANGE = range(4, 13)     # busca de k do K-Means por silhouette
KNN_K_GRID = [5, 10, 15, 20, 25, 30, 40, 60]   # grade de vizinhos testada por CV
RANDOM_STATE = 42
MODEL_DIR = "models"

AMENIDADES = [
    ("BARBECUE_GRILL", "Churrasqueira"),
    ("SWIMMING_POOL", "Piscina"),
    ("AIR_CONDITIONING", "Ar-condicionado"),
    ("FURNISHED", "Mobiliada"),
    ("BACKYARD", "Quintal"),
    ("GARDEN", "Jardim"),
    ("GOURMET_SPACE", "Espaço gourmet"),
    ("BALCONY", "Varanda"),
]
