#!/usr/bin/env python3
"""CLI para sincronizar todos os produtos do Olist/Tiny com o Mercado Livre.

Exemplos:
  # Simular (não publica nada) — recomendado antes de tudo:
  python main.py --dry-run

  # Testar com poucos produtos de verdade:
  python main.py --publish --limit 5

  # Publicar TODOS os produtos ativos:
  python main.py --publish

  # Renovar o access token do Mercado Livre e imprimir:
  python main.py --refresh-token
"""
from __future__ import annotations

import argparse
import logging
import sys

from olist_ml_sync.config import Config
from olist_ml_sync.sync import Synchronizer


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Olist/Tiny -> Mercado Livre")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula a sincronização sem criar/alterar anúncios (padrão).",
    )
    grupo.add_argument(
        "--publish",
        action="store_true",
        help="Publica de verdade no Mercado Livre.",
    )
    parser.add_argument(
        "--situacao",
        default="A",
        help="Situação dos produtos no Tiny: A=ativos (padrão), I=inativos, ''=todos.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Processa no máximo N produtos (útil para testes).",
    )
    parser.add_argument(
        "--refresh-token",
        action="store_true",
        help="Apenas renova e imprime o access token do Mercado Livre.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Log detalhado (DEBUG)."
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        config = Config.from_env()
    except RuntimeError as exc:
        print(f"ERRO de configuração: {exc}", file=sys.stderr)
        return 2

    if args.refresh_token:
        from olist_ml_sync.mercadolivre_client import MercadoLivreClient

        ml = MercadoLivreClient(
            client_id=config.ml_client_id,
            client_secret=config.ml_client_secret,
            refresh_token=config.ml_refresh_token,
        )
        token = ml.refresh_access_token()
        print("ACCESS_TOKEN:", token)
        print("NOVO REFRESH_TOKEN:", ml.refresh_token)
        return 0

    # dry-run é o padrão de segurança; só publica com --publish
    dry_run = not args.publish

    if not dry_run:
        print(
            "\n⚠️  MODO PUBLICAÇÃO REAL: anúncios serão criados/atualizados no "
            "Mercado Livre.\n"
        )

    synchronizer = Synchronizer(config, dry_run=dry_run)
    result = synchronizer.run(situacao=args.situacao, limit=args.limit)

    print("\n===== RESUMO =====")
    print(result.summary())
    if result.errors:
        print(f"\n{len(result.errors)} ocorrência(s):")
        for err in result.errors[:50]:
            print("  -", err)

    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
