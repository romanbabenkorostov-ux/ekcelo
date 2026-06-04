"""Идемпотентный сид справочников C2.

Сейчас наполняет `relation_types` из `relation_types_seed.RELATION_TYPES_SEED`
(коды грунтованы реальными рёбрами парсеров, см. PARSER_VOCAB_MAP.md).

Запуск:
    EKCELO_DB_URL=sqlite:///contracts/db/ekcelo.db python -m contracts.db.seed
    # или для PG:  EKCELO_DB_URL=postgresql+psycopg://user:pwd@host/ekcelo
"""
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from contracts.db.models import RelationType
from contracts.db.relation_types_seed import RELATION_TYPES_SEED


def seed_relation_types(session: Session) -> int:
    """Вставляет недостающие relation_types (по уникальному code). Возвращает кол-во добавленных."""
    existing = set(session.scalars(select(RelationType.code)).all())
    added = 0
    for rt in RELATION_TYPES_SEED:
        if rt["code"] in existing:
            continue
        session.add(RelationType(
            code=rt["code"], name=rt["name"],
            domain=rt["domain"], category=rt["category"],
        ))
        added += 1
    session.commit()
    return added


def main() -> None:
    url = os.environ.get("EKCELO_DB_URL", "sqlite:///contracts/db/ekcelo.db")
    engine = create_engine(url)
    with Session(engine) as session:
        added = seed_relation_types(session)
    print(f"relation_types: +{added} (всего в сиде {len(RELATION_TYPES_SEED)})")


if __name__ == "__main__":
    main()
