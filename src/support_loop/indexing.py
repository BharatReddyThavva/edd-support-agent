"""Chunk the handbook and store it in Qdrant."""

from __future__ import annotations

from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient

from .config import Settings, get_settings, require_env


def handbook_documents(text: str, settings: Settings) -> list[Document]:
    sections: list[tuple[str, list[str]]] = []
    current = "overview"
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((current, buffer))
            current = line.removeprefix("## ").strip().lower().replace(" ", "-")
            buffer = [line]
        else:
            buffer.append(line)
    sections.append((current, buffer))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    documents: list[Document] = []
    for section, lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue
        for chunk in splitter.split_text(body):
            documents.append(
                Document(
                    page_content=chunk,
                    metadata={"source": settings.handbook_path.name, "section": section},
                )
            )
    return documents


def index_handbook(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    require_env(settings, "qdrant_url")
    text = settings.handbook_path.read_text()
    documents = handbook_documents(text, settings)
    embeddings = FastEmbedEmbeddings(model_name=settings.embedding_model)
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )
    if client.collection_exists(settings.collection_name):
        client.delete_collection(settings.collection_name)
    QdrantVectorStore.from_documents(
        documents,
        embeddings,
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        collection_name=settings.collection_name,
    )
    return len(documents)


def vector_store(settings: Settings) -> QdrantVectorStore:
    require_env(settings, "qdrant_url")
    embeddings = FastEmbedEmbeddings(model_name=settings.embedding_model)
    return QdrantVectorStore.from_existing_collection(
        embedding=embeddings,
        collection_name=settings.collection_name,
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )
