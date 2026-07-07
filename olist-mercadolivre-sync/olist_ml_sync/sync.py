"""Orquestração: puxa produtos do Olist e publica no Mercado Livre."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Config
from .mapper import build_ml_payload, get_sku, validate_payload
from .mercadolivre_client import MercadoLivreClient, MercadoLivreError
from .olist_client import OlistClient
from .state import SyncState

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Criados: {self.created} | Atualizados: {self.updated} | "
            f"Pulados: {self.skipped} | Falhas: {self.failed}"
        )


class Synchronizer:
    def __init__(self, config: Config, dry_run: bool = True):
        self.config = config
        self.dry_run = dry_run
        self.olist = OlistClient(
            token=config.tiny_token,
            base_url=config.tiny_base_url,
            timeout=config.request_timeout,
            rate_limit_sleep=config.rate_limit_sleep,
        )
        self.ml = MercadoLivreClient(
            client_id=config.ml_client_id,
            client_secret=config.ml_client_secret,
            refresh_token=config.ml_refresh_token,
            access_token=config.ml_access_token,
            site_id=config.ml_site_id,
            base_url=config.ml_base_url,
            timeout=config.request_timeout,
            rate_limit_sleep=config.rate_limit_sleep,
        )
        self.state = SyncState.load(config.state_file)
        self._category_cache: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    def _resolve_category(self, title: str) -> str | None:
        key = title.lower()
        if key in self._category_cache:
            return self._category_cache[key]
        prediction = self.ml.predict_category(title)
        category_id = prediction.get("category_id") if prediction else None
        if category_id:
            self._category_cache[key] = category_id
        return category_id

    # ------------------------------------------------------------------ #
    def sync_produto(self, produto: dict, result: SyncResult) -> None:
        sku = get_sku(produto)
        nome = produto.get("nome", "(sem nome)")

        if not sku:
            logger.warning("Produto sem SKU/código, pulando: %s", nome)
            result.skipped += 1
            return

        if self.state.is_done(sku):
            logger.info("SKU %s já sincronizado, pulando.", sku)
            result.skipped += 1
            return

        payload = build_ml_payload(produto, self.config)
        problems = validate_payload(payload)
        if problems:
            msg = f"SKU {sku} ({nome}) inválido: {', '.join(problems)}"
            logger.warning(msg)
            self.state.record(sku, item_id=None, status="invalid", error="; ".join(problems))
            result.skipped += 1
            result.errors.append(msg)
            return

        # ---- categoria (chamada ao ML mesmo em dry-run, é só leitura) ----
        category_id = None
        if not self.dry_run or self.config.ml_access_token:
            try:
                category_id = self._resolve_category(payload["title"])
            except MercadoLivreError as exc:
                logger.warning("Sem categoria para SKU %s: %s", sku, exc)
        if category_id:
            payload["category_id"] = category_id

        if self.dry_run:
            logger.info(
                "[DRY-RUN] SKU %s -> criaria anúncio: título=%r preço=%s qtd=%s cat=%s imgs=%d",
                sku, payload["title"], payload["price"],
                payload["available_quantity"], category_id, len(payload["pictures"]),
            )
            result.created += 1
            return

        if not category_id:
            msg = f"SKU {sku} ({nome}) sem categoria prevista; defina manualmente."
            logger.error(msg)
            self.state.record(sku, item_id=None, status="no_category", error=msg)
            result.failed += 1
            result.errors.append(msg)
            return

        try:
            existing_id = self.ml.find_item_by_sku(sku)
            if existing_id:
                # atualiza campos que podem mudar (preço/estoque)
                self.ml.update_item(
                    existing_id,
                    {
                        "price": payload["price"],
                        "available_quantity": payload["available_quantity"],
                    },
                )
                self.state.record(sku, item_id=existing_id, status="updated")
                result.updated += 1
                logger.info("SKU %s atualizado (item %s).", sku, existing_id)
            else:
                description = payload.pop("description", None)
                created = self.ml.create_item(payload)
                item_id = created.get("id")
                if description and item_id:
                    try:
                        self.ml.update_description(item_id, description["plain_text"])
                    except MercadoLivreError as exc:
                        logger.warning("Item %s criado, mas descrição falhou: %s", item_id, exc)
                self.state.record(sku, item_id=item_id, status="created")
                result.created += 1
                logger.info("SKU %s criado (item %s).", sku, item_id)
        except MercadoLivreError as exc:
            msg = f"SKU {sku} ({nome}) falhou: {exc}"
            logger.error(msg)
            self.state.record(sku, item_id=None, status="failed", error=str(exc))
            result.failed += 1
            result.errors.append(msg)
        finally:
            self.state.save()

    # ------------------------------------------------------------------ #
    def run(self, situacao: str = "A", limit: int | None = None) -> SyncResult:
        result = SyncResult()
        mode = "DRY-RUN (nada será publicado)" if self.dry_run else "PUBLICAÇÃO REAL"
        logger.info("Iniciando sincronização Olist -> Mercado Livre [%s]", mode)

        count = 0
        for produto in self.olist.iter_produtos_completos(situacao=situacao):
            self.sync_produto(produto, result)
            count += 1
            if limit and count >= limit:
                logger.info("Limite de %d produtos atingido.", limit)
                break

        self.state.save()
        logger.info("Concluído. %s", result.summary())
        return result
