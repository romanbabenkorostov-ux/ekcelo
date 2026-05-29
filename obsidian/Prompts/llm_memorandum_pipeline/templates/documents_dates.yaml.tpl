# Список выписок ЕГРН/ЕГРЮЛ/ЕГРИП с датами актуальности.
#
# evidence_level (вычисляется автоматически):
#   1 — registered_date (когда данные зарегистрированы в реестре, приоритет)
#   2 — document_date   (когда сформирован документ выписки, ниже приоритетом)
#
# У каждой записи должно быть заполнено ХОТЯ БЫ ОДНО из двух полей дат.

documents:
  - document_id: egrn_extract_2024-05-12_kadastr_50_01_0010101_42
    type: ЕГРН
    registered_date: 2024-05-11       # YYYY-MM-DD — уровень 1
    document_date: 2024-05-12         # YYYY-MM-DD — уровень 2
    covers_cad_numbers:
      - "50:01:0010101:42"

  - document_id: egrlul_extract_2024-05-15_OOO_Antares
    type: ЕГРЮЛ
    registered_date: 2024-05-14
    document_date: 2024-05-15
    covers_entities:
      - inn: "1234567890"
        name: "ООО Антарес"

  - document_id: egrip_extract_2024-05-15_IP_Petrov
    type: ЕГРИП
    registered_date: null
    document_date: 2024-05-15
    covers_entities:
      - innfl: "123456789012"
        name: "ИП Петров А.А."
