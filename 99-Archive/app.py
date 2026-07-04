import streamlit as st
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.prompts import ChatPromptTemplate, PromptTemplate
from langchain_community.llms import Ollama
from langchain.chains import RetrievalQA
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
import os

# --- Configuration ---
# Make sure this matches the model you downloaded via `ollama run <model_name>`
OLLAMA_MODEL = "llama3" # e.g., "llama3", "mistral", "llama2-uncensored"
DOCUMENTS_DIR = "documents"
CHROMA_DB_PATH = "./chroma_db" # Local directory to store vector DB

# --- Streamlit UI Setup ---
st.set_page_config(
    page_title="NEXUS AI • Document Intelligence",
    page_icon="🧠",
    layout="centered"
)
st.title("🧠 NEXUS • Autonomous Document Intelligence")
st.markdown("*Self-contained RAG agent for private document analysis • Zero cloud dependencies*")

# --- Document Loading and Processing ---
@st.cache_resource # Cache this function to avoid re-running on every interaction
def setup_rag_pipeline():
    try:
        # Check if ChromaDB already exists to avoid reprocessing
        if os.path.exists(CHROMA_DB_PATH) and os.listdir(CHROMA_DB_PATH):
            st.info("🧠 NEXUS: Loading knowledge base from persistent storage...")
            embeddings = OllamaEmbeddings(model=OLLAMA_MODEL)
            vectorstore = Chroma(persist_directory=CHROMA_DB_PATH, embedding_function=embeddings)
            retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
            llm = Ollama(model=OLLAMA_MODEL)
        else:
            # 1. Load documents
            st.info(f"🧠 NEXUS: Ingesting documents from {DOCUMENTS_DIR}/...")
            documents = []
            for filename in os.listdir(DOCUMENTS_DIR):
                file_path = os.path.join(DOCUMENTS_DIR, filename)
                if filename.endswith(".pdf"):
                    loader = PyPDFLoader(file_path)
                    documents.extend(loader.load())
                elif filename.endswith((".txt", ".md")):
                    loader = TextLoader(file_path)
                    documents.extend(loader.load())
                # Add more loaders for other file types as needed (e.g., CSVLoader, DOCXLoader)
            
            if not documents:
                st.warning(f"⚠️ No documents detected in knowledge base '{DOCUMENTS_DIR}'!")
                st.info("Add PDF, TXT, or MD files for NEXUS to analyze.")
                return None, None

            # 2. Split documents into chunks
            st.info("🔄 NEXUS: Segmenting documents into semantic chunks...")
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            splits = text_splitter.split_documents(documents)

            # 3. Create embeddings and store in ChromaDB
            st.info(f"🧠 NEXUS: Generating embeddings and indexing to vector store...")
            embeddings = OllamaEmbeddings(model=OLLAMA_MODEL)
            vectorstore = Chroma.from_documents(documents=splits, embedding=embeddings, persist_directory=CHROMA_DB_PATH)
            
            # 4. Initialize the Retriever
            retriever = vectorstore.as_retriever(search_kwargs={"k": 3}) # Retrieve top 3 relevant chunks

            # 5. Initialize the Local LLM
            llm = Ollama(model=OLLAMA_MODEL)

        # 6. Define the RAG Prompt Template
        template = """
        You are NEXUS, an autonomous document intelligence agent.
        Analyze the retrieved context to provide accurate, insightful answers.
        If information is insufficient, acknowledge limitations transparently.
        Provide concise yet comprehensive responses.
        
        Context: {context}
        
        Question: {question}
        
        Answer:
        """
        prompt = ChatPromptTemplate.from_template(template)

        # 7. Build the RAG Chain
        rag_chain = (
            {"context": retriever, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        
        st.success("✅ NEXUS initialized! Knowledge base ready for queries.")
        return rag_chain, vectorstore # Return vectorstore to manage persistence
    
    except Exception as e:
        if "ConnectionError" in str(type(e)) or "connection" in str(e).lower():
            st.error(f"❌ NEXUS: Cannot connect to local LLM server (Ollama).")
            st.info(f"To activate NEXUS:\n1. Start Ollama: `ollama serve`\n2. Initialize model: `ollama run {OLLAMA_MODEL}`")
        else:
            st.error(f"❌ NEXUS initialization failed: {str(e)}")
        return None, None

# --- Main Application Flow ---
rag_chain, vectorstore_instance = setup_rag_pipeline()

if rag_chain:
    # Initialize NEXUS conversation memory
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Render conversation history with NEXUS
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Process user queries through NEXUS pipeline
    if prompt := st.chat_input("Query NEXUS knowledge base:"):
        # Input validation
        if not prompt.strip():
            st.warning("Please enter a valid question.")
        else:
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant", avatar="🧠"):
                with st.spinner("NEXUS analyzing knowledge base..."):
                    try:
                        response = rag_chain.invoke(prompt)
                        st.markdown(response)
                        # Add assistant response to chat history
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    except Exception as e:
                        error_msg = f"❌ NEXUS query processing failed: {str(e)}"
                        st.error(error_msg)
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})

    # NEXUS Control Panel
    with st.sidebar:
        st.markdown("### 🧠 NEXUS Control Panel")
        if st.button("🔄 Reset Knowledge Base", help="Clear conversation and re-index all documents"):
            st.session_state.messages = []
            # Delete ChromaDB to force re-indexing
            if os.path.exists(CHROMA_DB_PATH):
                import shutil
                shutil.rmtree(CHROMA_DB_PATH)
            st.cache_resource.clear()  # Clear NEXUS cache
            st.rerun()  # Reinitialize NEXUS pipeline
else:
    st.error("🧠 NEXUS requires documents to analyze. Add files to 'documents/' folder and restart.")