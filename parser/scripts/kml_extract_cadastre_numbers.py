"""
kml_extract_cadastre_numbers.py — интерактивный помощник: спрашивает в
консоли путь к KML, вытаскивает уникальные кадастровые номера из
полигонов и сохраняет их построчно в соседний файл `<имя>+<расширение>`
(`Олимп.kml` → `Олимп+.kml`).

Извлечение то же самое, что у `kml_apply_nspd_contours.py
--list-cadastre-numbers` (переиспользует его функцию
`list_cadastre_numbers`, не дублирует regex/логику) — здесь просто
другой интерфейс: не флаги командной строки, а интерактивный запрос
пути, для тех, кто предпочитает "запустить и ответить на вопрос" (так
же устроен `01_parsing_nspd_v8.py`).

Формат вывода — по одному КН на строке, без разделителей: тот же
формат, что принимает интерактивный ввод `01_parsing_nspd_v8.py`
(`read_cn_batch()`) — содержимое выходного файла можно скопировать и
вставить туда как есть.

Запуск:
    python parser/scripts/kml_extract_cadastre_numbers.py
    (дальше скрипт сам спросит путь к KML)

Подробности конвейера — parser/scripts/README_NSPD_CONTOURS.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kml_apply_nspd_contours import list_cadastre_numbers  # noqa: E402


def output_path_for(kml_path: Path) -> Path:
    """`Олимп.kml` → `Олимп+.kml` — '+' перед расширением, тот же каталог."""
    return kml_path.with_name(kml_path.stem + "+" + kml_path.suffix)


def prompt_kml_path(input_fn=input) -> Path:
    while True:
        raw = input_fn("Путь к KML-файлу: ").strip().strip('"')
        if not raw:
            print("Пустой путь — попробуйте снова.")
            continue
        path = Path(raw)
        if not path.exists():
            print(f"Файл не найден: {path}")
            continue
        if not path.is_file():
            print(f"Это не файл: {path}")
            continue
        return path


def main(input_fn=input) -> int:
    try:
        kml_path = prompt_kml_path(input_fn)
    except (EOFError, KeyboardInterrupt):
        print("\nОтменено.")
        return 1

    try:
        cns = list_cadastre_numbers(kml_path)
    except Exception as e:
        print(f"error: не удалось разобрать KML: {e.__class__.__name__}: {e}", file=sys.stderr)
        return 1

    out_path = output_path_for(kml_path)
    out_path.write_text("\n".join(cns) + ("\n" if cns else ""), encoding="utf-8")

    print(f"\n[i] найдено уникальных кадастровых номеров: {len(cns)}")
    for cn in cns:
        print(f"    {cn}")
    print(f"\n[+] записано в {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
