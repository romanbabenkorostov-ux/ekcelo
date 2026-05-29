# Полевой осмотр: фактическое состояние, износ, перепланировки, оборудование.
# Опционально. Если осмотр не проводился — не заполняй; слой пойдёт в missing_layers[].

inspection:
  inspector: "Иванов И.И., главный инженер"
  date: 2026-05-15
  document_id: field_inspection_2026-05-15

clusters:
  - cluster_id: liter_A
    cad_numbers:
      - "50:01:0010101:42"
    actual_address: "г. Ростов-на-Дону, ул. Суворова, д. 60, Литер А"
    actual_area_m2: 1280.5
    egrn_area_m2: 1245.0
    delta_area_m2: 35.5
    delta_comment: "Зашита веранда 35.5 м² (Литер А1), не отражена в ЕГРН"
    construction_year: 1908
    wear_pct: 42
    perepplanirovki:
      - description: "Объединены помещения №7 и №8 (снесена перегородка)"
        agreed: false
        risk: "штраф 30-50 тыс. руб. + предписание восстановить"
    state: "удовлетворительное"

equipment:
  - cluster_id: liter_A
    items:
      - name: "Газовая котельная Buderus Logano G334X"
        power_kw: 240
        year: 2018
        condition: "рабочая, прошла ТО 2025-09"
        capex_saving_rub: 4500000
      - name: "Приточно-вытяжная вентиляция Systemair с рекуперацией"
        power_kw: 18
        year: 2020
        condition: "рабочая"
        capex_saving_rub: 1200000
      - name: "ГРЩ 380В, выделенная мощность 150 кВт"
        power_kw: 150
        year: 2015
        condition: "рабочее, ТУ от РСО"
        capex_saving_rub: 800000
