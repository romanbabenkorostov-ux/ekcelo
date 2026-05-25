"""
NSPD Парсер v8.0 (extends standalone v25.0 — adds contour extraction)

Что нового vs v7/v25.0:
- Новый шаг в `parse_one()`: после парсинга карточки извлекается контур объекта.
- Гибрид-подход: WFS-API (primary) → DOM/OL-state (secondary) → screenshot+CV (last-resort).
- Если `info["Без координат границ"] == True` — шаг пропускается.
- Результат: `info["Контур"]` со схемой:
    {
      "источник": "wfs" | "ol_state" | "screenshot_cv",
      "тип": "Polygon" | "MultiPolygon",
      "кол-во_колец": int,
      "площадь_заявленная_кв_м": float | None,
      "площадь_вычисленная_кв_м": float | None,
      "коэф_коррекции_масштаба": float | None,
      "центроид": {"lon": float, "lat": float} | {"px_x": float, "px_y": float},
      "geojson": {...} | None,           # WGS84, если есть georeference
      "локальные_метры": [               # массив колец; первое — внешний контур,
        [{"dx": 1.234, "dy": -5.678}, ...], #   следующие — дырки (для MultiPolygon — flat list колец)
        ...
      ],
      "scale_bar_px": int | None,
      "scale_bar_m": float | None,
      "м_на_пиксель": float | None,
      "превью_png_b64": str | None,
      "алгоритм_версия": "v8.0"
    }

Зависимости:
- Базовые: playwright (как в v7).
- Для CV-fallback (опционально): numpy, opencv-python, Pillow.
  Если не установлены — fallback просто пропускается с warning.
"""
import asyncio
import base64
import io
import json
import math
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

try:
    import numpy as np
    import cv2
    from PIL import Image
    _HAS_CV = True
except ImportError:
    _HAS_CV = False


CN_RE = re.compile(r"^\d{1,2}:\d{1,2}:\d{1,7}:\d+(?:/\d+)?$")
CN_PART_RE = re.compile(r"^\d{1,2}:\d{1,2}:\d{1,7}:\d+/\d+$")
CN_PLAIN_RE = re.compile(r"^\d{1,2}:\d{1,2}:\d{1,7}:\d+$")
CN_FIND_RE = re.compile(r"\b\d{1,2}:\d{1,2}:\d{1,7}:\d+(?:/\d+)?\b")

HEADER_TYPES = (
    "Единое землепользование",
    "Земельный участок",
    "Здание",
    "Сооружение",
    "Помещение",
    "Объект незавершенного строительства",
)

CATEGORY_MAP = {
    "Земельный участок": "Земельные участки",
    "Единое землепользование": "Земельные участки",
    "Здание": "Здания",
    "Сооружение": "Сооружения",
    "Помещение": "Помещения",
    "Объект незавершенного строительства": "Объекты незавершенного строительства",
}

NUMERIC_KEYS = {
    "Кадастровая стоимость": "Кадастровая стоимость, руб.",
    "Удельный показатель кадастровой стоимости": "Удельный показатель кадастровой стоимости, руб./кв.м",
}

BUILDING_TABS = ("Информация", "Объекты", "Связанные ЗУ", "Части ОКС", "Виды разрешенного использования")
LAND_TABS = ("Информация", "Объекты", "Части ЗУ", "Состав ЕЗП", "Виды разрешенного использования")
ALL_TABS = ("Информация", "Объекты", "Связанные ЗУ", "Части ОКС", "Части ЗУ", "Состав ЕЗП", "Виды разрешенного использования")

# WFS layer IDs (взято из viewer/index.html v2.9.x)
NSPD_ZU_IDS = [36048]
NSPD_OKS_IDS = [36329, 36328, 36049]
CAD_FIELDS = ['cad_num', 'KAD_NUM', 'CAD_NUM', 'kadnum']

# CV-fallback: HSV-диапазон фиолетового контура NSPD (sampled empirically)
PURPLE_HSV_LOW = (130, 60, 80)
PURPLE_HSV_HIGH = (165, 255, 255)

# Минимальная площадь контура в пикселях (отсекаем шум)
MIN_CONTOUR_AREA_PX = 20

# RDP-упрощение полигона: tolerance в пикселях
RDP_EPSILON_PX = 1.5

ALG_VERSION = "v8.0"

# Поля с площадью, которые мы признаём (для калибровки)
AREA_KEYS = (
    "Площадь, кв.м",
    "Общая площадь, кв.м",
    "Площадь общая",
    "Площадь",
)


# ────────────────────── вспомогательные классы / исключения ──────────────────────


class UserExit(Exception):
    """Поднимается, когда пользователь явно запросил выход."""


class NSPDSession:
    def __init__(self):
        self.data = {
            "Земельные участки": {},
            "Здания": {},
            "Сооружения": {},
            "Помещения": {},
            "Объекты незавершенного строительства": {},
            "Другое": {},
        }
        self.processed = set()
        self.session_filename = (
            f"session_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

    def add(self, category, cn, payload):
        self.data.setdefault(category, {})[cn] = payload
        self.processed.add(cn)

    def has(self, cn):
        return cn in self.processed

    def save(self, filename=None):
        non_empty = {k: v for k, v in self.data.items() if v}
        if not non_empty:
            return None
        fname = filename or self.session_filename
        export = {
            "data": non_empty,
            "metadata": {
                "exported_at": datetime.now().isoformat(),
                "version": ALG_VERSION,
                "processed_count": len(self.processed),
            },
        }
        Path(fname).write_text(
            json.dumps(export, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        return fname

    def snapshot(self, cn, info, category):
        fname = (
            f"snapshot_{cn.replace(':', '_').replace('/', '-')}"
            f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        Path(fname).write_text(
            json.dumps({category: {cn: info}}, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
        return fname


# ────────────────────── строковые / cn-хелперы ──────────────────────


def normalize_whitespace(s):
    if not s:
        return ""
    s = s.replace(" ", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_number(s):
    s = (s or "").replace(" ", " ").strip()
    m = re.match(r"^([\d\s]+(?:[.,]\d+)?)", s)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace(",", ".")
    try:
        f = float(raw)
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


def parse_cn_list(text):
    found = CN_FIND_RE.findall(text or "")
    seen = set()
    out = []
    for cn in found:
        if cn not in seen:
            seen.add(cn)
            out.append(cn)
    return out


def read_cn_batch():
    print("\nВставьте кадастровые номера (можно много строк, любые разделители — ';', ',', пробел).")
    print("Пустая строка — старт обработки. Пустая строка сразу — выход из программы.")
    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            return []
        if not line.strip():
            break
        lines.append(line)
    return parse_cn_list("\n".join(lines))


def extract_related_cns_for_recursion(info, self_cn):
    out = []
    seen = set()
    related = info.get("Связанные объекты") if isinstance(info, dict) else None
    if not isinstance(related, dict):
        return out
    for value in related.values():
        if not isinstance(value, list):
            continue
        for cn in value:
            if not isinstance(cn, str):
                continue
            if not CN_PLAIN_RE.match(cn):
                continue
            if cn == self_cn or cn in seen:
                continue
            seen.add(cn)
            out.append(cn)
    return out


# ────────────────────── UI-промпты ──────────────────────


def prompt_after_parent():
    print("\n[?] Enter — следующий КН из списка | 1 — парсить связанные текущего по одному")
    try:
        ans = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans == "1"


def prompt_after_related():
    print("\n[?] Enter — следующий связанный | 1 — выход с сохранением сессии")
    try:
        ans = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return True
    return ans == "1"


# ────────────────────── DOM-помощники Playwright ──────────────────────


async def click_tab(page, tab_name, wait_ms=900):
    selector = f'm-tab-list button:has(m-typography[text="{tab_name}"])'
    loc = page.locator(selector)
    try:
        if await loc.count() > 0:
            await loc.first.click(timeout=4000)
            await page.wait_for_timeout(wait_ms)
            return True
    except Exception:
        pass
    return False


async def visit_all_tabs(page, tabs):
    visited = []
    for name in tabs:
        ok = await click_tab(page, name, wait_ms=900)
        if ok:
            visited.append(name)
    await click_tab(page, "Информация", wait_ms=900)
    return visited


async def extract_header(page):
    return await page.evaluate(
        """() => {
            const known = ["Единое землепользование", "Земельный участок", "Здание",
                           "Сооружение", "Помещение", "Объект незавершенного строительства"];
            const out = { type: null, cn: null, no_coords: false, raw: null };

            function walk(root, cb) {
                if (!root) return;
                const els = root.querySelectorAll ? root.querySelectorAll('*') : [];
                els.forEach(el => {
                    cb(el);
                    if (el.shadowRoot) walk(el.shadowRoot, cb);
                });
            }

            walk(document, (el) => {
                if (!el.getAttribute) return;
                const t = el.getAttribute('text');
                if (!t) return;
                const tt = t.trim();
                if (el.getAttribute('type') === 'h3' && !out.type) {
                    for (const k of known) {
                        if (tt.startsWith(k + ':') || tt.startsWith(k + ' :')) {
                            const idx = tt.indexOf(':');
                            out.type = k;
                            out.cn = tt.slice(idx + 1).trim().replace(/\\s+/g, '');
                            out.raw = tt;
                            return;
                        }
                    }
                }
                if (tt === 'Без координат границ') out.no_coords = true;
            });
            return out;
        }"""
    )


async def extract_info_slots(page):
    return await page.evaluate(
        """() => {
            const slots = [];

            function collectInside(root, bucket) {
                if (!root) return;
                const els = root.querySelectorAll ? root.querySelectorAll('*') : [];
                els.forEach(el => {
                    const t = el.getAttribute && el.getAttribute('text');
                    if (t !== null && t !== undefined && t !== '') bucket.push(t);
                    if (el.shadowRoot) collectInside(el.shadowRoot, bucket);
                });
            }

            function walk(root) {
                if (!root) return;
                const found = root.querySelectorAll ? root.querySelectorAll('m-attribute-slot') : [];
                found.forEach(slot => {
                    const bucket = [];
                    collectInside(slot, bucket);
                    if (slot.shadowRoot) collectInside(slot.shadowRoot, bucket);
                    const cleaned = [];
                    for (const x of bucket) {
                        const v = (x || '').trim();
                        if (v && !cleaned.includes(v)) cleaned.push(v);
                    }
                    if (cleaned.length >= 2) {
                        slots.push({ key: cleaned[0], value: cleaned.slice(1).join(' | ') });
                    }
                });
                const children = root.querySelectorAll ? root.querySelectorAll('*') : [];
                children.forEach(el => { if (el.shadowRoot) walk(el.shadowRoot); });
                if (root.shadowRoot) walk(root.shadowRoot);
            }

            walk(document);
            return slots;
        }"""
    )


async def extract_tab_panels(page):
    return await page.evaluate(
        """() => {
            const panels = [];

            function findHostPanel(content) {
                let n = content;
                while (n) {
                    if (n.tagName === 'M-TAB-PANEL') return n;
                    n = n.parentElement || n.parentNode || n.host;
                }
                return null;
            }

            function resolveTabName(panelHost) {
                if (!panelHost) return null;
                let ariaId = null;
                if (panelHost.shadowRoot) {
                    const inner = panelHost.shadowRoot.querySelector('[aria-labelledby]');
                    if (inner) ariaId = inner.getAttribute('aria-labelledby');
                }
                if (!ariaId) {
                    const inner2 = panelHost.querySelector ? panelHost.querySelector('[aria-labelledby]') : null;
                    if (inner2) ariaId = inner2.getAttribute('aria-labelledby');
                }
                if (!ariaId) return null;

                let btn = null;
                function findBtn(root) {
                    if (!root || btn) return;
                    const candidate = root.getElementById ? root.getElementById(ariaId) : null;
                    if (candidate) { btn = candidate; return; }
                    const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                    all.forEach(el => {
                        if (btn) return;
                        if (el.id === ariaId) { btn = el; return; }
                        if (el.shadowRoot) findBtn(el.shadowRoot);
                    });
                }
                findBtn(document);
                if (!btn) return null;
                return (btn.innerText || btn.textContent || '').trim();
            }

            function walk(root) {
                if (!root) return;
                const contents = root.querySelectorAll ? root.querySelectorAll('m-custom-tab-content') : [];
                contents.forEach(content => {
                    const panelHost = findHostPanel(content);
                    const tabName = resolveTabName(panelHost);

                    const sections = [];
                    const detailsList = content.querySelectorAll('details');

                    if (detailsList && detailsList.length > 0) {
                        detailsList.forEach(det => {
                            const summary = det.querySelector('summary p');
                            const title = summary ? (summary.innerText || summary.textContent || '').trim() : '';
                            const items = [];
                            det.querySelectorAll('button p, li p').forEach(p => {
                                if (p.closest && p.closest('summary')) return;
                                const t = (p.innerText || p.textContent || '').trim();
                                if (t) items.push(t);
                            });
                            sections.push({ title: title, items: items });
                        });
                    }

                    const headerEls = content.querySelectorAll('p.p1Medium, p[class*="p1Medium"]');
                    headerEls.forEach(headerEl => {
                        if (headerEl.closest && headerEl.closest('details')) return;
                        const header = (headerEl.innerText || headerEl.textContent || '').trim();
                        const items = [];
                        let sibling = headerEl.nextElementSibling;
                        while (sibling) {
                            sibling.querySelectorAll('li p, li button p, li button, ul li').forEach(el => {
                                const t = (el.innerText || el.textContent || '').trim();
                                if (t) items.push(t);
                            });
                            sibling = sibling.nextElementSibling;
                        }
                        if (items.length === 0 && (!detailsList || detailsList.length === 0)) {
                            content.querySelectorAll('ul li p, ul li button p').forEach(el => {
                                const t = (el.innerText || el.textContent || '').trim();
                                if (t) items.push(t);
                            });
                        }
                        sections.push({ title: header, items: items });
                    });

                    if (sections.length === 0) {
                        const items = [];
                        content.querySelectorAll('ul li p, ul li button p, ul li button').forEach(el => {
                            const t = (el.innerText || el.textContent || '').trim();
                            if (t) items.push(t);
                        });
                        sections.push({ title: '', items: items });
                    }

                    const allText = (content.innerText || content.textContent || '').trim();
                    panels.push({ tab: tabName, sections: sections, text: allText });
                });

                const children = root.querySelectorAll ? root.querySelectorAll('*') : [];
                children.forEach(el => { if (el.shadowRoot) walk(el.shadowRoot); });
                if (root.shadowRoot) walk(root.shadowRoot);
            }

            walk(document);
            return panels;
        }"""
    )


# ────────────────────── разбор данных карточки ──────────────────────


def parse_info(slots, header_cn):
    info = {}
    for s in slots:
        k = normalize_whitespace(s.get("key", ""))
        v = normalize_whitespace(s.get("value", ""))
        if not k or not v or k == v:
            continue
        if k in NUMERIC_KEYS:
            num = normalize_number(v)
            if num is not None:
                info[NUMERIC_KEYS[k]] = num
                continue
        info[k] = v
    if header_cn:
        info.setdefault("Кадастровый номер", header_cn)
    return info


def extract_cns_from_items(items, self_cn):
    out = []
    seen = set()
    for it in items:
        text = (it or "").strip().replace(" ", "")
        cn = None
        if CN_RE.match(text):
            cn = text
        else:
            m = CN_FIND_RE.search(it or "")
            if m:
                cn = m.group(0)
        if cn and cn != self_cn and cn not in seen:
            seen.add(cn)
            out.append(cn)
    return out


def append_unique(related, key, cns, seen_pairs):
    if not cns:
        return
    related.setdefault(key, [])
    for cn in cns:
        pair = (key, cn)
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            related[key].append(cn)


def classify_section(tab, title, panel_text):
    tlow = (title or "").lower()
    tab_low = (tab or "").lower()
    text_low = (panel_text or "").lower()

    if "количество" in tlow:
        return "count", title
    if "помещен" in tlow:
        return "premises", "Помещения"
    if "разрешенного использования" in tlow:
        return "permitted_use", "Виды разрешенного использования"
    if "часть" in tlow and ("окс" in tlow or "оks" in tlow):
        return "oks_parts", "Части ОКС"
    if ("часть" in tlow or "части" in tlow) and ("зу" in tlow or "земельн" in tlow):
        return "land_parts", "Части ЗУ"
    if "состав" in tlow and "езп" in tlow:
        return "ezp", "Состав ЕЗП"
    if "земельного участка" in tlow and ("границах" in tlow or "расположен" in tlow):
        return "land_link", "Кадастровый номер земельного участка, в границах которого расположен объект"
    if "объект недвижимости" in tlow:
        return "objects_list", "Список объектов"
    if "список объектов" in tlow:
        return "objects_list", "Список объектов"
    if tab_low == "связанные зу":
        return "land_link", "Кадастровый номер земельного участка, в границах которого расположен объект"
    if tab_low == "части окс":
        return "oks_parts", "Части ОКС"
    if tab_low == "части зу":
        return "land_parts", "Части ЗУ"
    if tab_low == "состав езп":
        return "ezp", "Состав ЕЗП"
    if tab_low == "виды разрешенного использования":
        return "permitted_use", "Виды разрешенного использования"
    if tab_low == "объекты":
        return "objects_list", "Список объектов"
    return "unknown", title or "Прочее"


def collect_related(panels, self_cn):
    related = {}
    permitted = []
    seen_pairs = set()

    for panel in panels:
        tab = (panel.get("tab") or "").strip()
        panel_text = panel.get("text", "")
        for section in panel.get("sections", []):
            title = normalize_whitespace(section.get("title", ""))
            items = section.get("items", [])
            cns = extract_cns_from_items(items, self_cn)

            kind, bucket = classify_section(tab, title, panel_text)

            if kind == "count":
                for it in items:
                    v = normalize_whitespace(it)
                    if v.isdigit():
                        related[title] = int(v)
                continue

            if kind == "permitted_use":
                for it in items:
                    v = normalize_whitespace(it)
                    if v and v not in permitted:
                        permitted.append(v)
                continue

            if kind == "unknown":
                if not cns:
                    continue

            append_unique(related, bucket, cns, seen_pairs)

    for key in list(related.keys()):
        if isinstance(related[key], list):
            related[key] = sorted(related[key])

    if permitted:
        related["Виды разрешенного использования"] = permitted

    return related


def print_discovered(related, self_cn):
    rows = []
    for group, value in related.items():
        if not isinstance(value, list):
            continue
        for cn in value:
            if not CN_RE.match(cn) or cn == self_cn:
                continue
            if CN_PART_RE.match(cn):
                kind = "Часть"
            elif group == "Помещения":
                kind = "Помещение"
            elif group == "Список объектов":
                kind = "Здание/Сооружение"
            elif "земельного участка" in group.lower():
                kind = "Земельный участок"
            elif group == "Состав ЕЗП":
                kind = "Часть ЕЗП"
            elif group == "Части ОКС":
                kind = "Часть ОКС"
            elif group == "Части ЗУ":
                kind = "Часть ЗУ"
            else:
                kind = "Объект"
            rows.append((kind, cn))

    if not rows:
        return
    print("\n  Обнаруженные связанные объекты:")
    for kind, cn in rows:
        print(f"    • [{kind}] {cn}")


# ════════════════════════════════════════════════════════════════════════
# НОВОЕ В v8: ИЗВЛЕЧЕНИЕ КОНТУРА (Гибрид WFS → OL-state → screenshot+CV)
# ════════════════════════════════════════════════════════════════════════


def _parsed_area_sqm(info):
    """Ищет в info площадь объекта (несколько ключей)."""
    for k in AREA_KEYS:
        v = info.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
        if isinstance(v, str):
            n = normalize_number(v)
            if n and n > 0:
                return float(n)
    return None


def _lonlat_to_local_meters(lon, lat, lon0, lat0):
    """Локальная плоская проекция (равноугольная) от центроида.
    Точность ±0.1% для объектов до ~10 км. Для зданий/ЗУ — избыточна."""
    lat0_rad = math.radians(lat0)
    dx = (lon - lon0) * 111320.0 * math.cos(lat0_rad)
    dy = (lat - lat0) * 110540.0
    return dx, dy


def _ring_centroid_wgs84(ring):
    """Центроид кольца через формулу планарного полигона на координатах WGS84.
    Возвращает (lon, lat)."""
    if len(ring) < 3:
        if ring:
            return ring[0][0], ring[0][1]
        return 0.0, 0.0
    A = 0.0
    cx = 0.0
    cy = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        cross = x1 * y2 - x2 * y1
        A += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    A *= 0.5
    if abs(A) < 1e-12:
        sx = sum(p[0] for p in ring) / n
        sy = sum(p[1] for p in ring) / n
        return sx, sy
    cx /= (6.0 * A)
    cy /= (6.0 * A)
    return cx, cy


def _ring_area_sqm_local(ring_local_m):
    """Площадь кольца в м² по локальным координатам (метры)."""
    n = len(ring_local_m)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = ring_local_m[i]
        x2, y2 = ring_local_m[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def _geojson_to_local_meters(geojson):
    """Конвертирует GeoJSON Polygon/MultiPolygon (WGS84) → массив колец в локальных метрах.
    Центроид — внешнее кольцо первого полигона.

    Возвращает:
      {
        "тип": str,
        "центроид": {"lon": float, "lat": float},
        "локальные_метры": [[{"dx":..,"dy":..}, ...], ...],
        "площадь_вычисленная_кв_м": float
      }
    """
    if not geojson or "type" not in geojson:
        return None

    gtype = geojson["type"]
    coords = geojson.get("coordinates")
    if not coords:
        return None

    if gtype == "Polygon":
        polygons = [coords]
    elif gtype == "MultiPolygon":
        polygons = coords
    else:
        return None

    # Центроид — внешнее кольцо первого полигона.
    outer_first = polygons[0][0]
    cx, cy = _ring_centroid_wgs84(outer_first)

    rings_local = []
    total_area = 0.0
    for poly in polygons:
        for i_ring, ring in enumerate(poly):
            ring_m = []
            for pt in ring:
                dx, dy = _lonlat_to_local_meters(pt[0], pt[1], cx, cy)
                ring_m.append((dx, dy))
            area = _ring_area_sqm_local(ring_m)
            if i_ring == 0:
                total_area += area
            else:
                total_area -= area  # дырка
            rings_local.append([{"dx": round(x, 3), "dy": round(y, 3)} for x, y in ring_m])

    return {
        "тип": gtype,
        "центроид": {"lon": round(cx, 7), "lat": round(cy, 7)},
        "локальные_метры": rings_local,
        "площадь_вычисленная_кв_м": round(total_area, 2),
    }


async def _fetch_geom_via_wfs(page, cad_num):
    """PRIMARY: запрашивает GeoJSON геометрию через WFS API НСПД.
    Делает fetch из контекста страницы (правильный Referer, cookies).
    Возвращает GeoJSON Polygon/MultiPolygon в WGS84 либо None.
    """
    layers_groups = [("zu", NSPD_ZU_IDS), ("oks", NSPD_OKS_IDS)]

    js = """
    async (args) => {
      const { cad, layerIds, fields } = args;
      const esc = cad.replace(/'/g, "\\\\'");
      for (const id of layerIds) {
        // XML FILTER
        for (const f of fields) {
          const xmlF = `<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0"><fes:PropertyIsEqualTo>`+
            `<fes:ValueReference>${f}</fes:ValueReference><fes:Literal>${esc}</fes:Literal>`+
            `</fes:PropertyIsEqualTo></fes:Filter>`;
          const base = `https://nspd.gov.ru/api/aeggis/v3/${id}/wfs?SERVICE=WFS&VERSION=2.0.0`+
            `&REQUEST=GetFeature&TYPENAMES=ms:layer_${id}&outputFormat=application/json`+
            `&SRSNAME=EPSG:4326&count=1`;
          const url = `${base}&FILTER=${encodeURIComponent(xmlF)}`;
          try {
            const ctl = new AbortController();
            const tid = setTimeout(() => ctl.abort(), 12000);
            const r = await fetch(url, { signal: ctl.signal });
            clearTimeout(tid);
            if (!r.ok) continue;
            const fc = await r.json();
            const feat = fc.features && fc.features[0];
            if (feat && feat.geometry) {
              return { geom: feat.geometry, props: feat.properties || {}, src_url: url, layer_id: id, field: f, method: 'xml' };
            }
          } catch(_) { /* keep trying */ }
        }
        // CQL_FILTER
        for (const f of fields) {
          const url = `https://nspd.gov.ru/api/aeggis/v3/${id}/wfs?SERVICE=WFS&VERSION=2.0.0`+
            `&REQUEST=GetFeature&TYPENAMES=ms:layer_${id}&CQL_FILTER=${encodeURIComponent(`${f}='${esc}'`)}`+
            `&outputFormat=application/json&SRSNAME=EPSG:4326&count=1`;
          try {
            const ctl = new AbortController();
            const tid = setTimeout(() => ctl.abort(), 12000);
            const r = await fetch(url, { signal: ctl.signal });
            clearTimeout(tid);
            if (!r.ok) continue;
            const fc = await r.json();
            const feat = fc.features && fc.features[0];
            if (feat && feat.geometry) {
              return { geom: feat.geometry, props: feat.properties || {}, src_url: url, layer_id: id, field: f, method: 'cql' };
            }
          } catch(_) {}
        }
      }
      return null;
    }
    """

    for _name, ids in layers_groups:
        try:
            result = await page.evaluate(js, {"cad": cad_num, "layerIds": ids, "fields": CAD_FIELDS})
        except Exception:
            result = None
        if result and result.get("geom"):
            return result
    return None


async def _fetch_geom_via_ol_state(page):
    """SECONDARY: пытается достать выбранную геометрию из состояния OpenLayers-карты.
    Большинство prod-инсталляций не expose'ят `ol.Map` в window, но попытка дёшевая."""
    js = """
    () => {
      try {
        if (typeof window === 'undefined') return null;
        // Пробуем найти ol Map через различные пути.
        const candidates = [];
        for (const k of Object.keys(window)) {
          try {
            const v = window[k];
            if (v && typeof v === 'object' && typeof v.getLayers === 'function' && typeof v.getView === 'function') {
              candidates.push(v);
            }
          } catch(_) {}
        }
        if (candidates.length === 0) return null;
        const map = candidates[0];
        const view = map.getView();
        const proj = (view && view.getProjection && view.getProjection().getCode) ? view.getProjection().getCode() : null;
        // Ищем vector-слой с features
        let foundFeat = null;
        map.getLayers().forEach(layer => {
          if (foundFeat) return;
          try {
            const src = layer.getSource && layer.getSource();
            if (src && typeof src.getFeatures === 'function') {
              const feats = src.getFeatures();
              if (feats && feats.length > 0) {
                // Берём feature с наибольшей площадью bbox
                let best = null, bestArea = -1;
                for (const f of feats) {
                  try {
                    const g = f.getGeometry && f.getGeometry();
                    if (!g) continue;
                    const ext = g.getExtent ? g.getExtent() : null;
                    if (!ext) continue;
                    const a = (ext[2]-ext[0]) * (ext[3]-ext[1]);
                    if (a > bestArea) { bestArea = a; best = f; }
                  } catch(_) {}
                }
                if (best) foundFeat = best;
              }
            }
          } catch(_) {}
        });
        if (!foundFeat) return null;
        const g = foundFeat.getGeometry();
        if (!g) return null;
        // Сериализуем в GeoJSON-подобный объект
        const type = g.getType();
        let coords = g.getCoordinates();
        return { geom: { type, coordinates: coords }, proj };
      } catch(e) { return null; }
    }
    """
    try:
        result = await page.evaluate(js)
    except Exception:
        result = None
    if not result or not result.get("geom"):
        return None
    # Если проекция 3857 — конвертируем в WGS84
    proj = result.get("proj") or ""
    geom = result["geom"]
    if "3857" in proj:
        geom = _reproject_3857_to_wgs84(geom)
    return {"geom": geom, "props": {}, "src": "ol_state", "proj_raw": proj}


def _reproject_3857_to_wgs84(geom):
    """EPSG:3857 → EPSG:4326 для GeoJSON-like геометрии."""
    def pt(p):
        x, y = p[0], p[1]
        lon = (x / 20037508.34) * 180.0
        lat = math.degrees(math.atan(math.exp((y / 20037508.34) * math.pi)) * 2 - math.pi / 2)
        return [lon, lat]

    t = geom.get("type")
    c = geom.get("coordinates")
    if not c:
        return geom
    if t == "Polygon":
        return {"type": t, "coordinates": [[pt(p) for p in ring] for ring in c]}
    if t == "MultiPolygon":
        return {"type": t, "coordinates": [[[pt(p) for p in ring] for ring in poly] for poly in c]}
    return geom


async def _read_scale_bar(page):
    """Читает scale-bar из DOM. Возвращает (px_width, meters) либо (None, None)."""
    js = """
    () => {
      const el = document.querySelector('.scale-inner');
      if (!el) return null;
      const txt = (el.innerText || el.textContent || '').trim();
      const w = el.offsetWidth || parseFloat(el.style.width) || null;
      // Парсим "10 m", "100 м", "1 km" и т.п.
      const m = txt.match(/([\\d.,]+)\\s*(km|км|m|м)/i);
      if (!m || !w) return null;
      let val = parseFloat(m[1].replace(',', '.'));
      const unit = m[2].toLowerCase();
      if (unit === 'km' || unit === 'км') val *= 1000.0;
      return { px: w, m: val, raw: txt };
    }
    """
    try:
        return await page.evaluate(js)
    except Exception:
        return None


async def _screenshot_map_canvas(page):
    """Делает скриншот OL-канваса карты. Возвращает (png_bytes, bbox_dict)."""
    js = """
    () => {
      const cv = document.querySelector('.ol-viewport canvas') || document.querySelector('canvas');
      if (!cv) return null;
      const r = cv.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    }
    """
    try:
        bbox = await page.evaluate(js)
        if not bbox or not bbox.get("w"):
            return None, None
        clip = {
            "x": int(bbox["x"]),
            "y": int(bbox["y"]),
            "width": int(bbox["w"]),
            "height": int(bbox["h"]),
        }
        png_bytes = await page.screenshot(clip=clip, type="png")
        return png_bytes, clip
    except Exception:
        return None, None


def _extract_contours_from_image(png_bytes, parsed_area_sqm, scale_px, scale_m):
    """LAST-RESORT: HSV-фильтр фиолетового → cv2.findContours.
    Возвращает (rings_local_meters, computed_area_sqm, m_per_px, thumb_b64)."""
    if not _HAS_CV:
        return None, None, None, None
    if not png_bytes:
        return None, None, None, None

    img = np.array(Image.open(io.BytesIO(png_bytes)).convert("RGB"))
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(PURPLE_HSV_LOW), np.array(PURPLE_HSV_HIGH))

    # Morph close — заглушить шум, замкнуть контур-обводку с заливкой
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # RETR_CCOMP: внешние контуры + 1 уровень вложенности (дырки)
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None, None, None

    # Группируем outer/inner по hierarchy
    # hierarchy[0][i] = [next, prev, first_child, parent]
    outers = []
    holes_by_parent = {}
    for i, h in enumerate(hierarchy[0]):
        parent = h[3]
        area = cv2.contourArea(contours[i])
        if area < MIN_CONTOUR_AREA_PX:
            continue
        if parent == -1:
            outers.append(i)
        else:
            holes_by_parent.setdefault(parent, []).append(i)

    if not outers:
        return None, None, None, None

    # Центроид общей маски (для совмещения rings)
    M = cv2.moments(mask)
    if M["m00"] == 0:
        cx_px = sum(np.mean(contours[i][:, 0, 0]) for i in outers) / len(outers)
        cy_px = sum(np.mean(contours[i][:, 0, 1]) for i in outers) / len(outers)
    else:
        cx_px = M["m10"] / M["m00"]
        cy_px = M["m01"] / M["m00"]

    # Масштаб м/пиксель из scale-bar
    if not scale_px or not scale_m:
        return None, None, None, None
    m_per_px = scale_m / scale_px

    # Площадь полигонов (outer - holes) в пикселях → м²
    total_area_px = 0.0
    for i in outers:
        total_area_px += cv2.contourArea(contours[i])
        for h in holes_by_parent.get(i, []):
            total_area_px -= cv2.contourArea(contours[h])
    computed_area_sqm = total_area_px * (m_per_px ** 2)

    # Коррекция масштаба по parsed_area (если есть)
    corr = 1.0
    if parsed_area_sqm and computed_area_sqm > 0:
        corr = math.sqrt(parsed_area_sqm / computed_area_sqm)
        m_per_px *= corr
        computed_area_sqm = parsed_area_sqm

    # RDP-упрощение + перевод в локальные метры
    rings_local = []
    for i in outers:
        cnt = contours[i]
        eps = RDP_EPSILON_PX
        cnt_simp = cv2.approxPolyDP(cnt, eps, closed=True)
        ring = []
        for p in cnt_simp[:, 0, :]:
            dx = (float(p[0]) - cx_px) * m_per_px
            # OY в пикселях направлена вниз; в метрах — вверх. Инвертируем.
            dy = -(float(p[1]) - cy_px) * m_per_px
            ring.append({"dx": round(dx, 3), "dy": round(dy, 3)})
        rings_local.append(ring)
        for h in holes_by_parent.get(i, []):
            hcnt = contours[h]
            hcnt_simp = cv2.approxPolyDP(hcnt, eps, closed=True)
            hring = []
            for p in hcnt_simp[:, 0, :]:
                dx = (float(p[0]) - cx_px) * m_per_px
                dy = -(float(p[1]) - cy_px) * m_per_px
                hring.append({"dx": round(dx, 3), "dy": round(dy, 3)})
            rings_local.append(hring)

    # PNG thumb с подсветкой маски (для отладки)
    overlay = bgr.copy()
    overlay[mask > 0] = (200, 80, 220)  # BGR фиолет
    blended = cv2.addWeighted(bgr, 0.5, overlay, 0.5, 0)
    cv2.drawContours(blended, [contours[i] for i in outers], -1, (0, 255, 0), 2)
    cv2.circle(blended, (int(cx_px), int(cy_px)), 4, (0, 0, 255), -1)
    # Уменьшаем для b64
    h, w = blended.shape[:2]
    if max(h, w) > 600:
        scale = 600.0 / max(h, w)
        blended = cv2.resize(blended, (int(w * scale), int(h * scale)))
    _ok, buf = cv2.imencode(".png", blended)
    thumb_b64 = base64.b64encode(buf.tobytes()).decode("ascii") if _ok else None

    return rings_local, computed_area_sqm, m_per_px, thumb_b64, (cx_px, cy_px), corr


def _build_payload_from_geojson(geom, parsed_area_sqm, source, scale_meta=None, thumb_b64=None):
    """Из WGS84 GeoJSON строит финальный payload."""
    converted = _geojson_to_local_meters(geom)
    if not converted:
        return None

    computed = converted["площадь_вычисленная_кв_м"]
    corr = None
    if parsed_area_sqm and computed and computed > 0:
        corr = round(parsed_area_sqm / computed, 6)

    payload = {
        "источник": source,
        "тип": converted["тип"],
        "кол-во_колец": len(converted["локальные_метры"]),
        "площадь_заявленная_кв_м": parsed_area_sqm,
        "площадь_вычисленная_кв_м": computed,
        "коэф_коррекции_масштаба": corr,
        "центроид": converted["центроид"],
        "geojson": geom,
        "локальные_метры": converted["локальные_метры"],
        "scale_bar_px": (scale_meta or {}).get("px"),
        "scale_bar_m": (scale_meta or {}).get("m"),
        "м_на_пиксель": None,
        "превью_png_b64": thumb_b64,
        "алгоритм_версия": ALG_VERSION,
    }
    return payload


def _build_payload_from_cv(rings_local, computed_area_sqm, m_per_px, parsed_area_sqm,
                            scale_meta, centroid_px, corr, thumb_b64):
    return {
        "источник": "screenshot_cv",
        "тип": "Polygon" if len(rings_local) == 1 else "MultiPolygon",
        "кол-во_колец": len(rings_local),
        "площадь_заявленная_кв_м": parsed_area_sqm,
        "площадь_вычисленная_кв_м": round(computed_area_sqm, 2),
        "коэф_коррекции_масштаба": round(corr, 6) if corr else None,
        "центроид": {"px_x": round(centroid_px[0], 2), "px_y": round(centroid_px[1], 2)},
        "geojson": None,
        "локальные_метры": rings_local,
        "scale_bar_px": (scale_meta or {}).get("px"),
        "scale_bar_m": (scale_meta or {}).get("m"),
        "м_на_пиксель": round(m_per_px, 6) if m_per_px else None,
        "превью_png_b64": thumb_b64,
        "алгоритм_версия": ALG_VERSION,
    }


async def extract_contour(page, info, cad_num, prefix=""):
    """Главная точка входа: пытается извлечь контур тремя способами.
    Возвращает payload (dict) либо None."""
    if info.get("Без координат границ") is True:
        print(f"{prefix}  [contour] объект без координат границ — пропуск")
        return None

    parsed_area = _parsed_area_sqm(info)
    scale_meta = await _read_scale_bar(page)

    # 1) PRIMARY: WFS
    try:
        wfs = await _fetch_geom_via_wfs(page, cad_num)
    except Exception as e:
        print(f"{prefix}  [contour] WFS exception: {e}")
        wfs = None
    if wfs and wfs.get("geom"):
        payload = _build_payload_from_geojson(wfs["geom"], parsed_area, "wfs", scale_meta)
        if payload:
            payload["wfs_layer_id"] = wfs.get("layer_id")
            payload["wfs_field"] = wfs.get("field")
            payload["wfs_method"] = wfs.get("method")
            n = payload["кол-во_колец"]
            comp = payload["площадь_вычисленная_кв_м"]
            print(f"{prefix}  [contour] ✓ WFS: тип={payload['тип']}, колец={n}, "
                  f"площадь={comp} м² (заявлено {parsed_area})")
            return payload

    # 2) SECONDARY: OL-state
    try:
        ol = await _fetch_geom_via_ol_state(page)
    except Exception as e:
        print(f"{prefix}  [contour] OL-state exception: {e}")
        ol = None
    if ol and ol.get("geom"):
        payload = _build_payload_from_geojson(ol["geom"], parsed_area, "ol_state", scale_meta)
        if payload:
            n = payload["кол-во_колец"]
            comp = payload["площадь_вычисленная_кв_м"]
            print(f"{prefix}  [contour] ✓ OL-state: тип={payload['тип']}, колец={n}, "
                  f"площадь={comp} м²")
            return payload

    # 3) LAST-RESORT: screenshot + CV
    if not _HAS_CV:
        print(f"{prefix}  [contour] CV-fallback недоступен (нет numpy/cv2/PIL) — контур не извлечён")
        return None
    if not scale_meta:
        print(f"{prefix}  [contour] CV-fallback: scale-bar не найден — контур не извлечён")
        return None
    png_bytes, _bbox = await _screenshot_map_canvas(page)
    if not png_bytes:
        print(f"{prefix}  [contour] CV-fallback: скриншот canvas не получен — пропуск")
        return None
    cv_res = _extract_contours_from_image(
        png_bytes, parsed_area, scale_meta.get("px"), scale_meta.get("m")
    )
    if not cv_res:
        print(f"{prefix}  [contour] CV-fallback: фиолетовый полигон не найден на снимке")
        return None
    rings_local, computed_area_sqm, m_per_px, thumb_b64, centroid_px, corr = cv_res
    payload = _build_payload_from_cv(
        rings_local, computed_area_sqm, m_per_px, parsed_area,
        scale_meta, centroid_px, corr, thumb_b64,
    )
    n = payload["кол-во_колец"]
    print(f"{prefix}  [contour] ✓ CV-fallback: колец={n}, "
          f"площадь={payload['площадь_вычисленная_кв_м']} м² "
          f"(коррекция масштаба ×{payload['коэф_коррекции_масштаба']})")
    return payload


# ────────────────────── основная обработка одной карточки ──────────────────────


async def parse_one(page, cadastral_number, session, depth=0):
    url = f"https://nspd.gov.ru/map?query={cadastral_number.replace(':', '%3A')}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        print(f"  [warn] goto domcontentloaded не дождался ({e.__class__.__name__}), пробуем 'load'")
        try:
            await page.goto(url, wait_until="load", timeout=45000)
        except Exception as e2:
            print(f"  [warn] goto load тоже не дождался ({e2.__class__.__name__}); "
                  "продолжаем — карточка может уже быть на экране")
    await page.wait_for_timeout(800)

    prefix = "  " * depth
    print(f"\n{prefix}[*] Объект (depth={depth}): {cadastral_number}")
    print(f"{prefix}[ПАУЗА] Откройте карточку, дождитесь данных справа и нажмите ENTER...")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        raise UserExit()

    header = await extract_header(page)
    obj_type = header.get("type")
    header_cn = header.get("cn") or cadastral_number
    no_coords = header.get("no_coords", False)

    if not obj_type:
        body_text = await page.evaluate("() => (document.body.innerText || '').toLowerCase()")
        if "землепользован" in body_text:
            obj_type = "Единое землепользование"
        elif "земельный участок" in body_text:
            obj_type = "Земельный участок"
        elif "здание" in body_text:
            obj_type = "Здание"
        elif "сооружение" in body_text:
            obj_type = "Сооружение"
        elif "помещение" in body_text:
            obj_type = "Помещение"

    is_land = obj_type in ("Земельный участок", "Единое землепользование")
    if obj_type:
        tabs = LAND_TABS if is_land else BUILDING_TABS
    else:
        tabs = ALL_TABS

    await visit_all_tabs(page, tabs)

    slots = await extract_info_slots(page)
    panels = await extract_tab_panels(page)

    info = parse_info(slots, header_cn)
    if obj_type:
        info.setdefault("Вид объекта недвижимости", obj_type)
    if no_coords:
        info["Без координат границ"] = True

    related = collect_related(panels, header_cn)
    if related:
        info["Связанные объекты"] = related

    # ── НОВОЕ В v8: извлечение контура ──
    try:
        contour = await extract_contour(page, info, header_cn, prefix=prefix)
        if contour:
            info["Контур"] = contour
    except Exception as e:
        print(f"{prefix}  [contour warn] {e.__class__.__name__}: {e}")

    category = CATEGORY_MAP.get(obj_type, "Другое")
    session.add(category, header_cn, info)

    # per-object файл — совместимость с merge_nspd_jsons.py
    fname = f"{header_cn.replace(':', '_').replace('/', '-')}.json"
    Path(fname).write_text(
        json.dumps({category: {header_cn: info}}, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )

    attr_count = sum(1 for k in info if k not in ("Связанные объекты", "Контур"))
    rel_count = sum(len(v) for v in info.get("Связанные объекты", {}).values()
                    if isinstance(v, list))
    contour_tag = ""
    if "Контур" in info:
        contour_tag = f" | Контур: {info['Контур']['источник']}/{info['Контур']['кол-во_колец']} колец"

    print(f"{prefix}[OK] {category} → {header_cn} | Атрибутов: {attr_count} | Связанных: {rel_count}{contour_tag}")
    print_discovered(info.get("Связанные объекты", {}), header_cn)

    try:
        saved = session.save()
        if saved:
            print(f"{prefix}  [autosave] {saved}")
    except Exception as e:
        print(f"{prefix}  [autosave warn] {e}")

    snap_path = None
    try:
        snap_path = session.snapshot(header_cn, info, category)
        print(f"{prefix}  [snapshot] {snap_path}")
    except Exception as e:
        print(f"{prefix}  [snapshot warn] {e}")

    return info, category, snap_path


async def parse_one_safe(page, cn, session, depth=0):
    try:
        return await parse_one(page, cn, session, depth=depth)
    except UserExit:
        raise
    except KeyboardInterrupt:
        raise UserExit()
    except Exception as e:
        print(f"  [!] Ошибка при обработке {cn}: {e}")
        try:
            session.save()
        except Exception as e2:
            print(f"     [autosave warn] {e2}")
        return None


# ────────────────────── обработка пакета ──────────────────────


async def process_batch(page, cns, session):
    total = len(cns)
    for idx, cn in enumerate(cns, 1):
        print(f"\n{'═' * 60}")
        print(f"[{idx}/{total}] Родитель: {cn}")
        print(f"{'═' * 60}")

        if session.has(cn):
            print(f"[skip] {cn} уже обработан ранее в этой сессии")
            continue

        result = await parse_one_safe(page, cn, session, depth=0)
        if result is None:
            continue
        info, _category, _snap = result

        if not prompt_after_parent():
            continue

        related = extract_related_cns_for_recursion(info, cn)
        related = [r for r in related if not session.has(r)]
        if not related:
            print("  [i] У этого родителя нет необработанных связанных полных КН — иду дальше")
            continue

        print(f"\n  [i] Связанных к обработке: {len(related)} (без дальнейшей рекурсии)")
        for jdx, rcn in enumerate(related, 1):
            if session.has(rcn):
                continue
            print(f"\n  ── связанный [{jdx}/{len(related)}] родителя {cn} ──")
            await parse_one_safe(page, rcn, session, depth=1)

            if prompt_after_related():
                raise UserExit()


# ────────────────────── главный цикл и точка входа ──────────────────────


async def run():
    session = NSPDSession()
    print(f"=== NSPD Парсер {ALG_VERSION} ===")
    print(f"[i] Файл сессии: {session.session_filename}")
    print(f"[i] CV-fallback {'доступен' if _HAS_CV else 'НЕдоступен (нет numpy/cv2/PIL)'}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            while True:
                cns = read_cn_batch()
                if not cns:
                    print("\n[i] Пустой ввод — завершаем сессию")
                    break

                already = sum(1 for c in cns if session.has(c))
                print(f"\n[i] Распознано КН: {len(cns)} (новых: {len(cns) - already}, уже обработано: {already})")
                for i, c in enumerate(cns, 1):
                    mark = " (уже есть)" if session.has(c) else ""
                    print(f"    {i:>3}. {c}{mark}")

                try:
                    await process_batch(page, cns, session)
                except UserExit:
                    print("\n[i] Запрошен выход — завершаем сессию")
                    break
        finally:
            try:
                fname = session.save()
                if fname:
                    print(f"\n[+++] СЕССИЯ СОХРАНЕНА: {fname}")
                    print(f"      Объектов: {len(session.processed)}")
                else:
                    print("\n[i] Нет данных для сохранения")
            except Exception as e:
                print(f"\n[!] Финальный save упал: {e}")

            for name, closer in (("context.close", context.close),
                                 ("browser.close", browser.close)):
                try:
                    await closer()
                except Exception as e:
                    print(f"[i] {name}: {e.__class__.__name__} (игнорируем)")


def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[i] Принудительный выход (Ctrl+C)")


if __name__ == "__main__":
    main()
