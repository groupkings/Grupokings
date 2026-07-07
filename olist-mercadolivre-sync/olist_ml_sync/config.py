"""Configuração via variáveis de ambiente.

Carrega as credenciais/opções do arquivo .env (se python-dotenv estiver
instalado) ou diretamente do ambiente.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # carregamento opcional do .env
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv é opcional
    pass


def _get(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(
            f"Variável de ambiente obrigatória ausente: {name}. "
            f"Preencha o arquivo .env (veja .env.example)."
        )
    return value


@dataclass
class Config:
    # ---- Olist / Tiny (API v2) ----
    tiny_token: str
    tiny_base_url: str

    # ---- Mercado Livre (API oficial) ----
    ml_client_id: str
    ml_client_secret: str
    ml_refresh_token: str
    ml_access_token: str | None
    ml_site_id: str
    ml_base_url: str

    # ---- Padrões de anúncio ----
    ml_listing_type_id: str
    ml_condition: str
    ml_currency_id: str
    ml_warranty: str
    default_available_quantity: int

    # ---- Comportamento ----
    request_timeout: int
    rate_limit_sleep: float
    state_file: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            tiny_token=_get("TINY_TOKEN", required=True),
            tiny_base_url=_get("TINY_BASE_URL", "https://api.tiny.com.br/api2"),
            ml_client_id=_get("ML_CLIENT_ID", required=True),
            ml_client_secret=_get("ML_CLIENT_SECRET", required=True),
            ml_refresh_token=_get("ML_REFRESH_TOKEN", required=True),
            ml_access_token=_get("ML_ACCESS_TOKEN"),
            ml_site_id=_get("ML_SITE_ID", "MLB"),
            ml_base_url=_get("ML_BASE_URL", "https://api.mercadolibre.com"),
            ml_listing_type_id=_get("ML_LISTING_TYPE_ID", "gold_special"),
            ml_condition=_get("ML_CONDITION", "new"),
            ml_currency_id=_get("ML_CURRENCY_ID", "BRL"),
            ml_warranty=_get("ML_WARRANTY", "Garantia do vendedor: 90 dias"),
            default_available_quantity=int(_get("ML_DEFAULT_QUANTITY", "1")),
            request_timeout=int(_get("REQUEST_TIMEOUT", "30")),
            rate_limit_sleep=float(_get("RATE_LIMIT_SLEEP", "0.4")),
            state_file=_get("STATE_FILE", "sync_state.json"),
        )
