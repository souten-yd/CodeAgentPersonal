from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import csv


class DependencyMissingError(RuntimeError):
    """Raised when an optional dependency required for extraction is unavailable."""


@dataclass(frozen=True)
class ExtractedPage:
    page_no: int
    text: str


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self._parts.append(value)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _extract_pdf(path: Path) -> list[ExtractedPage]:
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise DependencyMissingError("依存不足: PDF抽出にはPyMuPDF(fitz)が必要です") from exc

    pages: list[ExtractedPage] = []
    with fitz.open(path) as doc:
        for idx, page in enumerate(doc, start=1):
            pages.append(ExtractedPage(page_no=idx, text=page.get_text("text").strip()))
    return pages


def _extract_txt(path: Path) -> list[ExtractedPage]:
    return [ExtractedPage(page_no=1, text=path.read_text(encoding="utf-8", errors="ignore"))]


def _extract_md(path: Path) -> list[ExtractedPage]:
    return _extract_txt(path)


def _extract_csv(path: Path) -> list[ExtractedPage]:
    rows: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(", ".join(col.strip() for col in row if col is not None))
    return [ExtractedPage(page_no=1, text="\n".join(rows))]


def _extract_html(path: Path) -> list[ExtractedPage]:
    parser = _HTMLTextExtractor()
    parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
    return [ExtractedPage(page_no=1, text=parser.get_text())]


def extract_pages(path: Path) -> list[ExtractedPage]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext == ".txt":
        return _extract_txt(path)
    if ext == ".md":
        return _extract_md(path)
    if ext == ".csv":
        return _extract_csv(path)
    if ext == ".html":
        return _extract_html(path)
    raise ValueError(f"Unsupported file type: {ext}")
