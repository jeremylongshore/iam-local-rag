"""
Optimized version of the RAG application with performance improvements
Implements caching, parallel processing, and async operations
"""

import streamlit as st
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.prompts import ChatPromptTemplate
from langchain_community.llms import Ollama
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
import os
import time
import hashlib
import pickle
import json
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import List, Dict, Any, Tuple
import multiprocessing
from functools import lru_cache
import psutil
import shutil

# --- Configuration ---
OLLAMA_MODEL = "llama3"
DOCUMENTS_DIR = "documents"
CHROMA_DB_PATH = "./chroma_db_optimized"
CACHE_DIR = "./rag_cache"
INDEX_METADATA_PATH = "./index_metadata.json"

# Performance tuning parameters
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
EMBEDDING_BATCH_SIZE = 50
MAX_WORKERS = multiprocessing.cpu_count()
CACHE_TTL = 3600  # 1 hour
MAX_CACHE_SIZE = 100

# --- Performance Monitoring ---
class PerformanceMonitor:
    """Track and report performance metrics"""

    def __init__(self):
        self.metrics = {
            "document_processing": [],
            "query_latency": [],
            "cache_hits": 0,
            "cache_misses": 0
        }

    def record_metric(self, metric_type: str, value: float):
        self.metrics[metric_type].append({
            "timestamp": time.time(),
            "value": value
        })

    def get_cache_hit_rate(self) -> float:
        total = self.metrics["cache_hits"] + self.metrics["cache_misses"]
        if total == 0:
            return 0
        return self.metrics["cache_hits"] / total

# Initialize performance monitor
perf_monitor = PerformanceMonitor()

# --- Caching Layer ---
class MultiLayerCache:
    """Multi-layer caching system for embeddings, search results, and responses"""

    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

        # In-memory caches with LRU
        self.embedding_cache = {}
        self.search_cache = {}
        self.response_cache = {}

    def _get_cache_key(self, content: str) -> str:
        """Generate cache key from content"""
        return hashlib.md5(content.encode()).hexdigest()

    def get_embedding(self, text: str) -> List[float]:
        """Get cached embedding or None"""
        key = self._get_cache_key(text)
        if key in self.embedding_cache:
            perf_monitor.metrics["cache_hits"] += 1
            return self.embedding_cache[key]

        # Check disk cache
        cache_file = os.path.join(self.cache_dir, f"emb_{key}.pkl")
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                embedding = pickle.load(f)
                self.embedding_cache[key] = embedding
                perf_monitor.metrics["cache_hits"] += 1
                return embedding

        perf_monitor.metrics["cache_misses"] += 1
        return None

    def set_embedding(self, text: str, embedding: List[float]):
        """Cache embedding in memory and disk"""
        key = self._get_cache_key(text)
        self.embedding_cache[key] = embedding

        # Persist to disk
        cache_file = os.path.join(self.cache_dir, f"emb_{key}.pkl")
        with open(cache_file, 'wb') as f:
            pickle.dump(embedding, f)

        # LRU eviction
        if len(self.embedding_cache) > MAX_CACHE_SIZE:
            oldest = next(iter(self.embedding_cache))
            del self.embedding_cache[oldest]

    @lru_cache(maxsize=MAX_CACHE_SIZE)
    def get_search_results(self, query: str, k: int) -> List[Any]:
        """Get cached search results"""
        key = f"{query}_{k}"
        if key in self.search_cache:
            perf_monitor.metrics["cache_hits"] += 1
            return self.search_cache[key]
        perf_monitor.metrics["cache_misses"] += 1
        return None

    def set_search_results(self, query: str, k: int, results: List[Any]):
        """Cache search results"""
        key = f"{query}_{k}"
        self.search_cache[key] = results

# Initialize cache
cache = MultiLayerCache()

# --- Optimized Document Processing ---
class OptimizedDocumentProcessor:
    """Parallel document processing with incremental indexing"""

    def __init__(self):
        self.index_metadata = self.load_index_metadata()

    def load_index_metadata(self) -> Dict[str, Any]:
        """Load metadata about indexed files"""
        if os.path.exists(INDEX_METADATA_PATH):
            with open(INDEX_METADATA_PATH, 'r') as f:
                return json.load(f)
        return {}

    def save_index_metadata(self):
        """Save metadata about indexed files"""
        with open(INDEX_METADATA_PATH, 'w') as f:
            json.dump(self.index_metadata, f)

    def needs_indexing(self, file_path: str) -> bool:
        """Check if file needs to be indexed"""
        if file_path not in self.index_metadata:
            return True

        file_mtime = os.path.getmtime(file_path)
        indexed_mtime = self.index_metadata[file_path].get("mtime", 0)

        return file_mtime > indexed_mtime

    def load_document(self, file_path: str):
        """Load a single document"""
        if file_path.endswith(".pdf"):
            loader = PyPDFLoader(file_path)
        elif file_path.endswith((".txt", ".md")):
            loader = TextLoader(file_path)
        else:
            return []
        return loader.load()

    def process_documents_parallel(self, file_paths: List[str]) -> List[Any]:
        """Process documents in parallel"""
        start_time = time.perf_counter()

        # Filter files that need indexing
        files_to_process = [f for f in file_paths if self.needs_indexing(f)]

        if not files_to_process:
            st.info("All documents are up to date!")
            return []

        st.info(f"Processing {len(files_to_process)} new/modified documents...")

        # Parallel document loading
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = executor.map(self.load_document, files_to_process)
            all_documents = []
            for docs in futures:
                all_documents.extend(docs)

        # Parallel text splitting
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            split_futures = executor.map(
                lambda doc: text_splitter.split_documents([doc]),
                all_documents
            )
            all_splits = []
            for splits in split_futures:
                all_splits.extend(splits)

        # Update metadata
        for file_path in files_to_process:
            self.index_metadata[file_path] = {
                "mtime": os.path.getmtime(file_path),
                "indexed_at": time.time()
            }
        self.save_index_metadata()

        processing_time = time.perf_counter() - start_time
        perf_monitor.record_metric("document_processing", processing_time)

        st.success(f"Processed {len(files_to_process)} documents in {processing_time:.2f}s")

        return all_splits

# --- Optimized Embeddings ---
class OptimizedEmbeddings:
    """Batch embedding generation with caching"""

    def __init__(self, model: str = OLLAMA_MODEL):
        self.embeddings = OllamaEmbeddings(model=model)

    def embed_documents_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings in optimized batches"""
        embeddings = []

        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[i:i + EMBEDDING_BATCH_SIZE]

            # Check cache first
            batch_embeddings = []
            texts_to_embed = []

            for text in batch:
                cached_embedding = cache.get_embedding(text)
                if cached_embedding:
                    batch_embeddings.append(cached_embedding)
                else:
                    texts_to_embed.append(text)

            # Generate embeddings for uncached texts
            if texts_to_embed:
                new_embeddings = self.embeddings.embed_documents(texts_to_embed)

                # Cache the new embeddings
                for text, embedding in zip(texts_to_embed, new_embeddings):
                    cache.set_embedding(text, embedding)
                    batch_embeddings.append(embedding)

            embeddings.extend(batch_embeddings)

        return embeddings

# --- Optimized Vector Store ---
class OptimizedVectorStore:
    """Vector store with optimized search and caching"""

    def __init__(self, persist_directory: str = CHROMA_DB_PATH):
        self.persist_directory = persist_directory

        # Configure for better performance
        self.collection_metadata = {
            "hnsw:space": "cosine",
            "hnsw:construction_ef": 200,
            "hnsw:search_ef": 100
        }

    def create_or_load(self, documents=None, embeddings=None):
        """Create new or load existing vector store"""
        if os.path.exists(self.persist_directory) and os.listdir(self.persist_directory):
            return Chroma(
                persist_directory=self.persist_directory,
                embedding_function=embeddings
            )
        elif documents:
            return Chroma.from_documents(
                documents=documents,
                embedding=embeddings,
                persist_directory=self.persist_directory
            )
        return None

    def similarity_search_cached(self, vectorstore, query: str, k: int = 3):
        """Cached similarity search"""
        # Check cache first
        cached_results = cache.get_search_results(query, k)
        if cached_results:
            return cached_results

        # Perform search
        results = vectorstore.similarity_search(query, k=k)

        # Cache results
        cache.set_search_results(query, k, results)

        return results

# --- Streamlit UI Setup ---
st.set_page_config(page_title="Optimized RAG Chatbot", layout="centered")
st.title("🚀 Optimized Document Q&A Chatbot")
st.markdown("High-performance RAG with caching, parallel processing, and optimizations")

# Performance metrics sidebar
with st.sidebar:
    st.header("Performance Metrics")
    col1, col2 = st.columns(2)

    with col1:
        cache_hit_rate = perf_monitor.get_cache_hit_rate()
        st.metric("Cache Hit Rate", f"{cache_hit_rate:.1%}")

    with col2:
        memory_usage = psutil.Process().memory_info().rss / 1024 / 1024
        st.metric("Memory (MB)", f"{memory_usage:.1f}")

    if perf_monitor.metrics["query_latency"]:
        avg_latency = sum(m["value"] for m in perf_monitor.metrics["query_latency"]) / len(perf_monitor.metrics["query_latency"])
        st.metric("Avg Query Latency", f"{avg_latency:.2f}s")

    # Clear cache button
    if st.button("Clear All Caches"):
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
        if os.path.exists(CHROMA_DB_PATH):
            shutil.rmtree(CHROMA_DB_PATH)
        if os.path.exists(INDEX_METADATA_PATH):
            os.remove(INDEX_METADATA_PATH)
        st.cache_resource.clear()
        st.rerun()

# --- Optimized RAG Pipeline ---
@st.cache_resource
def setup_optimized_rag_pipeline():
    try:
        # Initialize components
        doc_processor = OptimizedDocumentProcessor()
        opt_embeddings = OptimizedEmbeddings()
        opt_vectorstore = OptimizedVectorStore()

        # Get documents to process
        file_paths = []
        for filename in os.listdir(DOCUMENTS_DIR):
            file_path = os.path.join(DOCUMENTS_DIR, filename)
            if filename.endswith((".pdf", ".txt", ".md")):
                file_paths.append(file_path)

        if not file_paths:
            st.warning(f"No documents found in '{DOCUMENTS_DIR}'")
            return None, None

        # Process documents (only new/modified)
        splits = doc_processor.process_documents_parallel(file_paths)

        # Create or load vector store
        embeddings = OllamaEmbeddings(model=OLLAMA_MODEL)

        if splits:
            # Generate embeddings with batching and caching
            st.info("Generating embeddings...")
            texts = [split.page_content for split in splits]
            embedded_vectors = opt_embeddings.embed_documents_batch(texts)

            # Update vector store
            vectorstore = opt_vectorstore.create_or_load(
                documents=splits,
                embeddings=embeddings
            )
        else:
            # Load existing vector store
            vectorstore = opt_vectorstore.create_or_load(embeddings=embeddings)

        if not vectorstore:
            st.error("Failed to initialize vector store")
            return None, None

        # Create optimized retriever
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

        # Initialize LLM
        llm = Ollama(model=OLLAMA_MODEL)

        # RAG prompt template
        template = """
        You are an AI assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question.
        If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.

        Context: {context}

        Question: {question}

        Answer:
        """
        prompt = ChatPromptTemplate.from_template(template)

        # Build RAG chain
        rag_chain = (
            {"context": retriever, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )

        st.success("Optimized RAG pipeline ready!")
        return rag_chain, opt_vectorstore

    except Exception as e:
        st.error(f"Error setting up RAG pipeline: {str(e)}")
        return None, None

# --- Main Application ---
rag_chain, vectorstore_helper = setup_optimized_rag_pipeline()

if rag_chain:
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Accept user input
    if prompt := st.chat_input("Ask a question about your documents:"):
        if not prompt.strip():
            st.warning("Please enter a valid question.")
        else:
            # Add user message
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Generate response with performance tracking
            with st.chat_message("assistant"):
                with st.spinner("Processing..."):
                    try:
                        start_time = time.perf_counter()

                        # Check response cache first
                        response_key = hashlib.md5(prompt.encode()).hexdigest()
                        if response_key in cache.response_cache:
                            response = cache.response_cache[response_key]
                            st.caption("📌 Cached response")
                        else:
                            response = rag_chain.invoke(prompt)
                            cache.response_cache[response_key] = response

                        query_time = time.perf_counter() - start_time
                        perf_monitor.record_metric("query_latency", query_time)

                        st.markdown(response)
                        st.caption(f"⚡ Response time: {query_time:.2f}s")

                        st.session_state.messages.append({"role": "assistant", "content": response})

                    except Exception as e:
                        error_msg = f"Error: {str(e)}"
                        st.error(error_msg)
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})

else:
    st.error("Please add documents to the 'documents/' folder and restart.")