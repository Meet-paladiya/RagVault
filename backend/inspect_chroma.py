"""
ChromaDB Full Export & Inspection Script
Dump or view ALL content, vector text, and metadata stored in ChromaDB.

Usage:
  cd backend
  source .venv/bin/activate

  # Print all chunks to terminal:
  python inspect_chroma.py

  # Save everything to a JSON file:
  python inspect_chroma.py --export
"""
import sys
import json
import argparse
from app.utils.chroma_client import get_chroma_client

def get_all_chroma_data():
    client = get_chroma_client()
    collections = client.list_collections()
    
    all_data = {}

    print("=" * 70)
    print("           CHROMADB FULL KNOWLEDGE DUMP & INSPECTOR           ")
    print("=" * 70)
    print(f"Total Knowledge Space Collections: {len(collections)}\n")

    if not collections:
        print("No collections found in ChromaDB yet.")
        return all_data

    for idx, col in enumerate(collections, start=1):
        count = col.count()
        print(f"\n============================================================")
        print(f"[{idx}] COLLECTION: {col.name}  (Total Chunks: {count})")
        print(f"============================================================")

        if count == 0:
            print("  (Empty collection)")
            all_data[col.name] = []
            continue

        # Get ALL chunks in the collection (no limit parameter)
        data = col.get(include=["documents", "metadatas"])
        docs = data.get("documents", [])
        metas = data.get("metadatas", [])
        ids = data.get("ids", [])

        col_chunks = []
        for i, (chunk_id, doc, meta) in enumerate(zip(ids, docs, metas), start=1):
            source = meta.get("source", "Unknown") if meta else "Unknown"
            page = meta.get("page", 1) if meta else 1
            chunk_idx = meta.get("chunk_index", 0) if meta else 0
            doc_id = meta.get("document_id", "") if meta else ""

            chunk_info = {
                "chunk_number": i,
                "id": chunk_id,
                "source_file": source,
                "page": page,
                "chunk_index": chunk_idx,
                "document_id": doc_id,
                "text": doc
            }
            col_chunks.append(chunk_info)

            print(f"\n--- Chunk #{i} | File: {source} | Page: {page} | Index: {chunk_idx} ---")
            print(f"ID: {chunk_id}")
            print(f"Content:\n{doc}")

        all_data[col.name] = col_chunks

    return all_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect or dump all ChromaDB contents.")
    parser.add_argument("--export", "-e", action="store_true", help="Export all ChromaDB data to chroma_export.json")
    args = parser.parse_args()

    data = get_all_chroma_data()

    if args.export and data:
        out_file = "chroma_export.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n\n✅ Successfully exported ALL ChromaDB contents to '{out_file}'!")
