#!/usr/bin/env python3
"""Ingest documents into the vector knowledge base."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.ingestion import ingest_directory, ingest_file


def main():
    parser = argparse.ArgumentParser(description="Ingest documents into the knowledge base")
    parser.add_argument("path", help="File or directory to ingest")
    args = parser.parse_args()

    path = Path(args.path)
    if path.is_dir():
        count = ingest_directory(path)
    elif path.is_file():
        count = ingest_file(path)
    else:
        print(f"Error: {path} not found")
        sys.exit(1)

    print(f"Successfully ingested {count} chunks from {path}")


if __name__ == "__main__":
    main()
