"""
egrn_parser/merge/content_hash.py — SHA-256 контент-хеш выписки.

Используется для идемпотентности: если хеш совпадает — пропуск.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


# Поля, участвующие в хеше (ТЗ раздел 7.6)
HASH_FIELDS = [
    "cad_number",
    "area",
    "cadastral_value",
    "address",
    "permitted_uses",
    "object_restrictions",
    "rights_summary",
]


def compute_content_hash(extract: dict) -> str:
    """
    SHA-256 от нормализованного содержимого выписки.

    extract должен содержать ключи из HASH_FIELDS.
    rights_summary — упорядоченный список кортежей
      (right_number, right_type, valid_until, beneficiary_inn).
    """
    payload = json.dumps(
        {k: extract.get(k) for k in HASH_FIELDS},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_rights_summary(rights: list[dict]) -> list:
    """Построить упорядоченный список для включения в хеш."""
    summary = [
        (
            r.get("right_number"),
            r.get("right_type"),
            r.get("valid_until"),
            r.get("beneficiary_inn"),
        )
        for r in rights
        if r.get("right_category") == "right"
    ]
    return sorted(summary)
