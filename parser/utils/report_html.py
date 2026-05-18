# -*- coding: utf-8 -*-
"""
EkceloFoto — report_html.py  v2.5
====================================
Генерирует самодостаточный HTML-отчёт из SQLite-базы.
Открывается в браузере без сервера.

Запуск:
    python report_html.py --db "C:\\Photos\\index.db"
    python report_html.py --db "C:\\Photos\\index.db" --out "C:\\Photos\\report.html"
"""
import sqlite3, json, argparse, sys
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────

def load_tree(conn):
    conn.row_factory = sqlite3.Row
    nodes = conn.execute(
        "SELECT * FROM nodes ORDER BY depth, path COLLATE NOCASE"
    ).fetchall()
    files = conn.execute("""
        SELECT f.*, n.path AS node_path
        FROM files f LEFT JOIN nodes n ON f.node_id = n.node_id
        ORDER BY f.filename COLLATE NOCASE
    """).fetchall()

    tree = {}
    roots = []
    for row in nodes:
        entry = dict(row)
        entry['children'] = []
        entry['files']    = []
        tree[row['node_id']] = entry

    for entry in tree.values():
        pid = entry['parent_id']
        if pid and pid in tree:
            tree[pid]['children'].append(entry)
        else:
            roots.append(entry)

    for row in files:
        nid = row['node_id']
        if nid and nid in tree:
            tree[nid]['files'].append(dict(row))

    return roots, tree


def load_stats(conn):
    r = conn.execute("""
        SELECT
            COUNT(*)                                                AS total,
            SUM(CASE WHEN gps_lat IS NOT NULL    THEN 1 ELSE 0 END) AS with_gps,
            SUM(CASE WHEN exif_loc_path IS NOT NULL
                     AND exif_loc_path != ''     THEN 1 ELSE 0 END) AS with_loc,
            SUM(CASE WHEN path_mismatch = 1      THEN 1 ELSE 0 END) AS path_mismatches,
            SUM(CASE WHEN date_mismatch = 1      THEN 1 ELSE 0 END) AS date_mismatches
        FROM files
    """).fetchone()
    return {
        'total':          r[0] or 0,
        'with_gps':       r[1] or 0,
        'with_loc':       r[2] or 0,
        'path_mismatches':r[3] or 0,
        'date_mismatches':r[4] or 0,
    }


# ─────────────────────────────────────────────────────────────────────────────

def esc(s):
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')


def render_file_row(f):
    name   = esc(f.get('filename',''))
    size   = f.get('size_bytes') or 0
    size_s = f'{size/1024:.0f} КБ' if size else '—'
    date   = esc(f.get('date_taken','') or '—')
    lat, lon       = f.get('gps_lat'), f.get('gps_lon')
    path_mis       = f.get('path_mismatch', 0)
    date_mis       = f.get('date_mismatch', 0)
    exif_source    = esc(f.get('exif_source','') or '')

    gps_badge = '<span class="badge gps">GPS</span>' if lat is not None else '<span class="badge nogps">нет GPS</span>'

    badges = gps_badge
    if path_mis:
        tip = esc(f.get('exif_loc_path') or '')
        badges += f' <span class="badge mismatch" title="EXIF: {tip}">⚠ путь</span>'
    if date_mis:
        badges += ' <span class="badge date-mis" title="mtime файла ≠ DateTimeOriginal. Запустите watchdog --fix-dates">⚠ дата</span>'
    if exif_source:
        badges += f' <span class="badge src" title="Источник">{esc(exif_source[:12])}</span>'

    row_cls = 'file-row' + (' mismatch-row' if path_mis or date_mis else '')
    abs_path = esc(f.get('abs_path',''))
    return f'<tr class="{row_cls}"><td class="fname" title="{abs_path}">{name}</td><td>{size_s}</td><td>{date}</td><td>{badges}</td></tr>'


def count_all(node):
    total = len(node['files'])
    for c in node['children']:
        total += count_all(c)
    return total


def render_node(node, depth=0):
    nid      = node['node_id']
    name     = esc(node['name'])
    path     = esc(node['path'])
    children = node['children']
    files    = node['files']
    n_gps    = sum(1 for f in files if f.get('gps_lat') is not None)
    n_pathm  = sum(1 for f in files if f.get('path_mismatch'))
    n_datem  = sum(1 for f in files if f.get('date_mismatch'))
    total    = count_all(node)

    summary = f'{total} ф.'
    if files:
        pct = int(n_gps / len(files) * 100) if len(files) else 0
        summary += f' | GPS {pct}%'
    if n_pathm: summary += f' | <span class="warn">⚠пути:{n_pathm}</span>'
    if n_datem: summary += f' | <span class="date-warn">⚠даты:{n_datem}</span>'

    files_html = ''
    if files:
        rows = ''.join(render_file_row(f) for f in files)
        files_html = f'''<div class="file-list"><table>
          <thead><tr><th>Файл</th><th>Размер</th><th>Дата съёмки</th><th>Статус</th></tr></thead>
          <tbody>{rows}</tbody></table></div>'''

    children_html = ''.join(render_node(c, depth+1) for c in children)
    open_attr = 'open' if depth < 2 else ''

    return f'''<details class="node depth-{depth}" id="n-{nid}" {open_attr}>
  <summary class="node-summary">
    <span class="node-name">{name}</span>
    <span class="node-path">{path}</span>
    <span class="node-stats">{summary}</span>
  </summary>
  {files_html}
  {children_html}
</details>'''


# ─────────────────────────────────────────────────────────────────────────────

CSS = """
:root{--bg:#0d0f14;--surface:#161a24;--border:#252b3a;--accent:#e8ff47;--accent2:#47c8ff;--text:#e4e8f0;--muted:#5a6480;--danger:#ff5c5c;--warn:#f59e0b}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;padding:24px}
h1{font-size:22px;color:var(--accent);margin-bottom:6px}
.meta{font-size:12px;color:var(--muted);margin-bottom:20px}
.stats-bar{display:flex;gap:24px;margin-bottom:24px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px 20px;flex-wrap:wrap}
.stat{display:flex;flex-direction:column}
.stat-val{font-size:24px;font-weight:700;color:var(--accent);font-family:monospace}
.stat-val.warn{color:var(--warn)}
.stat-lbl{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.search-bar{margin-bottom:16px;display:flex;gap:10px}
#search{background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--text);padding:8px 14px;font-size:14px;width:360px;outline:none}
#search:focus{border-color:var(--accent2)}
.btn{background:var(--surface);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:8px 14px;cursor:pointer;font-size:13px;transition:all .15s}
.btn:hover{border-color:var(--accent);color:var(--accent)}
details.node{margin-bottom:4px}
details.node>summary{list-style:none;display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:6px;cursor:pointer;border:1px solid transparent;transition:background .12s;user-select:none}
details.node>summary:hover{background:rgba(255,255,255,.04);border-color:var(--border)}
details.node[open]>summary{background:rgba(232,255,71,.06);border-color:rgba(232,255,71,.2)}
details.node>summary::before{content:'▶';font-size:10px;color:var(--muted);transition:transform .15s;flex-shrink:0}
details.node[open]>summary::before{transform:rotate(90deg)}
.node-name{font-weight:700;min-width:180px}
.depth-0 .node-name{color:var(--accent);font-size:15px}
.depth-1 .node-name{color:var(--accent2)}
.node-path{font-family:monospace;font-size:11px;color:var(--muted);flex:1}
.node-stats{font-size:11px;color:var(--muted);white-space:nowrap;font-family:monospace}
.warn{color:var(--warn)}
.date-warn{color:#fb923c}
details.node details.node{margin-left:24px}
.file-list{margin:4px 0 4px 32px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.4px;padding:4px 8px;border-bottom:1px solid var(--border)}
td{padding:3px 8px;border-bottom:1px solid rgba(255,255,255,.04)}
.fname{font-family:monospace;color:var(--accent2);max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mismatch-row td{background:rgba(255,92,92,.06)}
.badge{font-size:9px;padding:1px 5px;border-radius:3px;font-family:monospace}
.badge.gps{background:rgba(232,255,71,.15);color:var(--accent)}
.badge.nogps{background:rgba(90,100,128,.2);color:var(--muted)}
.badge.mismatch{background:rgba(245,158,11,.15);color:var(--warn);cursor:help}
.badge.date-mis{background:rgba(251,146,60,.15);color:#fb923c;cursor:help}
.badge.src{background:rgba(71,200,255,.1);color:var(--accent2)}
.hidden{display:none !important}
"""

JS = r"""
document.getElementById('search').addEventListener('input', function() {
  const q = this.value.trim().toLowerCase();
  document.querySelectorAll('.file-row').forEach(tr => {
    const match = !q || tr.querySelector('.fname').textContent.toLowerCase().includes(q);
    tr.classList.toggle('hidden', !match);
  });
  document.querySelectorAll('details.node').forEach(d => {
    const hasRows = d.querySelectorAll('.file-row:not(.hidden)').length > 0;
    d.classList.toggle('hidden', q ? !hasRows : false);
    if (q && hasRows) d.open = true;
  });
});
document.getElementById('expand-all').addEventListener('click', () =>
  document.querySelectorAll('details.node').forEach(d => d.open = true));
document.getElementById('collapse-all').addEventListener('click', () =>
  document.querySelectorAll('details.node').forEach(d => d.open = false));
"""


def build_html(roots, stats, generated_at, db_path):
    tree_html = ''.join(render_node(n) for n in roots) or \
        '<p style="color:var(--muted);padding:20px">База данных пуста.</p>'

    pct_gps = int(stats['with_gps']  / stats['total'] * 100) if stats['total'] else 0
    pct_loc = int(stats['with_loc']  / stats['total'] * 100) if stats['total'] else 0

    warn_color_path = "var(--warn)" if stats['path_mismatches'] else "var(--accent)"
    warn_color_date = "var(--warn)" if stats['date_mismatches'] else "var(--accent)"

    return f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>EkceloFoto — Отчёт</title><style>{CSS}</style></head>
<body>
<h1>📁 EkceloFoto — Объектная база</h1>
<div class="meta">Сформирован: {generated_at} · База: {esc(db_path)}</div>

<div class="stats-bar">
  <div class="stat"><span class="stat-val">{stats['total']}</span><span class="stat-lbl">фото</span></div>
  <div class="stat"><span class="stat-val">{stats['with_gps']} <small style="font-size:14px;color:var(--muted)">({pct_gps}%)</small></span><span class="stat-lbl">с GPS</span></div>
  <div class="stat"><span class="stat-val">{stats['with_loc']} <small style="font-size:14px;color:var(--muted)">({pct_loc}%)</small></span><span class="stat-lbl">с loc.path</span></div>
  <div class="stat"><span class="stat-val" style="color:{warn_color_path}">{stats['path_mismatches']}</span><span class="stat-lbl">⚠ пути</span></div>
  <div class="stat"><span class="stat-val" style="color:{warn_color_date}">{stats['date_mismatches']}</span><span class="stat-lbl">⚠ даты</span></div>
</div>

<div class="search-bar">
  <input id="search" type="search" placeholder="Поиск по имени файла…"/>
  <button class="btn" id="expand-all">Раскрыть всё</button>
  <button class="btn" id="collapse-all">Свернуть всё</button>
</div>

<div id="tree">{tree_html}</div>
<script>{JS}</script>
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EkceloFoto — HTML-отчёт из SQLite")
    parser.add_argument('--db',  required=True)
    parser.add_argument('--out', default='')
    args = parser.parse_args()

    db_path  = Path(args.db).resolve()
    out_path = Path(args.out).resolve() if args.out else db_path.with_name('report.html')

    if not db_path.exists():
        sys.exit(f'БД не найдена: {db_path}')

    conn = sqlite3.connect(str(db_path))
    try:
        roots, _ = load_tree(conn)
        stats    = load_stats(conn)
    finally:
        conn.close()

    html = build_html(roots, stats, datetime.now().strftime('%d.%m.%Y %H:%M:%S'), str(db_path))
    out_path.write_text(html, encoding='utf-8')

    print(f'Отчёт сохранён: {out_path}')
    print(f'Файлов: {stats["total"]} | GPS: {stats["with_gps"]} '
          f'| ⚠ пути: {stats["path_mismatches"]} | ⚠ даты: {stats["date_mismatches"]}')


if __name__ == '__main__':
    main()
