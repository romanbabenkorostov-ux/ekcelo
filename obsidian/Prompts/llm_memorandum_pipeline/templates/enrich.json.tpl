{
  "schema_version": "1.0",
  "lot_id": "<строка без пробелов, например pirushin_001>",
  "generated_at": "<ISO timestamp, например 2026-05-29T12:00:00+03:00>",

  "target_scenario": {
    "was": "<исходный статус, история консолидации>",
    "trigger": "<событие/сомнение/коммерческая гипотеза>",
    "to_plan": "<целевой инвестиционный трек: аренда/ГАБ | редевелопмент/снос | перевод фонда | продажа лота как ГАБ | иное>"
  },

  "egrn": {
    "$comment": "Вставить сюда содержимое парсерного JSON (выход parser/egrn_parser/exporters/json_exporter.py). Обычно под ключом tables: {...}",
    "tables": {}
  },

  "etp_profile": null,
  "$comment_etp_profile": "Если есть ЭТП-профиль (см. parser/tests/fixtures/etp/object_etp_profile_sample.json) — вставить объект; иначе null.",

  "graph_ref": "graph.html",

  "gpzu_minkult": null,
  "$comment_gpzu_minkult": "Содержимое gpzu_minkult.yaml после парсинга, или null если данных нет.",

  "field_inspection": null,
  "$comment_field_inspection": "Содержимое field_inspection.yaml после парсинга, или null.",

  "photo_album": null,
  "$comment_photo_album": "Содержимое photo_album_index.yaml после парсинга, или null.",

  "documents_dates": [
    {
      "$comment": "Пример записи. Реальные записи — из documents_dates.yaml.",
      "document_id": "egrn_extract_2024-05-12_kadastr_50_01_0010101_42",
      "type": "ЕГРН",
      "registered_date": "2024-05-11",
      "document_date": "2024-05-12",
      "covers_cad_numbers": ["50:01:0010101:42"]
    }
  ],

  "facts_index": [
    {
      "$comment": "Пример факта с provenance. Реальные факты строит Этап 1 из ЕГРН/YAML.",
      "fact_path": "egrn.tables.objects[0].area",
      "value": 1234.5,
      "provenance": {
        "document_id": "egrn_extract_2024-05-12_kadastr_50_01_0010101_42",
        "as_of_date": "2024-05-11",
        "evidence_level": 1
      }
    }
  ],

  "conflicts": [],
  "$comment_conflicts": "Факты, по которым два источника противоречат. Этап 2 применит правило: новее > registered > document_date.",

  "missing_layers": []
}
