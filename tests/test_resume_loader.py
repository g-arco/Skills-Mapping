import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python_pipeline.parser import read_resume_text


class ReadResumeTextTests(unittest.TestCase):
    def test_reads_plain_text_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "resume.txt"
            path.write_text("Summary\nPython and SQL", encoding="utf-8")

            self.assertEqual(read_resume_text(path), "Summary\nPython and SQL")

    def test_reads_pdf_resume_using_pdfminer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "resume.pdf"
            path.write_bytes(b"%PDF-1.4\n%test")

            with patch("pdfminer.high_level.extract_text", return_value="Extracted text from PDF"):
                self.assertEqual(read_resume_text(path), "Extracted text from PDF")


if __name__ == "__main__":
    unittest.main()
