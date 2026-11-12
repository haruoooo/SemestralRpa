"""Turns evidence files into HTML pages that a headless browser can screenshot (e-mails and the HR report).

Usage:
  python -m tools.renderEvidence find <folder> <text>      (first .eml whose decoded subject contains the text)
  python -m tools.renderEvidence eml <file.eml> <out.html>
  python -m tools.renderEvidence xlsx <file.xlsx> <out.html>
"""

import sys
from email import message_from_bytes, policy
from html import escape
from pathlib import Path

from openpyxl import load_workbook

_STYLE = """<style>
body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1d2a3a;background:#fff}
.head{background:#f3f6fa;border:1px solid #d5dde8;border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:14px}
.head b{display:inline-block;width:80px} table{border-collapse:collapse;margin:8px 0 24px;font-size:13px}
th{background:#1f4e79;color:#fff;text-align:left;padding:6px 10px} td{border-bottom:1px solid #ddd;padding:6px 10px;vertical-align:top}
h2{font-size:16px;margin:8px 0} pre{background:#f7f7f7;border:1px solid #ddd;padding:10px;font-size:11px;white-space:pre-wrap}
.note{color:#666;font-size:12px}
</style>"""


def emlToHtml(source: Path, target: Path) -> None:
    message = message_from_bytes(source.read_bytes(), policy=policy.default)
    body = message.get_body(("html", "plain"))
    content = body.get_content() if body.get_content_type() == "text/html" else f"<pre>{escape(body.get_content())}</pre>"
    attachments = "".join(
        f"<h2>Anexo: {escape(part.get_filename() or '')} ({escape(part.get_content_type())})</h2><pre>{escape(_text(part))}</pre>"
        for part in message.iter_attachments()
    )
    head = "".join(f"<div><b>{label}</b>{escape(str(message[key] or ''))}</div>" for label, key in (("De:", "From"), ("Para:", "To"), ("Assunto:", "Subject")))
    target.write_text(f"<!doctype html><meta charset='utf-8'>{_STYLE}<div class='head'>{head}</div>{content}{attachments}", encoding="utf-8")


def _text(part) -> str:
    content = part.get_content()
    text = content if isinstance(content, str) else content.decode("utf-8", "replace")
    text = text.replace("\r\n ", "").replace("\n ", "")  # Unfold long lines (RFC 5545)
    if "BEGIN:VTIMEZONE" in text:  # The time zone block is long and irrelevant for the reader
        text = text[: text.index("BEGIN:VTIMEZONE")] + "(definição do fuso America/Sao_Paulo omitida)\nEND:VCALENDAR"
    return text.strip()[:3000]


def xlsxToHtml(source: Path, target: Path) -> None:
    workbook = load_workbook(source, read_only=True)
    sections = []
    for sheet in workbook.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        header = "".join(f"<th>{escape(str(cell or ''))}</th>" for cell in rows[0])
        body = "".join("<tr>" + "".join(f"<td>{escape(str(cell if cell is not None else ''))}</td>" for cell in row) + "</tr>" for row in rows[1:])
        sections.append(f"<h2>Aba {escape(sheet.title)}</h2><table><tr>{header}</tr>{body}</table>")
    note = f"<p class='note'>Conteúdo do arquivo {escape(source.name)} gerado pelo robô (renderizado para impressão).</p>"
    target.write_text(f"<!doctype html><meta charset='utf-8'>{_STYLE}{note}{''.join(sections)}", encoding="utf-8")


def findEmail(folder: Path, text: str) -> Path | None:
    for path in sorted(folder.glob("*.eml")):
        if text in str(message_from_bytes(path.read_bytes(), policy=policy.default)["Subject"]):
            return path
    return None


if __name__ == "__main__":
    kind, source, target = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    if kind == "find":
        found = findEmail(source, target)
        print(found or "")
    else:
        (emlToHtml if kind == "eml" else xlsxToHtml)(source, Path(target))
