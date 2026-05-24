"""documents.json schema + validator (dev/SPEC_TEMPORAL_REPORTS.md §4).

Реализует:
  • `validate_documents_json(data)` — структурная валидация (raises ValueError
    с понятным сообщением; не использует jsonschema lib, чтобы не тянуть
    зависимости).
  • `load_documents(root)` — читает `<project>/_data/documents.json`,
    возвращает list[dict] (валидированный); пустой list если файла нет.
  • `parse_date(s)` — ISO `YYYY-MM-DD` строка → `date` объект.
  • Константы `EXTRACT_KINDS`, `KIND_PREFIXES` (соответствуют §4.3 spec'а).
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

EXTRACT_KINDS: frozenset[str] = frozenset({
    "egrn_extract", "egrul_extract", "egrip_extract",
})

KIND_PREFIXES: dict[str, str] = {
    "egrn_extract":     "ee_",
    "egrul_extract":    "eul_",
    "egrip_extract":    "eip_",
    "notarial_release": "nr_",
    "purchase":         "pc_",
    "mortgage":         "mg_",
    "court_decision":   "cd_",
    "bank_letter":      "bl_",
    "lease":            "ls_",
    "other":            "ot_",
}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DOC_ID_RE = re.compile(r"^[a-z]+_[A-Za-z0-9]+$")


def parse_date(s: str) -> date:
    """ISO `YYYY-MM-DD` → `date`. Raises ValueError на неправильный формат."""
    if not isinstance(s, str) or not _ISO_DATE_RE.match(s):
        raise ValueError(f"date должен быть ISO YYYY-MM-DD, получено: {s!r}")
    return date.fromisoformat(s)


def _err(path: str, msg: str) -> ValueError:
    return ValueError(f"documents.json: {path}: {msg}")


def _validate_subjects(subj: Any, path: str) -> None:
    if subj is None:
        return
    if not isinstance(subj, dict):
        raise _err(path, f"subjects должен быть dict или null, не {type(subj).__name__}")
    for k in ("cadastrals", "inns", "ogrns", "bu_ids"):
        v = subj.get(k)
        if v is not None and not (isinstance(v, list)
                                  and all(isinstance(x, str) for x in v)):
            raise _err(f"{path}.subjects.{k}", "должен быть list[str] или null")


def _validate_effect(eff: Any, path: str) -> None:
    if not isinstance(eff, dict):
        raise _err(path, "effect должен быть dict")
    op = eff.get("op")
    if op not in ("add", "remove", "change"):
        raise _err(path, f"op должен быть 'add'/'remove'/'change', не {op!r}")
    target = eff.get("target")
    if not (isinstance(target, str) and target):
        raise _err(path, "target должен быть непустая строка")
    payload = eff.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise _err(path, "payload должен быть dict или null")


def _validate_artifact(art: Any, path: str) -> None:
    if not isinstance(art, dict):
        raise _err(path, "artifact должен быть dict")
    f = art.get("file")
    if not (isinstance(f, str) and f):
        raise _err(path, "artifact.file должен быть непустая строка")
    for k in ("sha256", "external_url"):
        v = art.get(k)
        if v is not None and not isinstance(v, str):
            raise _err(f"{path}.{k}", "должен быть string или null")
    pc = art.get("page_count")
    if pc is not None and not (isinstance(pc, int) and pc > 0):
        raise _err(f"{path}.page_count", "должен быть int > 0 или null")


def validate_documents_json(data: Any) -> list[dict]:
    """Структурная валидация documents.json. Возвращает list документов.

    Raises ValueError с понятным path-сообщением при ошибке.
    Терпимо относится к незнакомым полям (forward-compat).
    """
    if not isinstance(data, dict):
        raise _err("$", "корень должен быть dict")
    sv = data.get("schema_version")
    if sv is not None and not isinstance(sv, str):
        raise _err("$.schema_version", "должен быть string или отсутствовать")
    docs = data.get("documents")
    if docs is None:
        return []
    if not isinstance(docs, list):
        raise _err("$.documents", "должен быть list или null")

    for i, doc in enumerate(docs):
        p = f"$.documents[{i}]"
        if not isinstance(doc, dict):
            raise _err(p, "document должен быть dict")
        doc_id = doc.get("doc_id")
        if not (isinstance(doc_id, str) and _DOC_ID_RE.match(doc_id)):
            raise _err(f"{p}.doc_id",
                       f"должен соответствовать [a-z]+_[A-Za-z0-9]+, не {doc_id!r}")
        kind = doc.get("kind")
        if kind not in KIND_PREFIXES:
            raise _err(f"{p}.kind",
                       f"должен быть один из {sorted(KIND_PREFIXES)}, не {kind!r}")
        expected_prefix = KIND_PREFIXES[kind]
        if not doc_id.startswith(expected_prefix):
            raise _err(f"{p}.doc_id",
                       f"для kind={kind!r} должен начинаться с {expected_prefix!r}, "
                       f"получено: {doc_id!r}")
        # doc_date обязателен.
        parse_date(doc.get("doc_date", ""))  # raises с понятным сообщением

        ra = doc.get("registered_at")
        if ra is not None and not isinstance(ra, str):
            raise _err(f"{p}.registered_at", "должен быть string или null")

        _validate_subjects(doc.get("subjects"), p)

        effects = doc.get("effects")
        if effects is not None:
            if not isinstance(effects, list):
                raise _err(f"{p}.effects", "должен быть list или null")
            for j, eff in enumerate(effects):
                _validate_effect(eff, f"{p}.effects[{j}]")

        artifacts = doc.get("artifacts")
        if artifacts is not None:
            if not isinstance(artifacts, list):
                raise _err(f"{p}.artifacts", "должен быть list или null")
            for j, art in enumerate(artifacts):
                _validate_artifact(art, f"{p}.artifacts[{j}]")

    return docs


def load_documents(root: Path) -> list[dict]:
    """`<project>/_data/documents.json` → list[dict] валидированных документов.

    Пустой list если файла нет. Raises ValueError если файл невалиден.
    """
    p = root / "_data" / "documents.json"
    if not p.exists():
        return []
    return validate_documents_json(json.loads(p.read_text(encoding="utf-8")))
