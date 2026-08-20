# -*- coding: utf-8 -*-
"""uuid7.py — тот же алгоритм, что gen_uuid7() в EkceloFotoMakeInvent и
VineInvent/etl/uuid7.py: UUIDv7 по RFC 9562, монотонный внутри одной
миллисекунды через 12-битный счётчик. Скопирован сюда (не тянем VineInvent
как зависимость — разные репозитории с разным циклом релиза), чтобы
`geo_entity.geo_uuid` минтился ТЕМ ЖЕ форматом, что и uuid7 везде в семье
(assets, sites, якорь VineInvent), а не только "похожим".
"""
import secrets
import threading
import time
import uuid as _uuidlib

_lock = threading.Lock()
_last_ms = -1
_counter = 0


def gen_uuid7() -> str:
    global _last_ms, _counter
    with _lock:
        ms = int(time.time() * 1000)
        if ms == _last_ms:
            _counter += 1
            if _counter > 0x0FFF:
                ms += 1
                _last_ms = ms
                _counter = 0
        else:
            _last_ms = ms
            _counter = 0
        rand_a = _counter & 0x0FFF
        rand_b = secrets.randbits(62)
    b = bytearray(16)
    b[0:6] = ms.to_bytes(6, "big")
    b[6] = 0x70 | ((rand_a >> 8) & 0x0F)
    b[7] = rand_a & 0xFF
    b[8] = 0x80 | ((rand_b >> 56) & 0x3F)
    b[9] = (rand_b >> 48) & 0xFF
    b[10] = (rand_b >> 40) & 0xFF
    b[11] = (rand_b >> 32) & 0xFF
    b[12] = (rand_b >> 24) & 0xFF
    b[13] = (rand_b >> 16) & 0xFF
    b[14] = (rand_b >> 8) & 0xFF
    b[15] = rand_b & 0xFF
    return str(_uuidlib.UUID(bytes=bytes(b)))
