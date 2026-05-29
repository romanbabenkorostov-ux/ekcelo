"""md_convert: конвертация Markdown lot_appendix в DOCX / PDF.

Закрывает SPEC §6 «lot_appendix.pdf». Pipeline (fallback-цепочка):
1. **LibreOffice headless** (`soffice --convert-to`) — основной путь;
   умеет и DOCX, и PDF из Markdown через промежуточный HTML.
2. **pandoc** — если установлен (опционально, чище Markdown→DOCX).
3. **Без конвертера** → возвращаем None + предупреждение; .md остаётся.

Дизайн: best-effort. Конвертер не падает, если внешний инструмент
недоступен — `lot_appendix.md` всегда пишется (Stage 3), PDF/DOCX —
бонус при наличии LibreOffice/pandoc.

См. `dev/SPEC_TEMPORAL_REPORTS.md` § MD→DOCX util fallback.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def _has(tool: str) -> bool:
    return shutil.which(tool) is not None


def soffice_bin() -> str | None:
    """Найти бинарь LibreOffice (soffice / libreoffice)."""
    for name in ("soffice", "libreoffice"):
        if _has(name):
            return name
    return None


def available_targets() -> set[str]:
    """Какие форматы конвертации доступны в текущей среде."""
    targets: set[str] = set()
    if soffice_bin() or _has("pandoc"):
        targets.update({"docx", "pdf"})
    return targets


# ─────────────────────────────────────────────────────────────────────────────
#  Markdown → HTML (минимальный, без зависимостей)
# ─────────────────────────────────────────────────────────────────────────────

def _md_to_html(md_text: str) -> str:
    """Очень простой Markdown → HTML конвертер.

    Поддерживает: заголовки (#..######), таблицы GFM, списки (- *),
    жирный (**), курсив (*), параграфы. Этого достаточно для формата
    lot_appendix.md (см. appendix.py). Не претендует на полноту CommonMark.
    """
    import html as _html
    import re

    lines = md_text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    def inline(s: str) -> str:
        s = _html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", s)
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        return s

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Заголовки
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # GFM-таблица: строка с | и следующая строка-разделитель |---|
        if "|" in stripped and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            out.append("<table border='1' cellspacing='0' cellpadding='4'><thead><tr>")
            out.extend(f"<th>{inline(c)}</th>" for c in header)
            out.append("</tr></thead><tbody>")
            i += 2
            while i < n and "|" in lines[i].strip():
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue

        # Списки
        if re.match(r"^[-*]\s+", stripped):
            out.append("<ul>")
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                item = re.sub(r"^[-*]\s+", "", lines[i].strip())
                out.append(f"<li>{inline(item)}</li>")
                i += 1
            out.append("</ul>")
            continue

        # Параграф
        out.append(f"<p>{inline(stripped)}</p>")
        i += 1

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{font-family:'DejaVu Sans',Arial,sans-serif;font-size:11pt}"
        "table{border-collapse:collapse;margin:8px 0}"
        "th{background:#eee;text-align:left}code{font-family:monospace}</style>"
        "</head><body>\n" + "\n".join(out) + "\n</body></html>"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Публичный API
# ─────────────────────────────────────────────────────────────────────────────

def convert_appendix(
    md_path: Path,
    target: str = "pdf",
) -> Path | None:
    """Конвертировать lot_appendix.md в DOCX или PDF.

    Args:
        md_path: путь к .md-файлу (должен существовать).
        target: "pdf" | "docx".

    Returns:
        Path к созданному файлу или None, если конвертер недоступен/упал.
    """
    if target not in ("pdf", "docx"):
        raise ValueError(f"target must be 'pdf' or 'docx', got {target!r}")
    if not md_path.exists():
        raise FileNotFoundError(md_path)

    out_path = md_path.with_suffix(f".{target}")

    # 1. pandoc (если есть) — чистый Markdown → DOCX/PDF.
    if _has("pandoc") and _pandoc_convert(md_path, out_path, target):
        return out_path

    # 2. LibreOffice headless через промежуточный HTML.
    soffice = soffice_bin()
    if soffice and _soffice_convert(md_path, out_path, target, soffice):
        return out_path

    print(f"[appendix-convert] нет конвертера (pandoc/LibreOffice) — "
          f"{target.upper()} пропущен, .md сохранён: {md_path.name}")
    return None


def _pandoc_convert(md_path: Path, out_path: Path, target: str) -> bool:
    try:
        cmd = ["pandoc", str(md_path), "-o", str(out_path)]
        if target == "pdf":
            cmd.extend(["--pdf-engine=weasyprint"]) if _has("weasyprint") else None
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and out_path.exists()
    except (subprocess.SubprocessError, OSError):
        return False


def _soffice_convert(md_path: Path, out_path: Path, target: str, soffice: str) -> bool:
    """MD → HTML → (soffice) → DOCX/PDF в temp профиле LibreOffice."""
    html = _md_to_html(md_path.read_text(encoding="utf-8"))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            html_path = tmp_dir / (md_path.stem + ".html")
            html_path.write_text(html, encoding="utf-8")
            profile = tmp_dir / "lo_profile"
            r = subprocess.run(
                [
                    soffice, "--headless", "--norestore",
                    f"-env:UserInstallation=file://{profile}",
                    "--convert-to", target,
                    "--outdir", str(tmp_dir),
                    str(html_path),
                ],
                capture_output=True, text=True, timeout=180,
            )
            produced = tmp_dir / (md_path.stem + f".{target}")
            if r.returncode != 0 or not produced.exists():
                return False
            shutil.move(str(produced), str(out_path))
            return out_path.exists()
    except (subprocess.SubprocessError, OSError):
        return False
