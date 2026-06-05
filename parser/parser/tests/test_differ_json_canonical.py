"""Замок: JSON-массивы (object_restrictions и др.) сравниваются канонически —
порядок элементов не вызывает ложный diff при повторном парсинге одного отчёта."""
import json

from egrn_parser.merge.differ import diff_objects


def _restr(items):
    return {"object_restrictions": json.dumps(items, ensure_ascii=False)}


def test_reordered_restrictions_not_a_diff():
    a = [{"type": "czuit_zone", "registry_number": "61:44-6.1"},
         {"type": "okn_territory", "registry_number": "61:44-6.2"}]
    b = list(reversed(a))
    assert diff_objects(_restr(a), _restr(b), "land") == {}


def test_changed_restriction_type_is_a_diff():
    a = [{"type": "czuit_zone", "registry_number": "61:44-6.1"}]
    b = [{"type": "okn_territory", "registry_number": "61:44-6.1"}]
    assert "object_restrictions" in diff_objects(_restr(a), _restr(b), "land")


def test_permitted_uses_reorder_not_a_diff():
    o = {"permitted_uses": json.dumps(["жилое", "офис"], ensure_ascii=False)}
    n = {"permitted_uses": json.dumps(["офис", "жилое"], ensure_ascii=False)}
    assert diff_objects(o, n, "land") == {}


def test_none_vs_empty_list_not_a_diff():
    assert diff_objects({"object_restrictions": None},
                        {"object_restrictions": "[]"}, "land") == {}
