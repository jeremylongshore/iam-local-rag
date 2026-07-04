#!/usr/bin/env python3
"""
Performance Analysis Tool for Local Document Q&A RAG System
Analyzes performance bottlenecks, memory usage, and optimization opportunities
"""

import time
import tracemalloc
import psutil
import os
import json
import numpy as np
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import Dict, List, Any, Tuple
import tempfile
import shutil

# Import application components
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.llms import Ollama
from langchain_core.documents import Document

class RAGPerformanceAnalyzer:
    """Comprehensive performance analysis for the RAG pipeline"""

    def __init__(self, model="llama3"):
        self.model = model
        self.metrics = {
            "document_processing": {},
            "embedding_generation": {},
            "vector_operations": {},
            "llm_inference": {},
            "memory_usage": {},
            "concurrent_performance": {}
        }

    def measure_time_and_memory(self, func, *args, **kwargs) -> Tuple[Any, float, float]:
        """Measure execution time and memory usage of a function"""
        # Start memory tracking
        tracemalloc.start()
        start_memory = tracemalloc.get_traced_memory()[0]

        # Measure time
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()

        # End memory tracking
        end_memory = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()

        elapsed_time = end_time - start_time
        memory_used = (end_memory - start_memory) / 1024 / 1024  # Convert to MB

        return result, elapsed_time, memory_used

    def analyze_document_processing(self, doc_sizes: List[int] = [1, 10, 50, 100, 500]):
        """Analyze document processing performance with different sizes"""
        print("\n=== Document Processing Performance ===")

        for size_kb in doc_sizes:
            # Create sample document
            sample_text = "This is a sample document. " * (size_kb * 50)
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
            temp_file.write(sample_text)
            temp_file.close()

            try:
                # Test loading
                loader = TextLoader(temp_file.name)
                docs, load_time, load_memory = self.measure_time_and_memory(loader.load)

                # Test splitting with different chunk sizes
                chunk_sizes = [500, 1000, 2000]
                for chunk_size in chunk_sizes:
                    splitter = RecursiveCharacterTextSplitter(
                        chunk_size=chunk_size,
                        chunk_overlap=int(chunk_size * 0.2)
                    )
                    splits, split_time, split_memory = self.measure_time_and_memory(
                        splitter.split_documents, docs
                    )

                    key = f"{size_kb}KB_chunk{chunk_size}"
                    self.metrics["document_processing"][key] = {
                        "doc_size_kb": size_kb,
                        "chunk_size": chunk_size,
                        "num_chunks": len(splits),
                        "load_time_ms": load_time * 1000,
                        "split_time_ms": split_time * 1000,
                        "total_time_ms": (load_time + split_time) * 1000,
                        "memory_mb": load_memory + split_memory,
                        "chunks_per_second": len(splits) / split_time if split_time > 0 else 0
                    }

                    print(f"  {size_kb}KB doc, {chunk_size} chunks: "
                          f"{len(splits)} chunks in {(load_time + split_time)*1000:.2f}ms")

            finally:
                os.unlink(temp_file.name)

    def analyze_embedding_performance(self, text_samples: int = 100):
        """Analyze embedding generation performance"""
        print("\n=== Embedding Generation Performance ===")

        try:
            embeddings = OllamaEmbeddings(model=self.model)

            # Test different batch sizes
            batch_sizes = [1, 10, 25, 50, 100]
            sample_texts = [f"Sample text {i} for embedding analysis." * 10
                          for i in range(text_samples)]

            for batch_size in batch_sizes:
                if batch_size > len(sample_texts):
                    continue

                batch = sample_texts[:batch_size]

                # Measure embedding generation
                _, embed_time, embed_memory = self.measure_time_and_memory(
                    embeddings.embed_documents, batch
                )

                self.metrics["embedding_generation"][f"batch_{batch_size}"] = {
                    "batch_size": batch_size,
                    "time_ms": embed_time * 1000,
                    "memory_mb": embed_memory,
                    "texts_per_second": batch_size / embed_time if embed_time > 0 else 0,
                    "ms_per_text": (embed_time * 1000) / batch_size
                }

                print(f"  Batch {batch_size}: {embed_time*1000:.2f}ms "
                      f"({(embed_time*1000)/batch_size:.2f}ms per text)")

        except Exception as e:
            print(f"  Warning: Could not test embeddings (Ollama may not be running): {e}")

    def analyze_vector_operations(self, num_vectors: List[int] = [100, 1000, 5000, 10000]):
        """Analyze vector database performance"""
        print("\n=== Vector Database Operations ===")

        temp_db_path = tempfile.mkdtemp()

        try:
            embeddings = OllamaEmbeddings(model=self.model)

            for n_vectors in num_vectors:
                # Create sample documents
                docs = [Document(page_content=f"Document {i} content " * 20,
                               metadata={"id": i}) for i in range(n_vectors)]

                # Test indexing
                _, index_time, index_memory = self.measure_time_and_memory(
                    Chroma.from_documents,
                    documents=docs[:n_vectors],
                    embedding=embeddings,
                    persist_directory=f"{temp_db_path}/chroma_{n_vectors}"
                )

                # Load and test retrieval
                vectorstore = Chroma(
                    persist_directory=f"{temp_db_path}/chroma_{n_vectors}",
                    embedding_function=embeddings
                )

                # Test different k values for retrieval
                k_values = [1, 3, 5, 10]
                for k in k_values:
                    if k > n_vectors:
                        continue

                    query = "Sample query text for retrieval"
                    _, search_time, _ = self.measure_time_and_memory(
                        vectorstore.similarity_search,
                        query, k=k
                    )

                    key = f"{n_vectors}_vectors_k{k}"
                    self.metrics["vector_operations"][key] = {
                        "num_vectors": n_vectors,
                        "k": k,
                        "index_time_ms": index_time * 1000,
                        "search_time_ms": search_time * 1000,
                        "index_memory_mb": index_memory,
                        "vectors_per_second": n_vectors / index_time if index_time > 0 else 0
                    }

                    print(f"  {n_vectors} vectors, k={k}: "
                          f"Search {search_time*1000:.2f}ms")

        except Exception as e:
            print(f"  Warning: Vector operation analysis failed: {e}")
        finally:
            shutil.rmtree(temp_db_path, ignore_errors=True)

    def analyze_llm_performance(self, prompt_lengths: List[int] = [100, 500, 1000, 2000]):
        """Analyze LLM inference performance"""
        print("\n=== LLM Inference Performance ===")

        try:
            llm = Ollama(model=self.model)

            for prompt_length in prompt_lengths:
                # Create context of varying lengths
                context = "This is sample context. " * (prompt_length // 20)
                question = "What is the main topic of the context?"

                prompt = f"""
                Context: {context}
                Question: {question}
                Answer:
                """

                # Measure inference time
                _, inference_time, inference_memory = self.measure_time_and_memory(
                    llm.invoke, prompt
                )

                self.metrics["llm_inference"][f"prompt_{prompt_length}"] = {
                    "prompt_length": prompt_length,
                    "time_ms": inference_time * 1000,
                    "memory_mb": inference_memory,
                    "chars_per_second": prompt_length / inference_time if inference_time > 0 else 0
                }

                print(f"  Prompt {prompt_length} chars: {inference_time*1000:.2f}ms")

        except Exception as e:
            print(f"  Warning: LLM analysis failed (Ollama may not be running): {e}")

    def analyze_concurrent_performance(self, num_queries: int = 10):
        """Analyze concurrent request handling"""
        print("\n=== Concurrent Request Performance ===")

        queries = [f"Test query {i}" for i in range(num_queries)]

        # Sequential processing
        start = time.perf_counter()
        for query in queries:
            # Simulate query processing
            time.sleep(0.1)  # Simulate processing time
        sequential_time = time.perf_counter() - start

        # Thread-based concurrent processing
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda q: time.sleep(0.1), queries))
        threaded_time = time.perf_counter() - start

        self.metrics["concurrent_performance"] = {
            "num_queries": num_queries,
            "sequential_time_ms": sequential_time * 1000,
            "threaded_time_ms": threaded_time * 1000,
            "speedup_factor": sequential_time / threaded_time if threaded_time > 0 else 0,
            "queries_per_second_sequential": num_queries / sequential_time,
            "queries_per_second_threaded": num_queries / threaded_time
        }

        print(f"  Sequential: {sequential_time*1000:.2f}ms")
        print(f"  Threaded: {threaded_time*1000:.2f}ms")
        print(f"  Speedup: {sequential_time/threaded_time:.2f}x")

    def analyze_memory_usage(self):
        """Analyze current memory usage patterns"""
        print("\n=== Memory Usage Analysis ===")

        process = psutil.Process()
        memory_info = process.memory_info()

        self.metrics["memory_usage"] = {
            "rss_mb": memory_info.rss / 1024 / 1024,
            "vms_mb": memory_info.vms / 1024 / 1024,
            "available_system_mb": psutil.virtual_memory().available / 1024 / 1024,
            "percent_used": process.memory_percent()
        }

        print(f"  Process RSS: {memory_info.rss / 1024 / 1024:.2f} MB")
        print(f"  Process VMS: {memory_info.vms / 1024 / 1024:.2f} MB")
        print(f"  System Available: {psutil.virtual_memory().available / 1024 / 1024:.2f} MB")

    def generate_optimization_report(self) -> Dict[str, Any]:
        """Generate optimization recommendations based on analysis"""
        recommendations = []
        bottlenecks = []

        # Analyze document processing
        if self.metrics["document_processing"]:
            avg_chunks_per_sec = np.mean([
                m["chunks_per_second"]
                for m in self.metrics["document_processing"].values()
            ])
            if avg_chunks_per_sec < 100:
                bottlenecks.append({
                    "area": "Document Processing",
                    "severity": "Medium",
                    "impact": f"Only {avg_chunks_per_sec:.1f} chunks/sec",
                    "recommendation": "Consider parallel document processing"
                })

        # Analyze embedding performance
        if self.metrics["embedding_generation"]:
            batch_metrics = self.metrics["embedding_generation"]
            if "batch_100" in batch_metrics and "batch_1" in batch_metrics:
                speedup = (batch_metrics["batch_1"]["ms_per_text"] /
                          batch_metrics["batch_100"]["ms_per_text"])
                if speedup > 2:
                    recommendations.append({
                        "area": "Embedding Generation",
                        "priority": "High",
                        "improvement": f"{speedup:.1f}x speedup possible",
                        "action": "Increase embedding batch size to 50-100"
                    })

        # Analyze vector operations
        if self.metrics["vector_operations"]:
            large_db_metrics = [m for k, m in self.metrics["vector_operations"].items()
                               if m["num_vectors"] >= 5000]
            if large_db_metrics:
                avg_search_time = np.mean([m["search_time_ms"] for m in large_db_metrics])
                if avg_search_time > 100:
                    bottlenecks.append({
                        "area": "Vector Search",
                        "severity": "High",
                        "impact": f"{avg_search_time:.1f}ms average search time",
                        "recommendation": "Implement vector index optimization or caching"
                    })

        # Memory recommendations
        if self.metrics["memory_usage"]:
            if self.metrics["memory_usage"]["percent_used"] > 75:
                recommendations.append({
                    "area": "Memory Usage",
                    "priority": "Critical",
                    "improvement": "Reduce memory pressure",
                    "action": "Implement document streaming and batch processing"
                })

        return {
            "bottlenecks": bottlenecks,
            "recommendations": recommendations,
            "metrics_summary": self.metrics
        }

    def run_full_analysis(self):
        """Run complete performance analysis"""
        print("=" * 60)
        print("RAG PERFORMANCE ANALYSIS")
        print("=" * 60)

        # Run all analyses
        self.analyze_document_processing([1, 10, 50])
        self.analyze_embedding_performance(50)
        self.analyze_vector_operations([100, 1000])
        self.analyze_llm_performance([100, 500])
        self.analyze_concurrent_performance()
        self.analyze_memory_usage()

        # Generate report
        report = self.generate_optimization_report()

        print("\n" + "=" * 60)
        print("PERFORMANCE BOTTLENECKS")
        print("=" * 60)

        for bottleneck in report["bottlenecks"]:
            print(f"\n[{bottleneck['severity']}] {bottleneck['area']}")
            print(f"  Impact: {bottleneck['impact']}")
            print(f"  Fix: {bottleneck['recommendation']}")

        print("\n" + "=" * 60)
        print("OPTIMIZATION RECOMMENDATIONS")
        print("=" * 60)

        for rec in report["recommendations"]:
            print(f"\n[{rec['priority']}] {rec['area']}")
            print(f"  Improvement: {rec['improvement']}")
            print(f"  Action: {rec['action']}")

        # Save detailed report
        with open("performance_report.json", "w") as f:
            json.dump(report, f, indent=2)
        print("\n✅ Full report saved to performance_report.json")

        return report


if __name__ == "__main__":
    analyzer = RAGPerformanceAnalyzer()
    analyzer.run_full_analysis()