-- 0008_contour_source_label.sql — чем именно снят текущий контур.
--
-- ЗАЧЕМ. `v_object_contour_current` отвечала на вопрос «какой контур считать
-- текущим» двумя значениями: 'egrn' и 'manual'. Пока «manual» означало ровно
-- обводку по спутнику, этого хватало. Теперь в §9 приходит третий источник —
-- контур, снятый парсингом публичной кадастровой карты НСПД: его точность
-- дециметры, а не десятки метров, и в отчёте он не должен выглядеть как
-- «нарисовано от руки». Источник лежит в `manual_contour.source`, но во вьюху
-- не доходил, и потребитель (abn, отчёт, карточка объекта) вынужден был
-- называть контур НСПД обводкой.
--
-- ПОЧЕМУ НЕ ПОДМЕНИТЬ `contour_source`. Значение 'manual' читают экспортёры и
-- запросы: для них важно «не из выписки». Подменив его на 'nspd', мы бы
-- сломали их молча. Поэтому добавлена ОТДЕЛЬНАЯ колонка `manual_source`, а
-- смысл `contour_source` остался прежним.
--
-- ИДЕМПОТЕНТНОСТЬ. Вьюха пересоздаётся (DROP + CREATE): ALTER VIEW в SQLite
-- нет, а `CREATE VIEW IF NOT EXISTS` на существующей вьюхе молча ничего не
-- сделает — и миграция выглядела бы применённой, не изменив ничего.

DROP VIEW IF EXISTS v_object_contour_current;

CREATE VIEW v_object_contour_current AS
    SELECT e.cad_number,
           'egrn'                AS contour_source,
           'egrn'                AS manual_source,
           e.contour_no,
           e.geom_geojson,
           e.area_computed_sqm,
           e.accuracy_m,
           NULL                  AS confidence,
           e.land_layout,
           e.source_extract_number,
           e.extract_date
      FROM egrn_contour e
     WHERE e.kind = 'parcel'
       AND NOT EXISTS (
           SELECT 1 FROM manual_contour m
            WHERE m.cad_number = e.cad_number AND m.retired_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM contour_conflict c
                   WHERE c.cad_number = e.cad_number AND c.resolution = 'use_egrn'))
    UNION ALL
    SELECT m.cad_number,
           'manual'              AS contour_source,
           m.source              AS manual_source,
           m.contour_no,
           m.geom_geojson,
           m.area_computed_sqm,
           NULL                  AS accuracy_m,
           m.confidence,
           NULL                  AS land_layout,
           NULL                  AS source_extract_number,
           NULL                  AS extract_date
      FROM manual_contour m
     WHERE m.retired_at IS NULL
       AND NOT EXISTS (
           SELECT 1 FROM contour_conflict c
            WHERE c.cad_number = m.cad_number AND c.resolution = 'use_egrn');
