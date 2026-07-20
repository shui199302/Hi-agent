"""Download/initialize PaddleOCR and verify a scanned PDF page end to end."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from hi_agent.ocr import PaddleOcrProvider


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    font = ImageFont.truetype(str(root / "backend/src/hi_agent/assets/NotoSansSC-Regular.ttf"), 54)
    image = Image.new("RGB", (1400, 260), "white")
    ImageDraw.Draw(image).text((60, 80), "Hi-agent 百度飞桨 OCR 验收 2026", font=font, fill="black")
    pdf_buffer = io.BytesIO()
    pdf = canvas.Canvas(pdf_buffer, pagesize=(1400, 260))
    pdf.drawImage(ImageReader(image), 0, 0, width=1400, height=260)
    pdf.showPage()
    pdf.save()
    provider = PaddleOcrProvider(args.data_dir / "models" / "paddleocr")
    result = provider.recognize_pdf_pages(pdf_buffer.getvalue(), [1], language="ch", dpi=180, max_pages=2)
    text = result[0].text if result else ""
    if "Hi-agent" not in text and "OCR" not in text:
        raise SystemExit(f"OCR smoke test failed: {text!r}")
    print(f"OCR smoke test passed: {text}")


if __name__ == "__main__":
    main()
