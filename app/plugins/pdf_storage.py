"""
RecoverFlow - Receivables and Collections
"""
import os
import shutil
import uuid
import logging
from pathlib import Path
from typing import Optional
from app.config import settings

class PDFStorage:
    """Store PDF files locally under generated names."""

    def __init__(self):
        self.storage_path = Path(settings.PDF_STORAGE_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def store_pdf(self, source_path: str) -> Optional[str]:
        """
        Copy a PDF into local storage under a UUID filename.
        """
        src = Path(source_path)
        if not src.exists():
            logging.warning(f"File {source_path} does not exist.")
            return None
        
        file_id = str(uuid.uuid4())
        ext = src.suffix
        new_filename = f"{file_id}{ext}"
        dest_path = self.storage_path / new_filename
        
        try:
            shutil.copy2(src, dest_path)
            return str(dest_path)
        except Exception as e:
            logging.error(f"Failed to store PDF: {e}")
            return None
