"""Cliente da API do Mercado Livre (API oficial).

Documentação: https://developers.mercadolivre.com.br/

Fluxo:
  - autenticação OAuth2 (refresh_token -> access_token)
  - previsão de categoria (domain_discovery)
  - atributos obrigatórios da categoria
  - criação e atualização de itens (/items)
  - busca por seller_custom_field (SKU) para evitar duplicados
"""
from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)


class MercadoLivreError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: object | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


class MercadoLivreClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        access_token: str | None = None,
        site_id: str = "MLB",
        base_url: str = "https://api.mercadolibre.com",
        timeout: int = 30,
        rate_limit_sleep: float = 0.4,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.site_id = site_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.rate_limit_sleep = rate_limit_sleep
        self.session = requests.Session()
        self._user_id: int | None = None

    # ------------------------------------------------------------------ #
    # OAuth
    # ------------------------------------------------------------------ #
    def refresh_access_token(self) -> str:
        url = f"{self.base_url}/oauth/token"
        resp = self.session.post(
            url,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise MercadoLivreError(
                f"Falha ao renovar token: {resp.text}", resp.status_code, resp.text
            )
        data = resp.json()
        self.access_token = data["access_token"]
        # o ML rotaciona o refresh_token a cada uso
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        logger.info("Access token do Mercado Livre renovado.")
        return self.access_token

    def _ensure_token(self) -> None:
        if not self.access_token:
            self.refresh_access_token()

    # ------------------------------------------------------------------ #
    # HTTP helper
    # ------------------------------------------------------------------ #
    def _request(self, method: str, path: str, *, params=None, json=None, max_retries: int = 4):
        self._ensure_token()
        url = path if path.startswith("http") else f"{self.base_url}{path}"

        for attempt in range(1, max_retries + 1):
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
            }
            try:
                resp = self.session.request(
                    method, url, params=params, json=json, headers=headers, timeout=self.timeout
                )
            except requests.RequestException as exc:
                wait = 2 ** attempt
                logger.warning("Falha de rede em %s %s (%s). Retry em %ss", method, path, exc, wait)
                time.sleep(wait)
                continue

            # token expirado -> renova e repete
            if resp.status_code == 401:
                logger.info("401 do ML; renovando token e repetindo.")
                self.refresh_access_token()
                continue

            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning("Rate limit do ML (429). Aguardando %ss", wait)
                time.sleep(wait)
                continue

            time.sleep(self.rate_limit_sleep)
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                except ValueError:
                    body = resp.text
                raise MercadoLivreError(
                    f"{method} {path} -> {resp.status_code}: {body}", resp.status_code, body
                )
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()

        raise MercadoLivreError(f"Excedido número de tentativas em {method} {path}")

    # ------------------------------------------------------------------ #
    # Usuário / conta
    # ------------------------------------------------------------------ #
    def get_user_id(self) -> int:
        if self._user_id is None:
            me = self._request("GET", "/users/me")
            self._user_id = me["id"]
        return self._user_id

    # ------------------------------------------------------------------ #
    # Categorias / atributos
    # ------------------------------------------------------------------ #
    def predict_category(self, title: str) -> dict | None:
        """Sugere uma categoria a partir do título do produto."""
        try:
            results = self._request(
                "GET",
                f"/sites/{self.site_id}/domain_discovery/search",
                params={"q": title, "limit": 1},
            )
        except MercadoLivreError as exc:
            logger.warning("Falha na previsão de categoria para '%s': %s", title, exc)
            return None
        if isinstance(results, list) and results:
            return results[0]
        return None

    def get_category_attributes(self, category_id: str) -> list[dict]:
        return self._request("GET", f"/categories/{category_id}/attributes")

    # ------------------------------------------------------------------ #
    # Itens
    # ------------------------------------------------------------------ #
    def find_item_by_sku(self, sku: str) -> str | None:
        """Procura um anúncio existente do vendedor por seller_custom_field (SKU)."""
        if not sku:
            return None
        user_id = self.get_user_id()
        result = self._request(
            "GET",
            f"/users/{user_id}/items/search",
            params={"seller_custom_field": sku},
        )
        results = result.get("results") or []
        return results[0] if results else None

    def create_item(self, payload: dict) -> dict:
        return self._request("POST", "/items", json=payload)

    def update_item(self, item_id: str, payload: dict) -> dict:
        return self._request("PUT", f"/items/{item_id}", json=payload)

    def update_description(self, item_id: str, plain_text: str) -> dict:
        return self._request(
            "PUT", f"/items/{item_id}/description", json={"plain_text": plain_text}
        )
