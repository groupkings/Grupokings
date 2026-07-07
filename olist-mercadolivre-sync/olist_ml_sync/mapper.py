"""Transforma um produto do Olist/Tiny no payload de item do Mercado Livre."""
from __future__ import annotations

import html
import logging
import re

logger = logging.getLogger(__name__)

# Limite de caracteres do título no Mercado Livre
ML_TITLE_MAX = 60


def _to_float(value) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    txt = str(value).strip().replace(".", "").replace(",", ".") if "," in str(value) else str(value)
    try:
        return float(txt)
    except ValueError:
        return 0.0


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clean_text(value) -> str:
    if not value:
        return ""
    text = html.unescape(str(value))
    # remove tags HTML da descrição do Tiny
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_pictures(produto: dict) -> list[dict]:
    """Extrai URLs de imagens do produto Tiny (anexos + imagens_externas)."""
    urls: list[str] = []

    for anexo in produto.get("anexos") or []:
        url = anexo.get("anexo") if isinstance(anexo, dict) else anexo
        if url:
            urls.append(url)

    for img in produto.get("imagens_externas") or []:
        url = img.get("url") if isinstance(img, dict) else img
        if url:
            urls.append(url)

    # remove duplicados preservando ordem; ML aceita até 12 imagens
    seen: set[str] = set()
    pictures = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            pictures.append({"source": url})
    return pictures[:12]


def build_attributes(produto: dict) -> list[dict]:
    """Monta atributos básicos (marca, modelo, EAN)."""
    attributes: list[dict] = []

    marca = produto.get("marca")
    if marca:
        attributes.append({"id": "BRAND", "value_name": str(marca)})

    modelo = produto.get("modelo")
    if modelo:
        attributes.append({"id": "MODEL", "value_name": str(modelo)})

    ean = produto.get("gtin") or produto.get("ean")
    if ean:
        attributes.append({"id": "GTIN", "value_name": str(ean)})

    return attributes


def get_sku(produto: dict) -> str:
    return str(produto.get("codigo") or produto.get("sku") or produto.get("id") or "").strip()


def build_ml_payload(produto: dict, config) -> dict:
    """Cria o payload de item do Mercado Livre a partir do produto Tiny.

    A `category_id` NÃO é definida aqui — é resolvida no sync (previsão por
    título), pois depende de chamada à API do ML.
    """
    nome = str(produto.get("nome") or produto.get("descricao") or "Produto").strip()
    title = nome[:ML_TITLE_MAX].strip()

    price = _to_float(produto.get("preco"))
    promocional = _to_float(produto.get("preco_promocional"))
    if promocional and promocional < price:
        price = promocional

    quantity = _to_int(produto.get("estoqueAtual"), config.default_available_quantity)
    if quantity <= 0:
        quantity = config.default_available_quantity

    descricao = _clean_text(
        produto.get("descricao_complementar") or produto.get("obs") or nome
    )

    payload: dict = {
        "title": title,
        "price": round(price, 2),
        "currency_id": config.ml_currency_id,
        "available_quantity": quantity,
        "buying_mode": "buy_it_now",
        "condition": config.ml_condition,
        "listing_type_id": config.ml_listing_type_id,
        "pictures": extract_pictures(produto),
        "attributes": build_attributes(produto),
        "sale_terms": [
            {"id": "WARRANTY_TYPE", "value_name": "Garantia do vendedor"},
            {"id": "WARRANTY_TIME", "value_name": "90 dias"},
        ],
        "seller_custom_field": get_sku(produto),
        "description": {"plain_text": descricao or nome},
    }
    return payload


def validate_payload(payload: dict) -> list[str]:
    """Retorna uma lista de problemas que impediriam a publicação no ML."""
    problems: list[str] = []
    if not payload.get("title"):
        problems.append("sem título")
    if payload.get("price", 0) <= 0:
        problems.append("preço zerado/ausente")
    if not payload.get("pictures"):
        problems.append("sem imagens (o ML exige ao menos 1)")
    return problems
