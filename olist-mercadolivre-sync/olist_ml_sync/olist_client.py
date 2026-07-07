"""Cliente da API do Olist/Tiny (API v2).

Documentação: https://www.tiny.com.br/api-docs/api2

A API v2 usa autenticação por token (parâmetro `token`) e retorna JSON
quando `formato=json`. Usada aqui para:
  - listar todos os produtos (produtos.pesquisa.php, paginado)
  - obter o detalhe completo de um produto (produto.obter.php)
"""
from __future__ import annotations

import logging
import time
from typing import Iterator

import requests

logger = logging.getLogger(__name__)


class OlistError(RuntimeError):
    """Erro retornado pela API do Tiny."""


class OlistClient:
    def __init__(
        self,
        token: str,
        base_url: str = "https://api.tiny.com.br/api2",
        timeout: int = 30,
        rate_limit_sleep: float = 0.4,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.rate_limit_sleep = rate_limit_sleep
        self.session = requests.Session()

    # ------------------------------------------------------------------ #
    # HTTP helper
    # ------------------------------------------------------------------ #
    def _post(self, endpoint: str, params: dict, max_retries: int = 4) -> dict:
        url = f"{self.base_url}/{endpoint}"
        payload = {"token": self.token, "formato": "json", **params}

        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.post(url, data=payload, timeout=self.timeout)
            except requests.RequestException as exc:
                wait = 2 ** attempt
                logger.warning("Falha de rede em %s (%s). Retry em %ss", endpoint, exc, wait)
                time.sleep(wait)
                continue

            # A API do Tiny limita a ~60 req/min; 429/erro -> backoff
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning("Rate limit do Tiny (429). Aguardando %ss", wait)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json().get("retorno", {})

            status = data.get("status")
            # status_processamento: 3 = OK; 2 = erro; 1 = em processamento
            if status == "Erro":
                erros = data.get("erros") or data.get("registros") or data
                # "Nenhum registro foi encontrado" não é um erro fatal na paginação
                msg = str(erros)
                if "nenhum registro" in msg.lower():
                    return data
                raise OlistError(f"Tiny API erro em {endpoint}: {msg}")

            time.sleep(self.rate_limit_sleep)
            return data

        raise OlistError(f"Excedido número de tentativas em {endpoint}")

    # ------------------------------------------------------------------ #
    # Produtos
    # ------------------------------------------------------------------ #
    def iter_produtos(self, situacao: str = "A") -> Iterator[dict]:
        """Itera sobre TODOS os produtos (resumo), página a página.

        situacao: 'A' = ativos, 'I' = inativos, 'E' = excluídos.
        Deixe vazio para trazer todos.
        """
        pagina = 1
        while True:
            params = {"pagina": pagina}
            if situacao:
                params["situacao"] = situacao

            data = self._post("produtos.pesquisa.php", params)
            produtos = data.get("produtos", [])
            if not produtos:
                break

            for item in produtos:
                yield item.get("produto", item)

            num_paginas = int(data.get("numero_paginas", pagina) or pagina)
            if pagina >= num_paginas:
                break
            pagina += 1

    def obter_produto(self, produto_id: str | int) -> dict:
        """Retorna o detalhe completo de um produto pelo ID."""
        data = self._post("produto.obter.php", {"id": produto_id})
        return data.get("produto", {})

    def iter_produtos_completos(self, situacao: str = "A") -> Iterator[dict]:
        """Itera trazendo o detalhe COMPLETO de cada produto.

        Faz uma chamada extra por produto (produto.obter.php) para obter
        descrição, imagens, dimensões, EAN etc.
        """
        for resumo in self.iter_produtos(situacao=situacao):
            pid = resumo.get("id")
            if not pid:
                continue
            try:
                completo = self.obter_produto(pid)
            except OlistError as exc:
                logger.error("Não foi possível obter produto %s: %s", pid, exc)
                continue
            # mescla o resumo (garante campos básicos) com o detalhe
            yield {**resumo, **completo}
