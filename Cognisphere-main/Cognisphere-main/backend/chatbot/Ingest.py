"""Reads every PDF / TXT / MD file in ./data, splits it into chunks,
embeds them with the Gemini API and stores them in a local Chroma database.

Run again whenever you add new documents:  python ingest.py
"""
import hashlib
from pathlib import Path

import chromadb
from pypdf import PdfReader

from embeddings import embed_documents

DATA_DIR = Path("data")
DB_DIR = "chroma_db"
COLLECTION = "agri_gemini"
CHUNK_CHARS = 900
OVERLAP = 150


def read_file(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                yield f"p.{i}", text
    elif suffix in (".txt", ".md"):
        yield "", path.read_text(encoding="utf-8", errors="ignore")


def chunk(text: str):
    text = " ".join(text.split())
    start = 0
    while start < len(text):
        piece = text[start:start + CHUNK_CHARS]
        if len(piece.strip()) > 80:
            yield piece
        start += CHUNK_CHARS - OVERLAP


def main():
    DATA_DIR.mkdir(exist_ok=True)
    files = [p for p in DATA_DIR.rglob("*") if p.suffix.lower() in (".pdf", ".txt", ".md")]
    if not files:
        print("No documents found in ./data. Add ICAR / KVK / state agriculture PDFs first.")
        return

    client = chromadb.PersistentClient(path=DB_DIR)
    col = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    for path in files:
        ids, docs, metas = [], [], []
        for label, text in read_file(path):
            for piece in chunk(text):
                uid = hashlib.md5(f"{path}|{label}|{piece[:60]}".encode()).hexdigest()
                ids.append(uid)
                docs.append(piece)
                metas.append({"source": path.name, "page": label})
        if not docs:
            print(f"  skipped (no text found): {path.name}")
            continue
        print(f"  embedding {len(docs)} chunks from {path.name} ...")
        embeds = embed_documents(docs)
        col.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embeds)
        print(f"  indexed {path.name}")

    print(f"Done. Database now holds {col.count()} chunks.")


if __name__ == "__main__":
    main()
