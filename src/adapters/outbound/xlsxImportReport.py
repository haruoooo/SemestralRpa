"""HR report (importReport<hash8>.xlsx), in Portuguese, with the outcome and every refused row."""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from src.domain.scheduleImport import RowIssue

_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")


class XlsxImportReport:
    def __init__(self, outputDir: Path):
        self._outputDir = outputDir

    def write(self, fileName: str, fileHash: str, outcome: str, summary: dict[str, object], issues: list[RowIssue]) -> str:
        workbook = Workbook()
        overview = workbook.active
        overview.title = "Resumo"
        overview.append(["Campo", "Valor"])
        overview.append(["Arquivo", fileName])
        overview.append(["Situação", outcome])
        for label, value in summary.items():
            overview.append([label, value])
        overview.append(["Código do arquivo (SHA-256)", fileHash])
        _styleHeader(overview, widths=(34, 90))

        details = workbook.create_sheet("Linhas recusadas")
        details.append(["Aba", "Linha", "Coluna", "Motivo"])
        for issue in issues:
            details.append([issue.sheet, issue.rowNumber or "-", issue.column or "-", issue.message])
        if not issues:
            details.append(["-", "-", "-", "Nenhuma linha recusada"])
        _styleHeader(details, widths=(16, 8, 26, 100))

        self._outputDir.mkdir(parents=True, exist_ok=True)
        target = self._outputDir / f"importReport{fileHash[:8]}.xlsx"
        workbook.save(target)
        return str(target)


def _styleHeader(sheet, widths: tuple[int, ...]) -> None:
    for cell in sheet[1]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
    for index, width in enumerate(widths):
        sheet.column_dimensions[chr(ord("A") + index)].width = width
    sheet.freeze_panes = "A2"
