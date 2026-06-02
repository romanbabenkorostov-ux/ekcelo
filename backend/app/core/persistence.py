"""Persistence — SQLite snapshot store.

Re-export `lot_orchestrator_web.persistence.SQLitePersistence` (PR #90).
Lazy-import чтобы импорт `backend.app.core` не падал на main.
"""
from __future__ import annotations


def _get_sqlite_persistence():
    """Lazy proxy: возвращает класс или None если модуль не доступен."""
    try:
        from lot_orchestrator_web.persistence import SQLitePersistence
        return SQLitePersistence
    except ImportError:
        return None


class SQLitePersistence:
    """Lazy-wrapped SQLitePersistence.

    Если `lot_orchestrator_web.persistence` доступен (PR #90 merged) —
    наследуется к нему. Иначе при инстанцировании пробрасывает
    ImportError с понятным сообщением.
    """

    def __new__(cls, *args, **kwargs):
        impl = _get_sqlite_persistence()
        if impl is None:
            raise ImportError(
                "SQLitePersistence требует PR #90 (lot_orchestrator_web.persistence). "
                "Установите ветку с persistence-cycle или merge'те PR #90."
            )
        return impl(*args, **kwargs)


__all__ = ["SQLitePersistence"]
