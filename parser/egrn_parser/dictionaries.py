"""
egrn_parser/dictionaries.py — все словари-классификаторы системы.

Единственный источник истины для кодов ЕГРН, типов прав, видов объектов и пр.
При старте системы содержимое загружается в таблицу code_dictionary SQLite
командой egrn-parser dict-load (db/seeds.py:load_dictionaries).

Словарь code_dictionary в SQLite НЕ экспортируется в JSON/graph.json,
но выводится листом «Словарь кодов» в XLSX-экспорте.
"""

# ─────────────────────────────────────────────────────────────────────────────
#  Виды прав (RIGHT_TYPES)
# ─────────────────────────────────────────────────────────────────────────────
RIGHT_TYPES: dict[str, dict] = {
    "ownership":        {"value_ru": "Собственность",                          "short": "Собств."},
    "lease":            {"value_ru": "Аренда",                                  "short": "Аренда"},
    "perpetual_use":    {"value_ru": "Постоянное (бессрочное) пользование",    "short": "ПБП"},
    "free_use":         {"value_ru": "Безвозмездное пользование",               "short": "БП"},
    "lifelong_inherit": {"value_ru": "Пожизненное наследуемое владение",        "short": "ПНВ"},
    "operative_mgmt":   {"value_ru": "Оперативное управление",                  "short": "ОУ"},
    "economic_mgmt":    {"value_ru": "Хозяйственное ведение",                   "short": "ХВ"},
    "trust_mgmt":       {"value_ru": "Доверительное управление",                "short": "ДУ"},
    "shared":           {"value_ru": "Общая долевая собственность",             "short": "ОДС"},
    "joint":            {"value_ru": "Общая совместная собственность",          "short": "ОСС"},
    "unknown":          {"value_ru": "Не определено",                           "short": "?"},
}

# Русскоязычные варианты → код (для парсинга PDF/XML)
RIGHT_TYPE_RU_TO_CODE: dict[str, str] = {
    "собственность":                       "ownership",
    "общая долевая собственность":         "shared",
    "общая совместная собственность":      "joint",
    "аренда":                              "lease",
    "постоянное (бессрочное) пользование": "perpetual_use",
    "постоянное пользование":              "perpetual_use",
    "безвозмездное пользование":           "free_use",
    "безвозмездное срочное пользование":   "free_use",
    "пожизненное наследуемое владение":    "lifelong_inherit",
    "оперативное управление":              "operative_mgmt",
    "хозяйственное ведение":               "economic_mgmt",
    "доверительное управление":            "trust_mgmt",
}


# ─────────────────────────────────────────────────────────────────────────────
#  Категории записей прав (RIGHT_CATEGORIES)
# ─────────────────────────────────────────────────────────────────────────────
RIGHT_CATEGORIES: dict[str, dict] = {
    "right":       {"value_ru": "Право",               "short": "Право"},
    "encumbrance": {"value_ru": "Обременение",          "short": "Обрем."},
    "restriction": {"value_ru": "Ограничение прав",     "short": "Ограничение"},
}


# ─────────────────────────────────────────────────────────────────────────────
#  Виды обременений (ENCUMBRANCE_TYPES)
# ─────────────────────────────────────────────────────────────────────────────
ENCUMBRANCE_TYPES: dict[str, dict] = {
    "mortgage":     {"value_ru": "Ипотека",                             "short": "Ипотека"},
    "lease":        {"value_ru": "Аренда",                              "short": "Аренда"},
    "arrest":       {"value_ru": "Арест",                               "short": "Арест"},
    "prohibition":  {"value_ru": "Запрещение регистрации",              "short": "Запрет"},
    "concession":   {"value_ru": "Концессия",                           "short": "Конц."},
    "easement":     {"value_ru": "Сервитут",                            "short": "Серв."},
    "pub_easement": {"value_ru": "Публичный сервитут",                  "short": "ПС"},
    "trust_mgmt":   {"value_ru": "Доверительное управление",            "short": "ДУ"},
    "claim":        {"value_ru": "Заявленное в судебном порядке право", "short": "Иск"},
    "other":        {"value_ru": "Иное обременение",                    "short": "Иное"},
}

# Русский → код (для парсинга)
ENCUMBRANCE_RU_TO_CODE: dict[str, str] = {
    "ипотека":                  "mortgage",
    "аренда":                   "lease",
    "арест":                    "arrest",
    "запрещение регистрации":   "prohibition",
    "запрет регистрационных действий": "prohibition",
    "концессия":                "concession",
    "сервитут":                 "easement",
    "публичный сервитут":       "pub_easement",
    "доверительное управление": "trust_mgmt",
}


# ─────────────────────────────────────────────────────────────────────────────
#  Виды объектов недвижимости (OBJECT_TYPES)
# ─────────────────────────────────────────────────────────────────────────────
OBJECT_TYPES: dict[str, dict] = {
    "land":      {"value_ru": "Земельный участок",                   "short": "ЗУ",    "level": 0},
    "building":  {"value_ru": "Здание",                              "short": "Здание","level": 1},
    "structure": {"value_ru": "Сооружение",                          "short": "Соор.", "level": 1},
    "room":      {"value_ru": "Помещение",                           "short": "Пом.",  "level": 1},
    "parking":   {"value_ru": "Машино-место",                        "short": "ММ",    "level": 1},
    "ons":       {"value_ru": "Объект незавершённого строительства",  "short": "ОНС",   "level": 1},
    "complex":   {"value_ru": "Единый недвижимый комплекс",          "short": "ЕНК",   "level": 1},
}

# Русский → код объекта
OBJECT_TYPE_RU_TO_CODE: dict[str, str] = {
    "земельный участок":                            "land",
    "здание":                                       "building",
    "сооружение":                                   "structure",
    "помещение":                                    "room",
    "машино-место":                                 "parking",
    "машиноместо":                                  "parking",
    "объект незавершённого строительства":          "ons",
    "объект незавершенного строительства":          "ons",
    "единый недвижимый комплекс":                   "complex",
}

# Корневые XML-теги → код объекта
XML_ROOT_TO_OBJECT_TYPE: dict[str, str] = {
    "extract_about_property_land":         "land",
    "extract_about_property_build":        "building",
    "extract_about_property_room":         "room",
    "extract_about_property_construction": "structure",
    "extract_about_property_parking":      "parking",
    "extract_about_property_ons":          "ons",
}


# ─────────────────────────────────────────────────────────────────────────────
#  Виды ограничений объекта-актива (OBJECT_RESTRICTION_TYPES)
# ─────────────────────────────────────────────────────────────────────────────
OBJECT_RESTRICTION_TYPES: dict[str, dict] = {
    "czuit_zone":       {"value_ru": "Зона с особыми условиями использования территории",         "short": "ЗОУИТ"},
    "okn_territory":    {"value_ru": "Территория объекта культурного наследия",                    "short": "ОКН"},
    "agri_lands":       {"value_ru": "Сельскохозяйственные угодья в составе земель с/х назначения","short": "С/х угодья"},
    "public_servitude": {"value_ru": "Публичный сервитут",                                         "short": "ПС"},
    "other":            {"value_ru": "Иное ограничение объекта",                                   "short": "Иное"},
}

# Ключевые фразы в тексте PDF → код ограничения объекта
RESTRICTION_PHRASE_TO_CODE: list[tuple[str, str]] = [
    ("зоне с особыми условиями",           "czuit_zone"),
    ("зоуит",                              "czuit_zone"),
    ("объекта культурного наследия",       "okn_territory"),
    ("объект культурного наследия",        "okn_territory"),
    ("охранная зона",                      "czuit_zone"),
    ("сельскохозяйственных угодий",        "agri_lands"),
    ("сельскохозяйственного назначения",   "agri_lands"),
    ("публичный сервитут",                 "public_servitude"),
]


# ─────────────────────────────────────────────────────────────────────────────
#  Категории земель (LAND_CATEGORIES)
# ─────────────────────────────────────────────────────────────────────────────
LAND_CATEGORIES: dict[str, dict] = {
    "agricultural":   {"value_ru": "Земли сельскохозяйственного назначения",  "short": "С/х"},
    "settlements":    {"value_ru": "Земли населённых пунктов",                 "short": "НП"},
    "industry":       {"value_ru": "Земли промышленности",                     "short": "Пром."},
    "specially_prot": {"value_ru": "Земли особо охраняемых территорий",        "short": "ООТ"},
    "forest":         {"value_ru": "Земли лесного фонда",                      "short": "Лес"},
    "water":          {"value_ru": "Земли водного фонда",                      "short": "Вода"},
    "reserve":        {"value_ru": "Земли запаса",                             "short": "Запас"},
    "unknown":        {"value_ru": "Не определено",                            "short": "?"},
}


# ─────────────────────────────────────────────────────────────────────────────
#  Типы правообладателей (HOLDER_TYPES)
# ─────────────────────────────────────────────────────────────────────────────
HOLDER_TYPES: dict[str, dict] = {
    "individual":    {"value_ru": "Физическое лицо",                      "short": "ФЛ"},
    "legal_entity":  {"value_ru": "Юридическое лицо",                     "short": "ЮЛ"},
    "public":        {"value_ru": "Российская Федерация / субъект РФ",    "short": "РФ"},
    "municipal":     {"value_ru": "Муниципальное образование",            "short": "МО"},
    "unknown":       {"value_ru": "Не определено",                         "short": "?"},
}


# ─────────────────────────────────────────────────────────────────────────────
#  Типы событий объектов (OBJECT_EVENT_TYPES)
# ─────────────────────────────────────────────────────────────────────────────
OBJECT_EVENT_TYPES: dict[str, dict] = {
    "created":             {"value_ru": "Объект создан"},
    "updated":             {"value_ru": "Объект обновлён"},
    "transformed":         {"value_ru": "Объект преобразован"},
    "merged":              {"value_ru": "Объекты объединены"},
    "split":               {"value_ru": "Объект разделён"},
    "deleted":             {"value_ru": "Объект снят с учёта"},
    "geometry_updated":    {"value_ru": "Уточнена геометрия"},
    "restriction_added":   {"value_ru": "Добавлено ограничение объекта"},
    "restriction_removed": {"value_ru": "Снято ограничение объекта"},
    "modified":            {"value_ru": "Поля изменены (diff)"},
}


# ─────────────────────────────────────────────────────────────────────────────
#  Типы событий прав (RIGHT_EVENT_TYPES)
# ─────────────────────────────────────────────────────────────────────────────
RIGHT_EVENT_TYPES: dict[str, dict] = {
    "registered":          {"value_ru": "Право зарегистрировано"},
    "transferred":         {"value_ru": "Право перешло"},
    "terminated":          {"value_ru": "Право прекращено"},
    "encumbrance_added":   {"value_ru": "Добавлено обременение"},
    "encumbrance_removed": {"value_ru": "Обременение снято"},
}


# ─────────────────────────────────────────────────────────────────────────────
#  Типы преобразований (TRANSFORMATION_TYPES)
# ─────────────────────────────────────────────────────────────────────────────
TRANSFORMATION_TYPES: dict[str, dict] = {
    "split":               {"value_ru": "Раздел"},
    "merge":               {"value_ru": "Объединение"},
    "boundary_correction": {"value_ru": "Уточнение границ"},
    "redivision":          {"value_ru": "Перераспределение"},
}


# ─────────────────────────────────────────────────────────────────────────────
#  Типы оценки (VALUATION_TYPES)
# ─────────────────────────────────────────────────────────────────────────────
VALUATION_TYPES: dict[str, dict] = {
    "cadastral":    {"value_ru": "Кадастровая стоимость"},
    "initial":      {"value_ru": "Первоначальная балансовая стоимость"},
    "depreciation": {"value_ru": "Накопленная амортизация"},
    "residual":     {"value_ru": "Остаточная балансовая стоимость"},
    "market":       {"value_ru": "Рыночная стоимость"},
    "appraisal":    {"value_ru": "Стоимость по оценке"},
    "writeoff":     {"value_ru": "Стоимость при выбытии"},
    "lease_annual": {"value_ru": "Арендные платежи в год"},
    "lease_monthly":{"value_ru": "Арендные платежи в месяц"},
}


# ─────────────────────────────────────────────────────────────────────────────
#  Маппинг счёта 1С → right_type (OSV_ACCOUNT_RIGHTS)
# ─────────────────────────────────────────────────────────────────────────────
OSV_ACCOUNT_RIGHTS: dict[str, str] = {
    "01.01": "ownership",
    "01.К":  "lease",
    "001":   "lease",
    "011":   "free_use",
}


# ─────────────────────────────────────────────────────────────────────────────
#  Типы бизнес-единиц (UNIT_TYPES)
# ─────────────────────────────────────────────────────────────────────────────
UNIT_TYPES: dict[str, dict] = {
    "restaurant":  {"value_ru": "Ресторан"},
    "cafe":        {"value_ru": "Кафе/бар"},
    "spa":         {"value_ru": "СПА-комплекс"},
    "beach":       {"value_ru": "Пляж"},
    "hotel":       {"value_ru": "Гостиница"},
    "parking":     {"value_ru": "Парковка"},
    "warehouse":   {"value_ru": "Склад"},
    "office":      {"value_ru": "Офис"},
    "other":       {"value_ru": "Иное"},
}


# ─────────────────────────────────────────────────────────────────────────────
#  Статусы бизнес-единиц (UNIT_STATUSES)
# ─────────────────────────────────────────────────────────────────────────────
UNIT_STATUSES: dict[str, dict] = {
    "active":             {"value_ru": "Действует"},
    "inactive":           {"value_ru": "Не действует"},
    "under_construction": {"value_ru": "Строится"},
    "decommissioned":     {"value_ru": "Выведено"},
}


# ─────────────────────────────────────────────────────────────────────────────
#  Уровни иерархии (HIERARCHY_LEVELS) — Block 2
# ─────────────────────────────────────────────────────────────────────────────
HIERARCHY_LEVELS: dict[int, dict] = {
    -1: {"value_ru": "Orphan / неподтверждённый"},
     0: {"value_ru": "Земельный участок"},
     1: {"value_ru": "ОКС (здание / сооружение / помещение)"},
     2: {"value_ru": "Принадлежность / оборудование"},
     3: {"value_ru": "Бизнес-единица"},
}


# ─────────────────────────────────────────────────────────────────────────────
#  Полный список категорий для загрузки в SQLite
# ─────────────────────────────────────────────────────────────────────────────
ALL_DICT_CATEGORIES = (
    "RIGHT_TYPES",
    "RIGHT_CATEGORIES",
    "ENCUMBRANCE_TYPES",
    "OBJECT_TYPES",
    "OBJECT_RESTRICTION_TYPES",
    "LAND_CATEGORIES",
    "HOLDER_TYPES",
    "OBJECT_EVENT_TYPES",
    "RIGHT_EVENT_TYPES",
    "TRANSFORMATION_TYPES",
    "VALUATION_TYPES",
    "UNIT_TYPES",
    "UNIT_STATUSES",
)
