from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage


def find_patient_pdfs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".pdf" else []
    if not input_path.exists():
        return []
    try:
        return sorted(p for p in input_path.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    except OSError:
        return []


def read_pdf_pages(path: Path, ocr_cache_dir: Path | None = None) -> tuple[list[DocumentPage], list[str]]:
    warnings: list[str] = []
    pages: list[DocumentPage] = []
    if path.suffix.lower() != ".pdf":
        return [], [f"{path.name}: skipped because it is not a PDF file."]

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001 - corrupted PDFs should fail safely
        warnings.append(f"{path.name}: could not be opened as a PDF ({_short_error(exc)}); trying OCR fallback.")
        return _ocr_fallback_pages(path, ocr_cache_dir, warnings), warnings

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001 - keep the failure visible
            warnings.append(f"{path.name}: encrypted PDF could not be decrypted ({_short_error(exc)}).")

    try:
        page_count = len(reader.pages)
    except Exception as exc:  # noqa: BLE001 - malformed page tree
        warnings.append(f"{path.name}: page list could not be read ({_short_error(exc)}); trying OCR fallback.")
        return _ocr_fallback_pages(path, ocr_cache_dir, warnings), warnings

    if page_count == 0:
        warnings.append(f"{path.name}: PDF has no readable pages.")
        return pages, warnings

    for idx in range(page_count):
        try:
            page = reader.pages[idx]
            text = (page.extract_text() or "").strip()
        except Exception as exc:  # noqa: BLE001 - one bad page should not stop the run
            warnings.append(f"{path.name} p{idx + 1}: text extraction failed ({_short_error(exc)}).")
            text = ""
        pages.append(DocumentPage(path.name, idx + 1, text))

    extracted_chars = sum(len(p.text) for p in pages)
    if extracted_chars >= max(150, len(pages) * 40):
        return pages, warnings

    warnings.append(
        f"{path.name}: native PDF text was sparse ({extracted_chars} chars); trying OCR fallback."
    )
    ocr_pages = _ocr_fallback_pages(path, ocr_cache_dir, warnings)
    if sum(len(p.text) for p in ocr_pages) > extracted_chars:
        pages = ocr_pages
    return pages, warnings


def _ocr_fallback_pages(path: Path, cache_dir: Path | None, warnings: list[str]) -> list[DocumentPage]:
    ocr_text = _read_ocr_cache(path, cache_dir)
    if ocr_text is None:
        try:
            ocr_text = _macos_vision_ocr(path)
        except Exception as exc:  # noqa: BLE001 - OCR is best-effort
            warnings.append(f"{path.name}: OCR fallback failed ({_short_error(exc)}).")
            ocr_text = None
        if ocr_text and cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{path.stem}.ocr.txt").write_text(ocr_text, encoding="utf-8")

    if not ocr_text:
        warnings.append(f"{path.name}: OCR fallback unavailable or empty.")
        return []
    return _split_ocr_pages(path.name, ocr_text)


def _short_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message.replace("\n", " ")[:160]


def _read_ocr_cache(path: Path, cache_dir: Path | None) -> str | None:
    if not cache_dir:
        return None
    cached = cache_dir / f"{path.stem}.ocr.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    return None


def _split_ocr_pages(source: str, text: str) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    current_page = 1
    current: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("--- PAGE ") and line.strip().endswith("---"):
            if current:
                pages.append(DocumentPage(source, current_page, "\n".join(current).strip()))
                current = []
            try:
                current_page = int(line.strip().split()[2])
            except (IndexError, ValueError):
                current_page += 1
        else:
            current.append(line)
    if current:
        pages.append(DocumentPage(source, current_page, "\n".join(current).strip()))
    return pages


def _macos_vision_ocr(path: Path) -> str | None:
    if sys.platform != "darwin":
        return None
    if subprocess.run(["which", "swift"], capture_output=True, text=True).returncode != 0:
        return None
    swift = r'''
import Foundation
import PDFKit
import Vision
import AppKit

let pdfURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let doc = PDFDocument(url: pdfURL) else { exit(2) }
var output = ""
for idx in 0..<doc.pageCount {
    autoreleasepool {
        guard let page = doc.page(at: idx) else { return }
        let bounds = page.bounds(for: .mediaBox)
        let scale: CGFloat = 0.9
        let size = NSSize(width: bounds.width * scale, height: bounds.height * scale)
        let image = NSImage(size: size)
        image.lockFocus()
        NSColor.white.setFill()
        NSRect(origin: .zero, size: size).fill()
        let ctx = NSGraphicsContext.current!.cgContext
        ctx.scaleBy(x: scale, y: scale)
        page.draw(with: .mediaBox, to: ctx)
        image.unlockFocus()
        guard let tiff = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff),
              let cgImage = bitmap.cgImage else {
            output += "\n\n--- PAGE \(idx + 1) ---\n[OCR_RENDER_FAILED]"
            return
        }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .fast
        request.usesLanguageCorrection = false
        request.recognitionLanguages = ["en-US"]
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        do {
            try handler.perform([request])
            let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            output += "\n\n--- PAGE \(idx + 1) ---\n" + lines.joined(separator: "\n")
        } catch {
            output += "\n\n--- PAGE \(idx + 1) ---\n[OCR_FAILED]"
        }
    }
}
print(output)
'''
    result = subprocess.run(
        ["swift", "-", str(path)],
        input=swift,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout if result.returncode == 0 and result.stdout.strip() else None
