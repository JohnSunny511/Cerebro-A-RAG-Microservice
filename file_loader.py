import os
from pypdf import PdfReader

def read_txt(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def read_pdf(path):
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

def load_file(path):
    ext = os.path.splitext(path)[1].lower()

    if ext == ".txt" or ext == ".md":
        return read_txt(path)

    elif ext == ".pdf":
        return read_pdf(path)

    else:
        raise Exception("Unsupported file type")