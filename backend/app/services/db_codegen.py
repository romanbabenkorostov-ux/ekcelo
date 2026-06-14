"""DB-контракт C2 — кодогенерация Pydantic-моделей (P0.1.3).

Берёт `contracts/db/schema.json` и генерирует Pydantic-модели для каждой таблицы.
Сгенерированный файл — `backend/app/services/db_models.py` — committed в репо
(для IDE/refactoring), но может быть перерегенерирован командой:

    python -m backend.app.services.db_codegen --output backend/app/services/db_models.py

Сigned dist чексумму контракта, чтобы CI ловил рассинхрон (тест проверяет:
текущий db_models.py побайтно совпадает с тем, что генерируется из текущего
schema.json).

Зачем:
- Backend-сервисы (bundle.py, viewmodel.py) могут вместо row["col"] делать
  типизированный доступ `ObjectRow.model_validate(dict(row))`.
- Parser-команда / внешние потребители получают готовые модели как пакет
  (`from backend.app.services.db_models import ObjectRow`).
- Sync-guard codegen ↔ schema.json не даёт моделям отстать от контракта.

См. также: `contracts/db/schema.json` (источник), `contracts/db/DB_SPEC.md`,
`obsidian/Architecture/p0-db-contract.md`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from backend.app.services.db_contract import load_contract


# ─────────────────────────────────────────────────────────────────────────────
#  Маппинг SQL-типов → Python-типов
# ─────────────────────────────────────────────────────────────────────────────

_SQL_TO_PY: dict[str, str] = {
    "TEXT": "str",
    "INTEGER": "int",
    "REAL": "float",
    "NUMERIC": "float",
    "BLOB": "bytes",
}


def _py_type(sql_type: str, nullable: bool) -> str:
    base = _SQL_TO_PY.get(sql_type.upper(), "Any")
    return f"{base} | None" if nullable else base


def _class_name(table: str) -> str:
    """`object_etp_profile` → `ObjectEtpProfileRow`."""
    parts = [p for p in table.split("_") if p]
    return "".join(p.capitalize() for p in parts) + "Row"


_VALID_PY_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ─────────────────────────────────────────────────────────────────────────────
#  Кодогенерация
# ─────────────────────────────────────────────────────────────────────────────

_FILE_HEADER = '''"""AUTO-GENERATED Pydantic models for C2 DB-contract interchange tables.

ВНИМАНИЕ: НЕ редактируйте вручную. Регенерация:

    python -m backend.app.services.db_codegen --output backend/app/services/db_models.py

Источник: contracts/db/schema.json
Sha256 контракта (на момент генерации): {contract_sha256}

Каждая модель соответствует одной таблице sidecar-схемы Bundle. Используйте
для типизированного чтения sqlite-row'ов:

    from backend.app.services.db_models import ObjectsRow
    row = conn.execute("SELECT * FROM objects WHERE cad_number=?", (cad,)).fetchone()
    obj = ObjectsRow.model_validate(dict(row))

См. `obsidian/Architecture/p0-db-contract.md` (P0.1.3).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


'''


def generate(contract: dict[str, Any] | None = None) -> str:
    """Возвращает исходник модуля `db_models.py` как строку."""
    contract = contract or load_contract()
    contract_canonical = json.dumps(contract, sort_keys=True,
                                    separators=(",", ":"),
                                    ensure_ascii=False)
    contract_sha = hashlib.sha256(contract_canonical.encode("utf-8")).hexdigest()

    out: list[str] = [_FILE_HEADER.format(contract_sha256=contract_sha)]
    out.append(f"CONTRACT_SHA256 = {contract_sha!r}\n\n")

    tables = contract["tables"]
    for tname in sorted(tables):
        tdef = tables[tname]
        cls = _class_name(tname)
        section = tdef.get("section", "?")
        restorable = tdef.get("restorable", True)
        out.append(
            f"class {cls}(BaseModel):\n"
            f'    """Row из таблицы `{tname}` '
            f'(§{section}, restorable={restorable})."""\n'
            f"    model_config = ConfigDict(extra='allow')\n\n"
        )
        for col, cdef in tdef["columns"].items():
            if not _VALID_PY_IDENT.fullmatch(col):
                raise ValueError(
                    f"невалидное имя колонки для Python: {tname}.{col}"
                )
            sql_t = cdef["type"]
            nullable = bool(cdef.get("nullable", True))
            default = " = None" if nullable else ""
            py_t = _py_type(sql_t, nullable)
            out.append(f"    {col}: {py_t}{default}\n")
        out.append("\n\n")

    # Карта table_name → класс — для динамического доступа
    out.append("TABLE_TO_MODEL: dict[str, type[BaseModel]] = {\n")
    for tname in sorted(tables):
        out.append(f"    {tname!r}: {_class_name(tname)},\n")
    out.append("}\n")
    return "".join(out)


def write_to(path: Path, *, contract: dict[str, Any] | None = None) -> None:
    src = generate(contract)
    path.write_text(src, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ekcelo-db-codegen",
        description="Кодогенерация Pydantic-моделей из contracts/db/schema.json.",
    )
    parser.add_argument(
        "--output", "-o", type=Path,
        default=Path(__file__).parent / "db_models.py",
        help="Куда записать (default: backend/app/services/db_models.py)",
    )
    parser.add_argument(
        "--stdout", action="store_true",
        help="Печатать в stdout вместо файла (для CI-проверки).",
    )
    args = parser.parse_args(argv)

    src = generate()
    if args.stdout:
        print(src)
    else:
        args.output.write_text(src, encoding="utf-8")
        print(f"OK: записано {len(src)} байт → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
