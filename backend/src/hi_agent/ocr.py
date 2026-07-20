"""Lazy PaddleOCR integration used only for PDF pages that need OCR."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import HiAgentError, ServiceUnavailableError


@dataclass(frozen=True)
class OcrPage:
    page: int
    text: str


class PaddleOcrProvider:
    """Small adapter around PaddleOCR 3.x with lazy model loading."""

    def __init__(self, cache_dir: Path) -> None:
        self._engines: dict[str, Any] = {}
        self.cache_dir = cache_dir

    def recognize_pdf_pages(
        self, content: bytes, page_numbers: list[int], *, language: str, dpi: int, max_pages: int
    ) -> list[OcrPage]:
        if len(page_numbers) > max_pages:
            raise HiAgentError("OCR_PAGE_LIMIT", "需要 OCR 的 PDF 页数超过平台限制", details={"max_pages": max_pages})
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise ServiceUnavailableError(
                "OCR_UNAVAILABLE", "OCR 渲染组件未安装，请安装 Hi-agent OCR 可选依赖"
            ) from exc
        engine = self._engine(language)
        try:
            import numpy as np

            pdf = pdfium.PdfDocument(io.BytesIO(content))
            output: list[OcrPage] = []
            for page_number in page_numbers:
                page = pdf[page_number - 1]
                image = page.render(scale=dpi / 72).to_pil()
                text = self._result_text(list(engine.predict(np.asarray(image))))
                output.append(OcrPage(page_number, text))
            return output
        except HiAgentError:
            raise
        except Exception as exc:
            raise HiAgentError("OCR_FAILED", "PaddleOCR 文字识别失败", details={"reason": str(exc)}) from exc

    def _engine(self, language: str) -> Any:
        cached = self._engines.get(language)
        if cached is not None:
            return cached
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(self.cache_dir))
            from paddleocr import PaddleOCR

            engine = PaddleOCR(
                lang=language,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except ImportError as exc:
            raise ServiceUnavailableError(
                "OCR_UNAVAILABLE", "PaddleOCR 未安装，请执行 uv sync --extra ocr 后重启平台"
            ) from exc
        except Exception as exc:
            raise ServiceUnavailableError("OCR_MODEL_UNAVAILABLE", "PaddleOCR 模型不可用", reason=str(exc)) from exc
        self._engines[language] = engine
        return engine

    @staticmethod
    def _result_text(results: list[Any]) -> str:
        lines: list[str] = []
        for result in results:
            data = getattr(result, "json", result)
            if callable(data):
                data = data()
            if isinstance(data, dict) and "res" in data:
                data = data["res"]
            if isinstance(data, dict):
                texts = data.get("rec_texts") or data.get("texts") or []
                lines.extend(str(item).strip() for item in texts if str(item).strip())
        return "\n".join(lines)
