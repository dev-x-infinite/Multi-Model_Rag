"""
ingestion.py
Turns raw files (PDF, images) into clean text chunks ready for embedding.

Free-tier only:
- PyPDF2       -> extracts text from PDFs (local, no API)
- pytesseract  -> OCR for images (local, needs the tesseract binary installed)
- No OpenAI / Pinecone / paid API calls anywhere in this file
"""

from pathlib import Path
from dataclasses import dataclass, field

import PyPDF2
from PIL import Image
import pytesseract


@dataclass
class Chunk:
    """One piece of text ready to be embedded and stored."""
    content: str
    source: str          # e.g. "invoice.pdf#page_2" or "receipt.jpg"
    doc_type: str         # "pdf" or "image"
    metadata: dict = field(default_factory=dict)


class MultiModalIngestion:
    """Reads PDFs and images, returns clean text chunks."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        # chunk_size / overlap are in characters, not tokens -- simple and
        # good enough for a portfolio project. Overlap keeps context from
        # getting cut off mid-sentence between chunks.
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # ---------- PDF ----------

    def ingest_pdf(self, file_path: str) -> list[Chunk]:
        """Extract text page by page, then chunk each page's text."""
        path = Path(file_path)
        chunks: list[Chunk] = []

        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                text = text.strip()
                if not text:
                    continue  # skip blank/image-only pages

                for i, piece in enumerate(self._split_text(text)):
                    chunks.append(
                        Chunk(
                            content=piece,
                            source=f"{path.name}#page_{page_num + 1}",
                            doc_type="pdf",
                            metadata={"page": page_num + 1, "chunk": i, "filename": path.name},
                        )
                    )

        return chunks

    # ---------- Image ----------

    def ingest_image(self, file_path: str) -> list[Chunk]:
        """Run OCR on an image and chunk the extracted text."""
        path = Path(file_path)
        image = Image.open(path)

        text = pytesseract.image_to_string(image).strip()
        if not text:
            return []

        return [
            Chunk(
                content=piece,
                source=path.name,
                doc_type="image",
                metadata={"chunk": i, "filename": path.name},
            )
            for i, piece in enumerate(self._split_text(text))
        ]

    # ---------- Router ----------

    def ingest_file(self, file_path: str) -> list[Chunk]:
        """Pick the right handler based on file extension."""
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self.ingest_pdf(file_path)
        elif suffix in (".jpg", ".jpeg", ".png"):
            return self.ingest_image(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

    # ---------- Helpers ----------

    def _split_text(self, text: str) -> list[str]:
        """
        Simple sliding-window chunker.
        Splits on character count with overlap so we don't lose context
        at chunk boundaries. Good enough for a portfolio project --
        no need for LangChain's text splitter.
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start = end - self.chunk_overlap  # step back for overlap
            if start <= 0:
                break
        return chunks