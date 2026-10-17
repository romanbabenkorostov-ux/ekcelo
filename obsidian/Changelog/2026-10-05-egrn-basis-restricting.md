# 2026-10-05 — xml ЕГРН: основание права, ограничиваемые права, личное участие

Повод — договоры по лоту в abn (ADR-025): без этих сведений не определить, кто
арендодатель, чья доля под запрещением и нужно ли согласие супруга.

- `parsers/xml_parser._parse_xml_right_record`: `basis` из `underlying_document`
  у права (раньше — только у обременений); `personal_participation_req` из
  `personal_participations` (ст. 36 218-ФЗ; PDF-разбор это уже видел).
- `parsers/xml_parser._parse_xml_restrict_record`: `restricting_right_number` —
  номера ограничиваемых прав через «; » (аренда → права арендодателей,
  запрещение → чьи доли).
- `merge/upsert.upsert_right`: `restricting_right_number` пишется в `rights`.
- Схема и контракт C2 не меняются — колонки уже были.
- Тест: `parser/tests/test_xml_basis_restricting.py`.
- Та же правка — в копии парсера olymp_v2.
