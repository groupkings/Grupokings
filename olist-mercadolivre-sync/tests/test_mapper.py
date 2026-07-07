"""Testes do mapeador Olist -> Mercado Livre (não fazem chamadas de rede)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from olist_ml_sync.mapper import (  # noqa: E402
    build_ml_payload,
    extract_pictures,
    get_sku,
    validate_payload,
)


class FakeConfig:
    ml_currency_id = "BRL"
    ml_condition = "new"
    ml_listing_type_id = "gold_special"
    default_available_quantity = 1


PRODUTO = {
    "id": "123456",
    "codigo": "SKU-001",
    "nome": "Volante Simulador Kings Racing GT Pro Edição Especial Premium XPTO",
    "preco": "1499.90",
    "preco_promocional": "1299.90",
    "estoqueAtual": "5",
    "marca": "Kings",
    "modelo": "GT Pro",
    "gtin": "7891234567890",
    "descricao_complementar": "<p>Volante <b>premium</b> para simulação.</p>",
    "anexos": [
        {"anexo": "https://exemplo.com/img1.jpg"},
        {"anexo": "https://exemplo.com/img2.jpg"},
        {"anexo": "https://exemplo.com/img1.jpg"},  # duplicada
    ],
}


def test_get_sku():
    assert get_sku(PRODUTO) == "SKU-001"


def test_title_truncado_em_60():
    payload = build_ml_payload(PRODUTO, FakeConfig())
    assert len(payload["title"]) <= 60


def test_usa_preco_promocional_quando_menor():
    payload = build_ml_payload(PRODUTO, FakeConfig())
    assert payload["price"] == 1299.90


def test_quantidade_do_estoque():
    payload = build_ml_payload(PRODUTO, FakeConfig())
    assert payload["available_quantity"] == 5


def test_imagens_sem_duplicadas():
    pics = extract_pictures(PRODUTO)
    assert len(pics) == 2
    assert pics[0]["source"] == "https://exemplo.com/img1.jpg"


def test_descricao_sem_html():
    payload = build_ml_payload(PRODUTO, FakeConfig())
    assert "<" not in payload["description"]["plain_text"]
    assert "premium" in payload["description"]["plain_text"]


def test_atributos_basicos():
    payload = build_ml_payload(PRODUTO, FakeConfig())
    ids = {a["id"]: a["value_name"] for a in payload["attributes"]}
    assert ids["BRAND"] == "Kings"
    assert ids["GTIN"] == "7891234567890"


def test_validacao_ok():
    payload = build_ml_payload(PRODUTO, FakeConfig())
    assert validate_payload(payload) == []


def test_validacao_sem_imagem_e_preco():
    payload = build_ml_payload(
        {"codigo": "X", "nome": "Sem foto", "preco": "0"}, FakeConfig()
    )
    problems = validate_payload(payload)
    assert "sem imagens (o ML exige ao menos 1)" in problems
    assert "preço zerado/ausente" in problems


if __name__ == "__main__":
    import traceback

    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    falhas = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            falhas += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(funcs) - falhas}/{len(funcs)} testes passaram.")
    raise SystemExit(1 if falhas else 0)
