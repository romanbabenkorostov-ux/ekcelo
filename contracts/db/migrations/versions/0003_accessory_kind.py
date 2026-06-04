"""C2 — добавление значения 'accessory' в enum entitykind.

PARSER_VOCAB_MAP §6: узел accessory (Block-2 accessories) нужен в entities.kind.

- SQLite: entities.kind — VARCHAR без CHECK (Enum create_constraint=False) → no-op.
- PostgreSQL: нативный тип entitykind → ALTER TYPE ... ADD VALUE (idempotent).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003_accessory"
down_revision: Union[str, Sequence[str], None] = "0002_egrn"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE entitykind ADD VALUE IF NOT EXISTS 'accessory'")
    # SQLite: значение хранится как обычный текст — изменение схемы не требуется.


def downgrade() -> None:
    # PostgreSQL не поддерживает удаление значения enum без пересоздания типа.
    # Откат не выполняем (значение остаётся в типе; на данные не влияет).
    pass
