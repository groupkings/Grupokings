"""Controle de estado para tornar a sincronização idempotente e retomável.

Guarda, por SKU, o item_id criado no Mercado Livre e o status. Assim,
rodar de novo não duplica anúncios e permite retomar de onde parou.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field


@dataclass
class SyncState:
    path: str
    items: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "SyncState":
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return cls(path=path, items=data.get("items", {}))
        return cls(path=path, items={})

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"items": self.items}, fh, ensure_ascii=False, indent=2)

    def get(self, sku: str) -> dict | None:
        return self.items.get(sku)

    def record(self, sku: str, *, item_id: str | None, status: str, error: str | None = None) -> None:
        self.items[sku] = {"item_id": item_id, "status": status, "error": error}

    def is_done(self, sku: str) -> bool:
        entry = self.items.get(sku)
        return bool(entry and entry.get("status") in ("created", "updated") and entry.get("item_id"))
