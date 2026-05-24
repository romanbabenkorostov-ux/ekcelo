"""state-tags v2 — namespaces + manual ingester (PR-η, §5 spec'а).

Реализует dev/SPEC_TEMPORAL_REPORTS.md §5:
  • NAMESPACES — 8 namespaces (legal_state, utility_*, highest_best_use,
    physical_state, actual_use_format).
  • validate_state_tag(tag) — структурная валидация single-tag.
  • resolve_active_tags(state_tags, target_date) — какие теги действуют
    на T (since ≤ T < until || +∞).
  • collect_tags_from_documents(documents, target_date) — собрать теги
    из documents.json effects вида `state_tags` (ручной ingester v2).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .documents_schema import parse_date


NAMESPACES: dict[str, frozenset[str]] = {
    "legal_state": frozenset({
        "введён_в_эксплуатацию", "введён_в_эксплуатацию_по_суду",
        "подготовлен_к_демонтажу", "разрешено_проживание",
        "сертификат_гостиница_5*", "сертификат_отозван",
        "признан_аварийным",
    }),
    "utility_water": frozenset({
        "проектируется", "работает_локальное", "работает_сетевое", "демонтировано",
    }),
    "utility_gas": frozenset({
        "получено_разрешение_на_подключение", "подключено", "демонтировано",
    }),
    "utility_electricity": frozenset({
        "проектируется", "работает", "демонтировано",
    }),
    "utility_sewage": frozenset({
        "проектируется", "работает_локальное", "работает_сетевое", "демонтировано",
    }),
    "highest_best_use": frozenset({
        "музей", "гостиница", "жилой_дом", "офисный_центр",
        "гараж", "эллинг", "апарт_отель",
    }),
    "physical_state": frozenset({
        "возводится", "отличное", "хорошее", "удовлетворительное",
        "требуется_косметический_ремонт", "требуется_капитальный_ремонт",
        "руинировано",
    }),
    "actual_use_format": frozenset({
        "апартаменты", "музей", "гараж", "мотель",
        "не_используется", "заброшено",
    }),
}


def validate_state_tag(tag: Any, *, strict_values: bool = False) -> None:
    """Структурная валидация single-tag. Raises ValueError при ошибке.

    `strict_values=True` — проверка values из NAMESPACES (по умолчанию
    forward-compat: новые values принимаются с warning'ом по namespace).
    """
    if not isinstance(tag, dict):
        raise ValueError(f"state_tag должен быть dict, получено {type(tag).__name__}")
    ns = tag.get("namespace")
    if ns not in NAMESPACES:
        raise ValueError(
            f"state_tag.namespace должен быть один из {sorted(NAMESPACES)}, "
            f"не {ns!r}")
    value = tag.get("value")
    if not (isinstance(value, str) and value):
        raise ValueError("state_tag.value должен быть непустая строка")
    if strict_values and value not in NAMESPACES[ns]:
        raise ValueError(
            f"state_tag.value={value!r} не в whitelist namespace {ns!r}; "
            f"допустимые: {sorted(NAMESPACES[ns])}")
    since = tag.get("since")
    if since is not None:
        parse_date(since)  # raises с понятным сообщением
    until = tag.get("until")
    if until is not None:
        parse_date(until)


def resolve_active_tags(
    state_tags: list[dict] | None,
    target_date: date,
) -> list[dict]:
    """Возвращает теги, действующие на target_date (since ≤ T < until||+∞)."""
    active: list[dict] = []
    for tag in state_tags or []:
        try:
            validate_state_tag(tag)
        except ValueError:
            continue
        since = parse_date(tag["since"]) if tag.get("since") else date.min
        until = parse_date(tag["until"]) if tag.get("until") else date.max
        if since <= target_date < until:
            active.append(tag)
    return active


def collect_tags_from_documents(
    documents: list[dict],
    target_date: date,
) -> dict[str, list[dict]]:
    """Собрать state_tags из documents.json effects (ручной ingester v2).

    Ищет effects вида:
      {"op":"add", "target":"cadastre_objects[id=cad_X].state_tags",
       "payload": {<state_tag dict>}}

    Возвращает {cad_id → list[active_state_tags]}.
    """
    out: dict[str, list[dict]] = {}
    for doc in documents or []:
        doc_date = parse_date(doc["doc_date"]) if doc.get("doc_date") else None
        if doc_date and doc_date > target_date:
            continue
        for eff in doc.get("effects") or []:
            if eff.get("op") != "add":
                continue
            target = eff.get("target", "")
            if not target.endswith(".state_tags"):
                continue
            # Parse cad_id из target
            import re
            m = re.match(r"^cadastre_objects\[id=([^\]]+)\]\.state_tags$", target)
            if not m:
                continue
            cad_id = m.group(1)
            payload = eff.get("payload") or {}
            try:
                validate_state_tag(payload)
            except ValueError:
                continue
            # Поглощение: since/until из payload, doc.doc_date как fallback since.
            tag = {**payload}
            if "since" not in tag and doc.get("doc_date"):
                tag["since"] = doc["doc_date"]
            tag["source_doc_id"] = doc.get("doc_id")
            out.setdefault(cad_id, []).append(tag)
    return out
