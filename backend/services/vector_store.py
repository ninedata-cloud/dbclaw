import logging
from typing import List, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class VectorStore:
    """Manage ChromaDB vector store for knowledge base."""

    def __init__(self, persist_dir: str, embedding_model: str):
        self.persist_dir = persist_dir
        self.embedding_model_name = embedding_model
        self._client = None
        self._embedding_function = None

    def _init_client(self):
        """Lazy initialization of ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
                from chromadb.utils import embedding_functions
            except ImportError:
                raise ImportError("chromadb is required. Install with: pip install chromadb")

            # Create persist directory if it doesn't exist
            Path(self.persist_dir).mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(path=self.persist_dir)

            # Initialize embedding function
            self._embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.embedding_model_name
            )

            logger.info(f"ChromaDB initialized at {self.persist_dir}")

    def create_collection(self, collection_name: str):
        """Create a new collection."""
        self._init_client()
        try:
            collection = self._client.create_collection(
                name=collection_name,
                embedding_function=self._embedding_function,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Created collection: {collection_name}")
            return collection
        except Exception as e:
            logger.error(f"Error creating collection {collection_name}: {e}")
            raise

    def get_collection(self, collection_name: str):
        """Get existing collection."""
        self._init_client()
        try:
            return self._client.get_collection(
                name=collection_name,
                embedding_function=self._embedding_function
            )
        except Exception as e:
            logger.error(f"Error getting collection {collection_name}: {e}")
            return None

    def delete_collection(self, collection_name: str):
        """Delete a collection."""
        self._init_client()
        try:
            self._client.delete_collection(name=collection_name)
            logger.info(f"Deleted collection: {collection_name}")
        except Exception as e:
            logger.error(f"Error deleting collection {collection_name}: {e}")
            raise

    def add_documents(self, collection_name: str, chunks: List[Dict], document_id: int):
        """Add document chunks to collection."""
        self._init_client()
        collection = self.get_collection(collection_name)
        if not collection:
            raise ValueError(f"Collection {collection_name} not found")

        if not chunks:
            return

        # Prepare data for ChromaDB
        ids = [f"doc_{document_id}_chunk_{i}" for i in range(len(chunks))]
        documents = [chunk["content"] for chunk in chunks]
        metadatas = []
        for chunk in chunks:
            metadata = chunk["metadata"].copy()
            metadata["document_id"] = document_id
            metadatas.append(metadata)

        try:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            logger.info(f"Added {len(chunks)} chunks to collection {collection_name}")
        except Exception as e:
            logger.error(f"Error adding documents to {collection_name}: {e}")
            raise

    def search(self, collection_name: str, query: str, top_k: int = 5) -> List[Dict]:
        """Search collection for similar documents."""
        self._init_client()
        collection = self.get_collection(collection_name)
        if not collection:
            return []

        try:
            results = collection.query(
                query_texts=[query],
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )

            # Format results
            search_results = []
            if results["ids"] and results["ids"][0]:
                for i in range(len(results["ids"][0])):
                    search_results.append({
                        "content": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i]
                    })

            return search_results
        except Exception as e:
            logger.error(f"Error searching collection {collection_name}: {e}")
            return []

    def delete_document(self, collection_name: str, document_id: int):
        """Delete all chunks for a document."""
        self._init_client()
        collection = self.get_collection(collection_name)
        if not collection:
            return

        try:
            # Get all chunk IDs for this document
            results = collection.get(
                where={"document_id": document_id},
                include=["metadatas"]
            )

            if results["ids"]:
                collection.delete(ids=results["ids"])
                logger.info(f"Deleted {len(results['ids'])} chunks for document {document_id}")
        except Exception as e:
            logger.error(f"Error deleting document {document_id} from {collection_name}: {e}")
            raise
