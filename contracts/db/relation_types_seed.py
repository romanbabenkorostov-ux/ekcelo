"""C2 — сид справочника relation_types, грунтованный реальными выходами парсеров.

Источники кодов:
  - parser/egrn_parser/exporters/graph_json.py (v1.1): contains, owns, leases, controls
  - parser/scripts/04_nspd_graph_v14.py:            level_in_building, equipment_on_level,
                                                    equipment_at_object, equipment_in_bu,
                                                    right/enc/beneficiary
  - DOC_CLASSIFIER_SPEC.md §3:                       ON_BALANCE_OF, LEASED_IN_BALANCE,
                                                    FOUNDER_OF, MANAGES, ESTABLISHES, ...

`domain ∈ {legal, tech, spatial, accounting, commercial}` (RelationDomain).
`category ∈ {right, encumbrance, restriction, topology, flow, accounting, commercial, corporate}`
  — `corporate` добавлен под бенефициарные цепочки (PARSER_VOCAB_MAP §3, вариант A).

Колонка `parser_edge` — какой код ребра эмитит парсер сейчас (для импорт-маппинга);
None = код есть в спецификации, но парсер его пока не emit'ит.

Использование:
    from contracts.db.models import RelationType
    for rt in RELATION_TYPES_SEED:
        session.merge(RelationType(code=rt["code"], name=rt["name"],
                                   domain=rt["domain"], category=rt["category"]))
"""

# (code, name, domain, category, parser_edge)
RELATION_TYPES_SEED: list[dict] = [
    # ── legal / right ────────────────────────────────────────────────────────
    {"code": "OWNS",          "name": "Собственность",            "domain": "legal", "category": "right",       "parser_edge": "owns"},
    {"code": "LEASES",        "name": "Аренда",                   "domain": "legal", "category": "right",       "parser_edge": "leases"},
    {"code": "OPERATES",      "name": "Оперативное управление",   "domain": "legal", "category": "right",       "parser_edge": None},
    {"code": "SERVITUDE",     "name": "Сервитут",                 "domain": "legal", "category": "right",       "parser_edge": None},
    {"code": "GRATUITOUS_USE","name": "Безвозмездное пользование","domain": "legal", "category": "right",       "parser_edge": None},
    # ── legal / encumbrance ──────────────────────────────────────────────────
    {"code": "MORTGAGED_BY",  "name": "Ипотека/залог",            "domain": "legal", "category": "encumbrance", "parser_edge": "enc"},
    {"code": "ARRESTED_BY",   "name": "Арест",                    "domain": "legal", "category": "encumbrance", "parser_edge": "enc"},
    # ── legal / restriction ──────────────────────────────────────────────────
    {"code": "RESTRICTED_BY", "name": "Ограничение (СЗЗ/ВОЗ/ОКН)","domain": "legal", "category": "restriction", "parser_edge": None},
    # ── legal / corporate (бенефициарные цепочки + реорганизация, EGRUL) ─────
    {"code": "CONTROLS",      "name": "Контроль (доля)",          "domain": "legal", "category": "corporate",   "parser_edge": "controls"},
    {"code": "FOUNDER_OF",    "name": "Учредитель",               "domain": "legal", "category": "corporate",   "parser_edge": None},
    {"code": "MANAGES",       "name": "Руководитель/УК (без доверенности)", "domain": "legal", "category": "corporate", "parser_edge": None},
    {"code": "BRANCH_OF",     "name": "Обособленное подразделение","domain": "legal","category": "corporate",   "parser_edge": None},
    # правопреемство при реорганизации (от=правопреемник, к=правопредшественник); reorg_type в meta
    {"code": "SUCCESSOR_OF",      "name": "Правопреемник (реорганизация)", "domain": "legal", "category": "corporate", "parser_edge": None},
    {"code": "REORGANIZING_WITH", "name": "Участвует в реорганизации",     "domain": "legal", "category": "corporate", "parser_edge": None},
    # ── spatial / topology ───────────────────────────────────────────────────
    {"code": "CONTAINS",      "name": "Содержит",                 "domain": "spatial", "category": "topology",  "parser_edge": "contains"},
    {"code": "INSIDE",        "name": "Внутри",                   "domain": "spatial", "category": "topology",  "parser_edge": "level_in_building"},
    {"code": "LOCATED_ON",    "name": "Расположен на",            "domain": "spatial", "category": "topology",  "parser_edge": "equipment_on_level"},
    {"code": "INTERSECTS",    "name": "Пересекает",               "domain": "spatial", "category": "topology",  "parser_edge": None},
    {"code": "ADJACENT_TO",   "name": "Смежен",                   "domain": "spatial", "category": "topology",  "parser_edge": None},
    # ── tech / flow ──────────────────────────────────────────────────────────
    {"code": "MOVED_TO",      "name": "Перемещено в",             "domain": "tech", "category": "flow",         "parser_edge": None},
    {"code": "FEEDS",         "name": "Питает",                   "domain": "tech", "category": "flow",         "parser_edge": None},
    {"code": "TRANSFORMS_TO", "name": "Преобразуется в",          "domain": "tech", "category": "flow",         "parser_edge": None},
    {"code": "CONNECTED_TO",  "name": "Подключено к",             "domain": "tech", "category": "flow",         "parser_edge": None},
    # ── accounting (ОСВ) ─────────────────────────────────────────────────────
    {"code": "ON_BALANCE_OF",     "name": "На балансе (01.01)",      "domain": "accounting", "category": "accounting", "parser_edge": None},
    {"code": "LEASED_IN_BALANCE", "name": "Аренда/лизинг (01.03/К)", "domain": "accounting", "category": "accounting", "parser_edge": None},
    {"code": "CAPITALIZED_BY",    "name": "Капитализировано",        "domain": "accounting", "category": "accounting", "parser_edge": None},
    # ── commercial ───────────────────────────────────────────────────────────
    {"code": "INCLUDED_IN_LOT",   "name": "Включено в лот",          "domain": "commercial", "category": "commercial", "parser_edge": None},
    {"code": "SUBJECT_OF_ORDER",  "name": "Предмет заказа",          "domain": "commercial", "category": "commercial", "parser_edge": None},
    {"code": "GROUPS",            "name": "Группирует (БА)",         "domain": "commercial", "category": "commercial", "parser_edge": "equipment_in_bu"},
    # ── doc-связи (ESTABLISHES/EVIDENCES/DEPICTS — в doc_links.relation_code) ─
    {"code": "ESTABLISHES",   "name": "Устанавливает право",      "domain": "legal", "category": "right",        "parser_edge": None},
    {"code": "EVIDENCES",     "name": "Подтверждает факт",        "domain": "legal", "category": "right",        "parser_edge": None},
    {"code": "DEPICTS",       "name": "Изображает (фото)",        "domain": "spatial", "category": "topology",   "parser_edge": None},
]

# Быстрый индекс: какой relation_types.code соответствует ребру парсера.
PARSER_EDGE_TO_CODE: dict[str, str] = {
    rt["parser_edge"]: rt["code"] for rt in RELATION_TYPES_SEED if rt["parser_edge"]
}
# equipment_at_object тоже → LOCATED_ON (несколько рёбер парсера на один код)
PARSER_EDGE_TO_CODE["equipment_at_object"] = "LOCATED_ON"

# Виды реорганизации (ЕГРЮЛ, ФЗ-129 ст.5 п.1 пп «ж») — значения relations.meta.reorg_type
# для рёбер SUCCESSOR_OF / REORGANIZING_WITH.
REORG_TYPES: dict[str, str] = {
    "merger":         "слияние",        # A + B → C (новое ЮЛ)
    "affiliation":    "присоединение",  # B → A (B прекращается, права к A)
    "division":       "разделение",     # A → B + C (A прекращается)
    "spin_off":       "выделение",      # A → A + B (A продолжает, B новое)
    "transformation": "преобразование", # A → A' (смена ОПФ)
}
