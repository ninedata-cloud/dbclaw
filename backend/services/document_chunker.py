import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class DocumentChunker:
    """Split documents into chunks for embedding."""

    def __init__(self, chunk_size: int = 1000, overlap: int = 200):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str, filename: str, file_type: str) -> List[Dict[str, any]]:
        """
        Split text into chunks with overlap.
        Returns list of dicts with 'content' and 'metadata'.
        """
        if not text or not text.strip():
            return []

        # Split on paragraph boundaries first
        paragraphs = text.split("\n\n")

        chunks = []
        current_chunk = ""
        chunk_index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If adding this paragraph exceeds chunk size, save current chunk
            if current_chunk and len(current_chunk) + len(para) + 2 > self.chunk_size:
                chunks.append({
                    "content": current_chunk.strip(),
                    "metadata": {
                        "filename": filename,
                        "file_type": file_type,
                        "chunk_index": chunk_index,
                    }
                })
                chunk_index += 1

                # Start new chunk with overlap from previous chunk
                if self.overlap > 0 and len(current_chunk) > self.overlap:
                    current_chunk = current_chunk[-self.overlap:] + "\n\n" + para
                else:
                    current_chunk = para
            else:
                # Add paragraph to current chunk
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para

        # Add final chunk
        if current_chunk.strip():
            chunks.append({
                "content": current_chunk.strip(),
                "metadata": {
                    "filename": filename,
                    "file_type": file_type,
                    "chunk_index": chunk_index,
                }
            })

        logger.info(f"Chunked {filename} into {len(chunks)} chunks")
        return chunks
