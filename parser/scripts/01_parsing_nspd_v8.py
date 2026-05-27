"""
NSPD Парсер v8.5 (extends standalone v25.0 — adds contour extraction)

Что нового vs v8.4:
- **Удалён `превью_png_b64` из payload** — раздувал JSON (десятки КБ на объект).
  Превью теперь пишется только в debug-dump на диск при неудаче CV.
- **SSL-блокировки WFS/PKK починены** — `ignore_https_errors=True` в
  `browser.new_context()`. Раньше `page.request` падал на:
    `self-signed certificate in certificate chain` (НСПД)
    `certificate has expired` (PKK).
- **Buffered debug-log**: список 15 captured URLs печатается ТОЛЬКО если
  все 5 источников упали. При успехе CV-fallback (как и любого другого)
  лог чистый — одна строка ✓.
- **Явный успех-маркер**: лог при найденном контуре теперь начинается с
  `✅ КОНТУР [source]: ...`.

Что нового vs v8.3 (второй боевой прогон 23:50:0301004:25 — все источники упали):
- **WFS** переведён с `context.request` на `page.request` — наследует
  cookies/Referer открытой страницы, проходит anti-bot фильтры. Подробный
  лог статусов (200/403/404/EXC) и `e.message` вместо просто класса.
- **+ новый источник PKK** (Rosreestr feature API) между WFS и OL-state:
  `pkk.rosreestr.ru/api/features/{1|5}/{cad_num}` + text-search fallback.
- **scale-bar Deep DOM**: обход всех Shadow Root'ов (НСПД использует
  web-components m-* — обычный `querySelectorAll` их не видит). Добавлен
  тег M-TYPOGRAPHY в список text-эвристики.
- **NetworkCapture.all_urls**: хранит все URL'ы (даже отфильтрованные).
  При cap=0 печатает последние 15 для диагностики — видно какие endpoints
  страница реально дёргает.
- **scale-bar fail log** — печатает text-samples (что нашлось похожего на
  scale), чтобы можно было руками докрутить регекс.

Что нового vs v8.2 (фиксы боевого прогона 23:50:0301004:25):
- **KeyError 'кол-во_колец'** — последний legacy-ключ в print лога parse_one()
  заменён на новые 'полигонов'/'колец_всего'.
- **NetworkCapture исключает search/suggest endpoints** — они отдают
  extent квартала вместо геометрии объекта (причина площади 1.4e15 м²).
- **find_by_cad: exact > substring** — выбираем feature с точным
  совпадением cad_num вместо первого попавшегося substring-матча.
- **Auto-reproject EPSG:3857 → WGS84** через `_maybe_reproject_to_wgs84`,
  вызывается в `_build_payload_from_geojson` для всех источников.
- **Sanity-check площади** (`_payload_area_sane`): отвергаем payload где
  computed > 1e10 м² или off-by-100x от parsed_area. Применяется ко
  всем источникам (network_capture, wfs, ol_state).

Что нового vs v8.1 (боевая адаптация под реальную DOM НСПД):
- **NetworkCapture**: пассивный network-sniffer ловит ВСЕ JSON-ответы НСПД
  (когда страница сама загружает feature). Стало PRIMARY-источником —
  работает без активного HTTP-запроса, без CORS/Referer-проблем.
- WFS-fetch переведён с `page.evaluate(fetch)` (CORS-проблема) на
  `context.request.get()` (Playwright APIRequestContext). Корректные headers.
- Scale-bar: множество селекторов (`.ol-scale-line-inner`,
  `.ol-scale-bar-single`, `[class*="scale"]`) + текст-эвристика
  (любой div/span с текстом `/^[\\d.,]+\\s*(m|м|km|км)$/`).
- Screenshot canvas: 6 селекторов вместо 1.
- При неудаче CV — debug-dump на диск: `debug_contour_<cn>_<ts>/` со
  screenshot.png, mask.png, hsv-histogram.png, чтобы можно было
  диагностировать визуально.
- Подробное логирование на каждой ступени fallback'а.

Что нового vs v8.0:
- CV-pipeline отрефакторен под сложные формы (например 90:25:020103:1393 — сеть дорожек).
- Двух-проходная HSV-маска: stroke (резкий пурпур) + fill (полупрозрачный).
- Bounded morphology: маленькое ядро 3×3, 1 итерация — не «съедает» тонкие перешейки.
- `polygons` — семантическая структура: [{outer: ring, holes: [ring,...]}, ...].
- `тип` корректно: Polygon при 1 outer, MultiPolygon при ≥2.
- Адаптивный RDP epsilon: max(0.8, 0.0015 × perimeter).
- Backward-compat: `локальные_метры` (плоский) остаётся.

Что нового vs v7/v25.0:
- Новый шаг в `parse_one()`: после парсинга карточки извлекается контур объекта.
- Гибрид-подход: WFS-API (primary) → DOM/OL-state (secondary) → screenshot+CV (last-resort).
- Если `info["Без координат границ"] == True` — шаг пропускается.
- Результат: `info["Контур"]` со схемой:
    {
      "источник": "wfs" | "ol_state" | "screenshot_cv",
      "тип": "Polygon" | "MultiPolygon",
      "полигонов": int,
      "колец_всего": int,
      "площадь_заявленная_кв_м": float | None,
      "площадь_вычисленная_кв_м": float | None,
      "коэф_коррекции_масштаба": float | None,
      "центроид": {"lon": float, "lat": float} | {"px_x": float, "px_y": float},
      "geojson": {...} | None,           # WGS84, если есть georeference
      "полигоны": [                       # NEW v8.1 — семантическая структура
        {"outer": [{"dx":..,"dy":..}, ...], "holes": [[...], ...]},
        ...
      ],
      "локальные_метры": [...],          # legacy flat (deprecated, оставлен)
      "scale_bar_px": int | None,
      "scale_bar_m": float | None,
      "м_на_пиксель": float | None,
      "превью_png_b64": str | None,
      "алгоритм_версия": "v8.1"
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

# CV-fallback: HSV-диапазоны фиолетового NSPD (sampled empirically).
# Два прохода:
#   1) STROKE — резкая обводка ~ #7030a0 (насыщенный пурпур, S высокий).
#   2) FILL — полупрозрачная заливка поверх серой карты ~ (160,130,200) (S низкий).
# OpenCV HSV: H ∈ [0..179], S,V ∈ [0..255].
PURPLE_STROKE_HSV_LOW = (125, 90, 60)
PURPLE_STROKE_HSV_HIGH = (165, 255, 255)
PURPLE_FILL_HSV_LOW = (125, 30, 100)
PURPLE_FILL_HSV_HIGH = (170, 255, 255)

# Минимальная площадь контура в пикселях (отсекаем шум).
# Для тонких сегментов (~3м при 6 px/m → ~18 px ширина × 30 px длина = 540 px²) — подходит.
MIN_CONTOUR_AREA_PX = 80

# RDP-упрощение полигона: адаптивный epsilon = max(MIN, FRAC * perimeter).
RDP_EPSILON_MIN_PX = 0.8
RDP_EPSILON_FRAC = 0.0015

ALG_VERSION = "v8.5"

# Включить запись debug-dump на диск при неудаче CV-pipeline.
CONTOUR_DEBUG_DUMP = True

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
    """GeoJSON Polygon/MultiPolygon (WGS84) → семантические полигоны в локальных метрах.
    Центроид — внешнее кольцо первого полигона.

    Возвращает:
      {
        "тип": "Polygon" | "MultiPolygon",
        "центроид": {"lon": float, "lat": float},
        "полигоны": [{"outer": [{dx,dy},...], "holes": [[...], ...]}, ...],
        "локальные_метры": [[...], ...],            # legacy flat
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
        polys_raw = [coords]
        out_type = "Polygon"
    elif gtype == "MultiPolygon":
        polys_raw = coords
        out_type = "MultiPolygon"
    else:
        return None

    outer_first = polys_raw[0][0]
    cx, cy = _ring_centroid_wgs84(outer_first)

    polygons_struct = []
    flat_rings = []
    total_area = 0.0

    for poly in polys_raw:
        outer_m = []
        holes_m = []
        for i_ring, ring in enumerate(poly):
            ring_tuples = [_lonlat_to_local_meters(p[0], p[1], cx, cy) for p in ring]
            ring_rounded = [{"dx": round(x, 3), "dy": round(y, 3)} for x, y in ring_tuples]
            area = _ring_area_sqm_local(ring_tuples)
            if i_ring == 0:
                outer_m = ring_rounded
                total_area += area
            else:
                holes_m.append(ring_rounded)
                total_area -= area
            flat_rings.append(ring_rounded)
        polygons_struct.append({"outer": outer_m, "holes": holes_m})

    return {
        "тип": out_type,
        "центроид": {"lon": round(cx, 7), "lat": round(cy, 7)},
        "полигоны": polygons_struct,
        "локальные_метры": flat_rings,
        "площадь_вычисленная_кв_м": round(total_area, 2),
    }


class NetworkCapture:
    """Пассивно слушает все JSON-ответы с nspd.gov.ru/rosreestr.ru/pkk.
    Когда страница сама подгружает feature/featurecollection — мы их видим
    без CORS, без явных запросов. Главный PRIMARY-источник в v8.2."""

    def __init__(self):
        self.features = []        # [{url, feature, source}]
        self.all_urls = []        # [(url, status, content_type)] — для debug
        self._page = None

    async def _on_response(self, resp):
        try:
            url = resp.url
            if not any(d in url for d in (
                "nspd.gov.ru", "rosreestr.ru", "pkk.rosreestr",
            )):
                return
            status = None
            ct = ""
            try:
                status = resp.status
                ct = (resp.headers or {}).get("content-type", "") or ""
            except Exception:
                pass
            self.all_urls.append((url, status, ct))
            # Search/suggest/autocomplete отдают extent квартала/региона.
            if any(skip in url for skip in (
                "/search/", "/suggest", "/autocomplete", "/typeahead",
            )):
                return
            if "json" not in ct.lower():
                if not url.endswith(".json") and "json" not in url.lower():
                    return
            try:
                data = await resp.json()
            except Exception:
                return
            self._scan(data, url)
        except Exception:
            return

    def _scan(self, data, url, depth=0):
        if depth > 4 or data is None:
            return
        if isinstance(data, list):
            for x in data:
                self._scan(x, url, depth + 1)
            return
        if not isinstance(data, dict):
            return
        t = data.get("type")
        if t == "FeatureCollection":
            for f in data.get("features") or []:
                if isinstance(f, dict) and f.get("geometry"):
                    self.features.append({"url": url, "feature": f})
        elif t == "Feature" and data.get("geometry"):
            self.features.append({"url": url, "feature": data})
        # PKK style: {feature: {geometry: ..., attrs: ...}}
        feat = data.get("feature")
        if isinstance(feat, dict) and feat.get("geometry"):
            self.features.append({"url": url, "feature": feat})
        # Подзапросы — рекурсивно
        for k in ("data", "result", "response", "body"):
            if k in data:
                self._scan(data[k], url, depth + 1)

    def attach(self, page):
        self._page = page

        # Wrap async handler into a sync callback that schedules a task.
        def _cb(resp):
            try:
                asyncio.create_task(self._on_response(resp))
            except RuntimeError:
                pass

        self._cb = _cb
        page.on("response", _cb)

    def detach(self):
        if self._page and self._cb:
            try:
                self._page.remove_listener("response", self._cb)
            except Exception:
                pass

    def clear(self):
        self.features.clear()
        self.all_urls.clear()

    def debug_summary(self, max_urls=20):
        """Список последних N URL'ов для диагностики (когда features=0)."""
        return self.all_urls[-max_urls:]

    def find_by_cad(self, cad_num):
        """Ищет feature с переданным кадастровым номером.
        Приоритет: точное совпадение > substring. Точное всегда побеждает,
        иначе ловим search-результаты с extent квартала вместо геометрии объекта."""
        cn_compact = (cad_num or "").replace(" ", "").upper()
        if not cn_compact:
            return None
        cn_core = cn_compact.split("/")[0]
        exact = []
        substr = []
        for entry in self.features:
            f = entry["feature"]
            props = f.get("properties") or f.get("attrs") or {}
            prop_strs = [v.replace(" ", "").upper()
                         for v in props.values() if isinstance(v, str)]
            if any(p == cn_compact for p in prop_strs):
                exact.append(entry)
            elif any(p == cn_core for p in prop_strs):
                exact.append(entry)
            elif any((cn_compact in p) or (cn_core in p) for p in prop_strs):
                substr.append(entry)
        pick = exact[0] if exact else (substr[0] if substr else None)
        if not pick:
            return None
        f = pick["feature"]
        return {
            "geom": f["geometry"],
            "props": f.get("properties") or f.get("attrs") or {},
            "src_url": pick["url"],
        }


async def _fetch_geom_via_wfs(page, cad_num, prefix=""):
    """SECONDARY: WFS API НСПД через page.request (тот же storage state, что и страница).
    Перебирает ZU/OKS layers × CAD_FIELDS. Возвращает {geom, ...} или None.

    v8.4: используем `page.request` вместо `context.request` — он наследует
    cookies/Referer открытой страницы НСПД, поэтому проходит anti-bot фильтры
    лучше. Подробное логирование (status, e.message).
    """
    from urllib.parse import quote
    headers = {
        "Referer": "https://nspd.gov.ru/map",
        "Accept": "application/json, */*",
        "Origin": "https://nspd.gov.ru",
    }
    tried = 0
    statuses = {}
    last_err = None
    for kind, ids in (("zu", NSPD_ZU_IDS), ("oks", NSPD_OKS_IDS)):
        for id_ in ids:
            for f in CAD_FIELDS:
                cql = quote(f"{f}='{cad_num}'", safe="")
                url = (
                    f"https://nspd.gov.ru/api/aeggis/v3/{id_}/wfs?"
                    f"SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&"
                    f"TYPENAMES=ms:layer_{id_}&CQL_FILTER={cql}&"
                    f"outputFormat=application/json&SRSNAME=EPSG:4326&count=1"
                )
                tried += 1
                try:
                    resp = await page.request.get(url, headers=headers, timeout=15000)
                except Exception as e:
                    last_err = f"{e.__class__.__name__}: {str(e)[:140]}"
                    statuses.setdefault("EXC", 0)
                    statuses["EXC"] += 1
                    continue
                st = resp.status
                statuses[st] = statuses.get(st, 0) + 1
                if st != 200:
                    continue
                try:
                    body = await resp.json()
                except Exception:
                    continue
                feats = (body or {}).get("features") or []
                if feats and isinstance(feats[0], dict) and feats[0].get("geometry"):
                    return {
                        "geom": feats[0]["geometry"],
                        "props": feats[0].get("properties") or {},
                        "src_url": url,
                        "layer_id": id_,
                        "field": f,
                        "method": "cql",
                        "kind": kind,
                    }
    summary = ", ".join(f"{k}:{v}" for k, v in statuses.items())
    print(f"{prefix}  [wfs] перебрано {tried} комбинаций — без результата. "
          f"Статусы: [{summary}]" + (f". Последняя ошибка: {last_err}" if last_err else ""))
    return None


async def _fetch_geom_via_pkk(page, cad_num, prefix=""):
    """SECONDARY-B: PKK Rosreestr API. Старый, но даёт feature.geometry для
    большинства объектов. type 1 = ЗУ, type 5 = ОКС. Через page.request."""
    headers = {
        "Referer": "https://pkk.rosreestr.ru/",
        "Accept": "application/json, */*",
        "Origin": "https://pkk.rosreestr.ru",
    }
    tried_urls = []
    for type_id, kind in ((1, "zu"), (5, "oks")):
        url = f"https://pkk.rosreestr.ru/api/features/{type_id}/{cad_num}"
        tried_urls.append((url, "feat"))
        try:
            resp = await page.request.get(url, headers=headers, timeout=15000)
            if resp.status == 200:
                body = await resp.json()
                feat = (body or {}).get("feature")
                if feat and feat.get("geometry"):
                    return {
                        "geom": feat["geometry"],
                        "props": feat.get("attrs") or {},
                        "src_url": url,
                        "type_id": type_id,
                        "kind": kind,
                    }
        except Exception as e:
            print(f"{prefix}  [pkk] type {type_id}: {e.__class__.__name__}: {str(e)[:120]}")
            continue
    # Text-search fallback (returns center/extent if no geometry).
    from urllib.parse import quote
    qurl = (f"https://pkk.rosreestr.ru/api/features/search?"
            f"text={quote(cad_num)}&tolerance=4&limit=1&layers[]=1&layers[]=5")
    tried_urls.append((qurl, "search"))
    try:
        resp = await page.request.get(qurl, headers=headers, timeout=15000)
        if resp.status == 200:
            body = await resp.json()
            feats = (body or {}).get("features") or []
            if feats and feats[0].get("geometry"):
                f0 = feats[0]
                return {
                    "geom": f0["geometry"],
                    "props": f0.get("attrs") or {},
                    "src_url": qurl,
                    "kind": "search",
                }
    except Exception as e:
        print(f"{prefix}  [pkk] search: {e.__class__.__name__}: {str(e)[:120]}")
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


def _first_point(coords):
    """Первая координатная пара любого вложенного GeoJSON-coordinates."""
    c = coords
    while isinstance(c, list) and c and isinstance(c[0], list):
        c = c[0]
    if isinstance(c, list) and len(c) >= 2 and all(isinstance(x, (int, float)) for x in c[:2]):
        return c
    return None


def _maybe_reproject_to_wgs84(geom):
    """Если координаты выходят за пределы [-180,180]/[-90,90] — считаем EPSG:3857
    и reproject'им в WGS84. Иначе возвращаем как есть."""
    if not geom or "coordinates" not in geom:
        return geom
    p = _first_point(geom["coordinates"])
    if not p:
        return geom
    if abs(p[0]) > 180 or abs(p[1]) > 90:
        return _reproject_3857_to_wgs84(geom)
    return geom


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
    """Читает scale-bar из DOM **с обходом shadowRoot** (НСПД использует
    web-components m-* с Shadow DOM). Несколько стратегий + текст-эвристика.
    Возвращает {px, m, raw, sel} либо {debug_tried, debug_text_samples}."""
    js = """
    () => {
      const tried = [];
      const matchUnit = (txt) => txt.match(/([\\d.,]+)\\s*(km|км|m|м)\\b/i);
      const selectors = [
        '.ol-scale-line-inner', '.ol-scale-bar-single', '.ol-scale-bar', '.ol-scale-line',
        '[class*="scale-line"]', '[class*="scale-bar"]', '[class*="scale-inner"]',
        '[class*="ScaleLine"]', '[class*="ScaleBar"]',
        '.scale-control', '.map-scale', 'm-scale-bar',
      ];

      // Обход DOM включая Shadow DOM — собираем все Elements
      function collectAll(root, bag) {
        if (!root || !root.querySelectorAll) return;
        const els = root.querySelectorAll('*');
        els.forEach(el => {
          bag.push(el);
          if (el.shadowRoot) collectAll(el.shadowRoot, bag);
        });
      }
      const all = [];
      collectAll(document, all);

      // 1) Селекторы среди всех найденных
      for (const sel of selectors) {
        let count = 0;
        for (const el of all) {
          try {
            if (!el.matches || !el.matches(sel)) continue;
            count++;
            const txt = (el.innerText || el.textContent || '').trim();
            const m = matchUnit(txt);
            if (!m) continue;
            const r = el.getBoundingClientRect();
            const w = el.offsetWidth || r.width;
            if (!w || w < 10) continue;
            let val = parseFloat(m[1].replace(',', '.'));
            if (m[2].toLowerCase().startsWith('k')) val *= 1000;
            return {px: Math.round(w * 100) / 100, m: val, raw: txt, sel, debug_tried: tried};
          } catch(_) {}
        }
        tried.push({sel, count});
      }

      // 2) Текст-эвристика: любой элемент с коротким текстом-scale + видимая ширина
      const textSamples = [];
      for (const el of all) {
        try {
          if (!['DIV','SPAN','P','LABEL','M-TYPOGRAPHY'].includes(el.tagName)) continue;
          const txt = (el.innerText || el.textContent || '').trim();
          if (!txt || txt.length > 14) continue;
          const m = txt.match(/^([\\d.,]+)\\s*(km|км|m|м)$/i);
          if (!m) continue;
          const r = el.getBoundingClientRect();
          const w = el.offsetWidth || r.width;
          if (!w || w < 20 || w > 400) continue;
          if (textSamples.length < 5) textSamples.push({tag: el.tagName, txt, w});
          let val = parseFloat(m[1].replace(',', '.'));
          if (m[2].toLowerCase().startsWith('k')) val *= 1000;
          return {px: Math.round(w * 100) / 100, m: val, raw: txt,
                  sel: 'text-heuristic:' + el.tagName, debug_tried: tried};
        } catch(_) {}
      }
      return {match: null, debug_tried: tried, debug_text_samples: textSamples};
    }
    """
    try:
        result = await page.evaluate(js)
    except Exception as e:
        return {"_error": f"{e.__class__.__name__}: {e}"}
    if not result or "px" not in result:
        return result
    return result


async def _screenshot_map_canvas(page):
    """Скриншот канваса карты с перебором селекторов.
    Возвращает (png_bytes, clip_dict, used_sel) либо (None, None, tried_log)."""
    js = """
    () => {
      const tried = [];
      const selectors = [
        '.ol-viewport canvas',
        '.ol-unselectable canvas',
        '#map canvas',
        '.map canvas',
        '[class*="map-container"] canvas',
        '[class*="MapContainer"] canvas',
        'canvas',
      ];
      for (const sel of selectors) {
        let els;
        try { els = document.querySelectorAll(sel); }
        catch(_) { continue; }
        tried.push({sel, count: els.length});
        for (const el of els) {
          const r = el.getBoundingClientRect();
          if (r.width < 200 || r.height < 200) continue;
          return {sel, x: r.x, y: r.y, w: r.width, h: r.height, tried};
        }
      }
      return {match: null, tried};
    }
    """
    try:
        bbox = await page.evaluate(js)
    except Exception as e:
        return None, None, f"evaluate-error: {e.__class__.__name__}"
    if not bbox or "w" not in bbox:
        return None, None, bbox.get("tried") if bbox else None
    clip = {
        "x": max(0, int(bbox["x"])),
        "y": max(0, int(bbox["y"])),
        "width": int(bbox["w"]),
        "height": int(bbox["h"]),
    }
    try:
        png_bytes = await page.screenshot(clip=clip, type="png")
    except Exception as e:
        return None, clip, f"screenshot-error: {e.__class__.__name__}"
    return png_bytes, clip, bbox.get("sel")


def _save_debug_dump(cad_num, png_bytes, mask_bytes=None, payload=None, reason=""):
    """Сохраняет диагностический дамп при неудаче CV-pipeline."""
    if not CONTOUR_DEBUG_DUMP:
        return None
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_cn = (cad_num or "unknown").replace(":", "_").replace("/", "-")
        d = Path(f"debug_contour_{safe_cn}_{ts}")
        d.mkdir(exist_ok=True)
        if png_bytes:
            (d / "screenshot.png").write_bytes(png_bytes)
        if mask_bytes:
            (d / "mask.png").write_bytes(mask_bytes)
        info = {"reason": reason, "ts": ts}
        if payload:
            info["payload"] = payload
        (d / "info.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(d)
    except Exception:
        return None


def _decode_png_to_bgr(png_bytes):
    """PNG bytes → BGR numpy array. None если не декодировался."""
    if not _HAS_CV or not png_bytes:
        return None
    try:
        img = np.array(Image.open(io.BytesIO(png_bytes)).convert("RGB"))
    except Exception:
        return None
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def _build_purple_mask(bgr):
    """Двух-проходная HSV-маска: STROKE ∪ FILL.
    Возвращает binary uint8 mask (H×W), 255 — пурпурный пиксель."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    stroke = cv2.inRange(hsv,
                         np.array(PURPLE_STROKE_HSV_LOW),
                         np.array(PURPLE_STROKE_HSV_HIGH))
    fill = cv2.inRange(hsv,
                       np.array(PURPLE_FILL_HSV_LOW),
                       np.array(PURPLE_FILL_HSV_HIGH))
    return cv2.bitwise_or(stroke, fill)


def _clean_mask(mask):
    """Минимальная морфология: OPEN(шум) → CLOSE(склейка микро-разрывов stroke).
    Маленькое ядро 3×3, 1 итерация — НЕ съедает тонкие перешейки сложных форм."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=1)
    return m


def _find_polygons(mask, min_area_px=MIN_CONTOUR_AREA_PX):
    """RETR_CCOMP → группировка outer/holes по hierarchy.
    Возвращает (contours, polygons), где polygons = [{outer: idx, holes: [idx,...]}].
    Маленькие контуры (< min_area_px) отбрасываются.
    """
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not contours or hierarchy is None:
        return [], []

    polygons = []
    keep = set()
    parent_to_outer = {}

    # hierarchy[0][i] = [next, prev, first_child, parent]
    for i, h in enumerate(hierarchy[0]):
        parent = int(h[3])
        if cv2.contourArea(contours[i]) < min_area_px:
            continue
        keep.add(i)
        if parent == -1:
            parent_to_outer[i] = len(polygons)
            polygons.append({"outer": i, "holes": []})

    for i, h in enumerate(hierarchy[0]):
        if i not in keep:
            continue
        parent = int(h[3])
        if parent == -1 or parent not in parent_to_outer:
            continue
        polygons[parent_to_outer[parent]]["holes"].append(i)

    return contours, polygons


def _mask_centroid(mask, contours, polygon_idxs):
    """Центроид общей маски через moments. Fallback — среднее по outer'ам."""
    M = cv2.moments(mask)
    if M["m00"] > 0:
        return M["m10"] / M["m00"], M["m01"] / M["m00"]
    if not polygon_idxs:
        h, w = mask.shape
        return w / 2.0, h / 2.0
    xs = [float(np.mean(contours[p["outer"]][:, 0, 0])) for p in polygon_idxs]
    ys = [float(np.mean(contours[p["outer"]][:, 0, 1])) for p in polygon_idxs]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _polygons_area_px(contours, polygons):
    """Площадь всех полигонов (outer - holes) в пикселях²."""
    total = 0.0
    for p in polygons:
        total += cv2.contourArea(contours[p["outer"]])
        for h in p["holes"]:
            total -= cv2.contourArea(contours[h])
    return max(total, 0.0)


def _adaptive_rdp(contour):
    """Адаптивный RDP: epsilon = max(MIN, FRAC × perimeter)."""
    perim = cv2.arcLength(contour, closed=True)
    eps = max(RDP_EPSILON_MIN_PX, RDP_EPSILON_FRAC * perim)
    return cv2.approxPolyDP(contour, eps, closed=True)


def _ring_to_local_m(contour, cx_px, cy_px, m_per_px):
    """Pixel-ring → массив {dx, dy} в метрах от центроида. OY инвертирован."""
    simp = _adaptive_rdp(contour)
    pts = simp[:, 0, :]
    return [
        {
            "dx": round((float(x) - cx_px) * m_per_px, 3),
            "dy": round(-(float(y) - cy_px) * m_per_px, 3),
        }
        for x, y in pts
    ]


def _localize_polygons(contours, polygons, cx_px, cy_px, m_per_px):
    """polygons[idx]={outer:i, holes:[j..]} → list of {outer: [{dx,dy}], holes: [[...], ...]}."""
    out = []
    for p in polygons:
        outer = _ring_to_local_m(contours[p["outer"]], cx_px, cy_px, m_per_px)
        holes = [_ring_to_local_m(contours[h], cx_px, cy_px, m_per_px) for h in p["holes"]]
        out.append({"outer": outer, "holes": holes})
    return out


def _make_debug_overlay_bytes(bgr, mask, contours, polygons, centroid_px):
    """Превью PNG (bytes): подсветка mask, контуры зелёным, центроид красным.
    v8.5: возвращает raw bytes (раньше — base64 для payload, теперь сохраняется на диск)."""
    overlay = bgr.copy()
    overlay[mask > 0] = (200, 80, 220)
    blended = cv2.addWeighted(bgr, 0.5, overlay, 0.5, 0)
    outer_cnts = [contours[p["outer"]] for p in polygons]
    cv2.drawContours(blended, outer_cnts, -1, (0, 255, 0), 2)
    for p in polygons:
        for h in p["holes"]:
            cv2.drawContours(blended, [contours[h]], -1, (0, 200, 255), 1)
    cv2.circle(blended, (int(centroid_px[0]), int(centroid_px[1])), 4, (0, 0, 255), -1)
    h_img, w_img = blended.shape[:2]
    if max(h_img, w_img) > 800:
        s = 800.0 / max(h_img, w_img)
        blended = cv2.resize(blended, (int(w_img * s), int(h_img * s)))
    ok, buf = cv2.imencode(".png", blended)
    return buf.tobytes() if ok else None


def _extract_contours_from_image(png_bytes, parsed_area_sqm, scale_px, scale_m):
    """LAST-RESORT orchestrator: PNG → семантические полигоны в локальных метрах.
    Возвращает dict с ключами: polygons_local_m, area_sqm, m_per_px, centroid_px, corr, thumb_b64.
    None — если CV-deps отсутствуют, скриншот пустой, scale-bar не задан, или маска пуста.
    """
    if not _HAS_CV or not png_bytes or not scale_px or not scale_m:
        return None

    bgr = _decode_png_to_bgr(png_bytes)
    if bgr is None:
        return None

    raw_mask = _build_purple_mask(bgr)
    mask = _clean_mask(raw_mask)
    contours, polygons = _find_polygons(mask)
    if not polygons:
        return None

    cx_px, cy_px = _mask_centroid(mask, contours, polygons)
    m_per_px = scale_m / scale_px

    area_px = _polygons_area_px(contours, polygons)
    computed_sqm = area_px * (m_per_px ** 2)

    # Калибровка масштаба по заявленной площади (если есть)
    corr = 1.0
    if parsed_area_sqm and computed_sqm > 0:
        corr = math.sqrt(parsed_area_sqm / computed_sqm)
        m_per_px *= corr
        computed_sqm = parsed_area_sqm

    polygons_local_m = _localize_polygons(contours, polygons, cx_px, cy_px, m_per_px)
    overlay_bytes = _make_debug_overlay_bytes(bgr, mask, contours, polygons, (cx_px, cy_px))

    return {
        "polygons_local_m": polygons_local_m,
        "area_sqm": computed_sqm,
        "m_per_px": m_per_px,
        "centroid_px": (cx_px, cy_px),
        "corr": corr,
        "overlay_png": overlay_bytes,
        "num_polygons": len(polygons),
    }


def _build_payload_from_geojson(geom, parsed_area_sqm, source, scale_meta=None):
    """Из WGS84 GeoJSON строит финальный payload.
    Авто-reproject если координаты в EPSG:3857.
    v8.5: превью_png_b64 больше не пишется в payload."""
    geom = _maybe_reproject_to_wgs84(geom)
    converted = _geojson_to_local_meters(geom)
    if not converted:
        return None

    computed = converted["площадь_вычисленная_кв_м"]
    corr = None
    if parsed_area_sqm and computed and computed > 0:
        corr = round(parsed_area_sqm / computed, 6)

    polys = converted["полигоны"]
    rings_total = sum(1 + len(p["holes"]) for p in polys)

    return {
        "источник": source,
        "тип": converted["тип"],
        "полигонов": len(polys),
        "колец_всего": rings_total,
        "площадь_заявленная_кв_м": parsed_area_sqm,
        "площадь_вычисленная_кв_м": computed,
        "коэф_коррекции_масштаба": corr,
        "центроид": converted["центроид"],
        "geojson": geom,
        "полигоны": polys,
        "локальные_метры": converted["локальные_метры"],
        "scale_bar_px": (scale_meta or {}).get("px"),
        "scale_bar_m": (scale_meta or {}).get("m"),
        "м_на_пиксель": None,
        "алгоритм_версия": ALG_VERSION,
    }


def _payload_area_sane(payload, parsed_area_sqm):
    """Грубый sanity-check площади. Отсекает search-результаты
    (extent квартала вместо геометрии объекта) и кривые проекции.

    Правила:
      - computed > 1e10 м² (≥ 10 000 км²) → всегда мусор.
      - parsed известен и computed > 100×parsed → мусор.
      - parsed известен и computed < parsed/100 (off by 2 orders down) → подозрительно, мусор.
    """
    comp = payload.get("площадь_вычисленная_кв_м") or 0
    if comp > 1e10:
        return False
    if parsed_area_sqm and parsed_area_sqm > 0 and comp > 0:
        ratio = comp / parsed_area_sqm
        if ratio > 100.0 or ratio < 0.01:
            return False
    return True


def _build_payload_from_cv(cv_result, parsed_area_sqm, scale_meta):
    """cv_result = output of _extract_contours_from_image (dict).
    v8.5: превью_png_b64 больше не в payload (он сохраняется отдельно на диск)."""
    polys = cv_result["polygons_local_m"]
    rings_total = sum(1 + len(p["holes"]) for p in polys)
    flat_rings = []
    for p in polys:
        flat_rings.append(p["outer"])
        flat_rings.extend(p["holes"])

    corr = cv_result["corr"]
    centroid_px = cv_result["centroid_px"]
    return {
        "источник": "screenshot_cv",
        "тип": "Polygon" if len(polys) == 1 else "MultiPolygon",
        "полигонов": len(polys),
        "колец_всего": rings_total,
        "площадь_заявленная_кв_м": parsed_area_sqm,
        "площадь_вычисленная_кв_м": round(cv_result["area_sqm"], 2),
        "коэф_коррекции_масштаба": round(corr, 6) if corr else None,
        "центроид": {"px_x": round(centroid_px[0], 2), "px_y": round(centroid_px[1], 2)},
        "geojson": None,
        "полигоны": polys,
        "локальные_метры": flat_rings,
        "scale_bar_px": (scale_meta or {}).get("px"),
        "scale_bar_m": (scale_meta or {}).get("m"),
        "м_на_пиксель": round(cv_result["m_per_px"], 6) if cv_result["m_per_px"] else None,
        "алгоритм_версия": ALG_VERSION,
    }


def _save_overlay_png(cad_num, overlay_bytes):
    """Сохраняет debug-overlay рядом с снэпшотом объекта."""
    if not overlay_bytes:
        return None
    try:
        safe_cn = (cad_num or "unknown").replace(":", "_").replace("/", "-")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"contour_overlay_{safe_cn}_{ts}.png"
        Path(fname).write_bytes(overlay_bytes)
        return fname
    except Exception:
        return None


def _success_log(payload, source_label, parsed_area, prefix=""):
    extras = ""
    if source_label == "screenshot_cv" and payload.get("коэф_коррекции_масштаба"):
        extras = f", коррекция ×{payload['коэф_коррекции_масштаба']}"
    print(f"{prefix}  ✅ КОНТУР [{source_label}]: тип={payload['тип']}, "
          f"полигонов={payload['полигонов']}, колец={payload['колец_всего']}, "
          f"площадь={payload['площадь_вычисленная_кв_м']} м² "
          f"(заявлено {parsed_area}){extras}")


async def extract_contour(page, context, capture, info, cad_num, prefix=""):
    """5-уровневый fallback: NetworkCapture → WFS → PKK → OL-state → screenshot+CV.

    v8.5: debug-сообщения копятся в локальный буфер и печатаются ТОЛЬКО если
    все 5 источников провалились. При успехе любой ступени — одна короткая
    строка `✅ КОНТУР [source]: ...`.
    """
    if info.get("Без координат границ") is True:
        print(f"{prefix}  [contour] объект без координат границ — пропуск")
        return None

    parsed_area = _parsed_area_sqm(info)
    debug = []  # buffered debug — печатаем только при полной неудаче

    def dbg(msg):
        debug.append(f"{prefix}  {msg}")

    # 0) NetworkCapture
    cap = capture.find_by_cad(cad_num) if capture else None
    if cap and cap.get("geom"):
        payload = _build_payload_from_geojson(cap["geom"], parsed_area, "network_capture")
        if payload and _payload_area_sane(payload, parsed_area):
            payload["capture_url"] = cap.get("src_url")
            _success_log(payload, "network_capture", parsed_area, prefix)
            return payload
        elif payload:
            dbg(f"[contour] network_capture отвергнут: "
                f"computed={payload['площадь_вычисленная_кв_м']} м² нереалистично")
    else:
        n_cap = len(capture.features) if capture else 0
        dbg(f"[contour] network_capture: подходящей feature не найдено "
            f"(перехвачено features: {n_cap})")

    # 1) WFS
    try:
        wfs = await _fetch_geom_via_wfs(page, cad_num, prefix=prefix)
    except Exception as e:
        dbg(f"[contour] WFS exception: {e.__class__.__name__}: {e}")
        wfs = None
    if wfs and wfs.get("geom"):
        payload = _build_payload_from_geojson(wfs["geom"], parsed_area, "wfs")
        if payload and _payload_area_sane(payload, parsed_area):
            payload["wfs_layer_id"] = wfs.get("layer_id")
            payload["wfs_field"] = wfs.get("field")
            payload["wfs_method"] = wfs.get("method")
            _success_log(payload, "wfs", parsed_area, prefix)
            return payload
        elif payload:
            dbg(f"[contour] WFS отвергнут: computed={payload['площадь_вычисленная_кв_м']} нереалистично")
    else:
        dbg(f"[contour] WFS: без результата")

    # 1b) PKK
    try:
        pkk = await _fetch_geom_via_pkk(page, cad_num, prefix=prefix)
    except Exception as e:
        dbg(f"[contour] PKK exception: {e.__class__.__name__}: {e}")
        pkk = None
    if pkk and pkk.get("geom"):
        payload = _build_payload_from_geojson(pkk["geom"], parsed_area, "pkk")
        if payload and _payload_area_sane(payload, parsed_area):
            payload["pkk_url"] = pkk.get("src_url")
            payload["pkk_kind"] = pkk.get("kind")
            _success_log(payload, "pkk", parsed_area, prefix)
            return payload
        elif payload:
            dbg(f"[contour] PKK отвергнут: computed={payload['площадь_вычисленная_кв_м']} нереалистично")
    else:
        dbg(f"[contour] PKK: нет feature.geometry")

    # 2) OL-state
    try:
        ol = await _fetch_geom_via_ol_state(page)
    except Exception as e:
        dbg(f"[contour] OL-state exception: {e.__class__.__name__}: {e}")
        ol = None
    if ol and ol.get("geom"):
        payload = _build_payload_from_geojson(ol["geom"], parsed_area, "ol_state")
        if payload and _payload_area_sane(payload, parsed_area):
            _success_log(payload, "ol_state", parsed_area, prefix)
            return payload
        elif payload:
            dbg(f"[contour] OL-state отвергнут: computed={payload['площадь_вычисленная_кв_м']} нереалистично")
    else:
        dbg("[contour] OL-state: map-instance не найден в window.*")

    # 3) CV
    if not _HAS_CV:
        dbg("[contour] CV-fallback недоступен (нет numpy/cv2/PIL)")
        _flush_debug(debug)
        return None

    scale_meta = await _read_scale_bar(page)
    valid_scale = bool(scale_meta and scale_meta.get("px") and scale_meta.get("m"))

    png_bytes, clip, used_sel = await _screenshot_map_canvas(page)
    if not png_bytes:
        dbg(f"[contour] CV-fallback: скриншот canvas не получен ({used_sel})")
        _flush_debug(debug)
        return None

    if not valid_scale:
        tried = (scale_meta or {}).get("debug_tried") or []
        nonzero = [t for t in tried if t.get("count")]
        samples = (scale_meta or {}).get("debug_text_samples") or []
        dbg(f"[contour] CV-fallback: scale-bar не найден. "
            f"Селекторы (>0): {nonzero[:5] or 'none'}")
        if samples:
            dbg(f"    text-samples: {samples}")
        elif scale_meta and scale_meta.get("_error"):
            dbg(f"    evaluate error: {scale_meta['_error']}")
        dump = _save_debug_dump(cad_num, png_bytes, reason="no_scale_bar")
        if dump:
            dbg(f"[contour] debug-dump: {dump}")
        _flush_debug(debug)
        return None

    cv_res = _extract_contours_from_image(
        png_bytes, parsed_area, scale_meta.get("px"), scale_meta.get("m")
    )
    if not cv_res:
        dump = _save_debug_dump(cad_num, png_bytes, reason="no_purple_mask",
                                payload={"scale_meta": scale_meta})
        dbg(f"[contour] CV-fallback: фиолетовый полигон не найден"
            + (f". debug: {dump}" if dump else ""))
        _flush_debug(debug)
        return None

    payload = _build_payload_from_cv(cv_res, parsed_area, scale_meta)
    _success_log(payload, "screenshot_cv", parsed_area, prefix)
    # Сохраняем overlay PNG на диск (не в payload — раздувал JSON)
    overlay_path = _save_overlay_png(cad_num, cv_res.get("overlay_png"))
    if overlay_path:
        print(f"{prefix}  [contour] overlay → {overlay_path}")
    return payload


def _flush_debug(debug_lines):
    """Печатает накопленный debug-лог одним блоком при провале всех источников."""
    if not debug_lines:
        return
    print("\n".join(debug_lines))
    print(debug_lines[0].split(']')[0].split('[')[0] + "❌ КОНТУР: все источники упали")


# ────────────────────── основная обработка одной карточки ──────────────────────


async def parse_one(page, context, capture, cadastral_number, session, depth=0):
    if capture is not None:
        capture.clear()
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

    # ── v8.2: извлечение контура (4-уровневый fallback) ──
    try:
        contour = await extract_contour(page, context, capture, info, header_cn, prefix=prefix)
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
        contour_tag = (f" | Контур: {info['Контур']['источник']}/"
                       f"{info['Контур'].get('полигонов', 0)} полиг./"
                       f"{info['Контур'].get('колец_всего', 0)} колец")

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


async def parse_one_safe(page, context, capture, cn, session, depth=0):
    try:
        return await parse_one(page, context, capture, cn, session, depth=depth)
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


async def process_batch(page, context, capture, cns, session):
    total = len(cns)
    for idx, cn in enumerate(cns, 1):
        print(f"\n{'═' * 60}")
        print(f"[{idx}/{total}] Родитель: {cn}")
        print(f"{'═' * 60}")

        if session.has(cn):
            print(f"[skip] {cn} уже обработан ранее в этой сессии")
            continue

        result = await parse_one_safe(page, context, capture, cn, session, depth=0)
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
            await parse_one_safe(page, context, capture, rcn, session, depth=1)

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
        # ignore_https_errors=True — фиксит WFS/PKK "self-signed cert in chain"
        # / "certificate has expired" (v8.5).
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        # v8.2: NetworkCapture — пассивно ловит GeoJSON-ответы НСПД
        capture = NetworkCapture()
        capture.attach(page)
        print("[i] NetworkCapture attached — слушаю JSON-ответы НСПД на response-event")

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
                    await process_batch(page, context, capture, cns, session)
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
