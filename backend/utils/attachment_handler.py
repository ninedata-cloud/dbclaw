"""
File attachment handling for chat messages
"""
import os
import base64
import mimetypes
from pathlib import Path
from typing import List, Dict, Any
from PIL import Image
import io


class AttachmentHandler:
    """Handle file attachments for chat messages"""

    UPLOAD_DIR = Path("uploads/chat_attachments")
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    ALLOWED_TEXT_TYPES = {".txt", ".log", ".sql", ".json", ".yaml", ".yml", ".md", ".csv"}
    ALLOWED_DOC_TYPES = {".pdf", ".doc", ".docx"}

    @classmethod
    def init_upload_dir(cls):
        """Initialize upload directory"""
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_allowed_file(cls, filename: str) -> bool:
        """Check if file type is allowed"""
        ext = Path(filename).suffix.lower()
        return ext in (cls.ALLOWED_IMAGE_TYPES | cls.ALLOWED_TEXT_TYPES | cls.ALLOWED_DOC_TYPES)

    @classmethod
    def get_file_type(cls, filename: str) -> str:
        """Get file type category"""
        ext = Path(filename).suffix.lower()
        if ext in cls.ALLOWED_IMAGE_TYPES:
            return "image"
        elif ext in cls.ALLOWED_TEXT_TYPES:
            return "text"
        elif ext in cls.ALLOWED_DOC_TYPES:
            return "document"
        return "unknown"

    @classmethod
    async def save_attachment(cls, file_content: bytes, filename: str, session_id: int) -> Dict[str, Any]:
        """Save attachment and return metadata"""
        cls.init_upload_dir()

        # Generate unique filename
        import uuid
        file_ext = Path(filename).suffix
        unique_filename = f"{session_id}_{uuid.uuid4().hex}{file_ext}"
        file_path = cls.UPLOAD_DIR / unique_filename

        # Save file
        with open(file_path, "wb") as f:
            f.write(file_content)

        # Get file info
        file_size = len(file_content)
        file_type = cls.get_file_type(filename)
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        metadata = {
            "filename": filename,
            "stored_filename": unique_filename,
            "file_type": file_type,
            "mime_type": mime_type,
            "size": file_size,
            "path": str(file_path),
        }

        return metadata

    @classmethod
    async def process_image_for_vision(cls, file_path: str) -> str:
        """Process image for vision API (convert to base64)"""
        try:
            with Image.open(file_path) as img:
                # Resize if too large
                max_size = (1024, 1024)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Convert to RGB if necessary
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")

                # Convert to base64
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85)
                img_bytes = buffer.getvalue()
                img_base64 = base64.b64encode(img_bytes).decode("utf-8")

                return f"data:image/jpeg;base64,{img_base64}"
        except Exception as e:
            raise ValueError(f"Failed to process image: {str(e)}")

    @classmethod
    async def read_text_file(cls, file_path: str) -> str:
        """Read text file content"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Limit content size
                if len(content) > 50000:
                    content = content[:50000] + "\n... (truncated)"
                return content
        except UnicodeDecodeError:
            # Try with different encoding
            with open(file_path, "r", encoding="latin-1") as f:
                content = f.read()
                if len(content) > 50000:
                    content = content[:50000] + "\n... (truncated)"
                return content
        except Exception as e:
            raise ValueError(f"Failed to read file: {str(e)}")

    @classmethod
    async def format_attachment_for_llm(cls, attachment: Dict[str, Any]) -> Dict[str, Any]:
        """Format attachment for LLM consumption"""
        file_type = attachment["file_type"]
        file_path = attachment["path"]

        if file_type == "image":
            # For vision models
            image_data = await cls.process_image_for_vision(file_path)
            return {
                "type": "image_url",
                "image_url": {"url": image_data}
            }
        elif file_type == "text":
            # Read text content
            content = await cls.read_text_file(file_path)
            return {
                "type": "text",
                "text": f"File: {attachment['filename']}\n\n{content}"
            }
        else:
            # For other files, just provide metadata
            return {
                "type": "text",
                "text": f"Attached file: {attachment['filename']} ({attachment['mime_type']}, {attachment['size']} bytes)"
            }
