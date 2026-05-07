import os
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Any
import fitz  # PyMuPDF
from neo4j import GraphDatabase
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

# Configuration
NEO4J_URI = os.getenv("NEO4J_URL")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
VECTOR_INDEX_NAME = "vector"
FULLTEXT_INDEX_NAME = "ftChunk"

# Initialize Driver and Embeddings
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
hf_embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

def create_indexes():
    """Wipes old indexes and creates fresh ones for your new DB."""
    with driver.session() as session:
        session.run(f"DROP INDEX {VECTOR_INDEX_NAME} IF EXISTS")
        session.run(f"DROP INDEX {FULLTEXT_INDEX_NAME} IF EXISTS")
        
        # Vector Index for E5-Large (1024 dimensions)
        session.run(f"""
            CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS
            FOR (c:Chunk) ON (c.embedding)
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: 1024,
                `vector.similarity_function`: 'cosine'
            }}}}
        """)
        # Fulltext Index for names and law types
        session.run(f"""
            CREATE FULLTEXT INDEX {FULLTEXT_INDEX_NAME} IF NOT EXISTS
            FOR (c:Chunk) ON EACH [c.text_normalized, c.title, c.law_type]
        """)
    print("✅ Indexes initialized.")

def detect_lang(text):
    arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
    return "ar" if arabic_chars > 20 else "en"

def store_in_neo4j(chunks, filename, law_type, batch_size=20):
    """Stores chunks in small batches to avoid connection timeouts."""
    query = """
    UNWIND $rows AS row
    MERGE (c:Chunk {chunk_id: row.chunk_id})
    SET c.text = row.text,
        c.text_normalized = row.text_normalized,
        c.embedding = row.embedding,
        c.page = row.page,
        c.title = row.title,
        c.law_type = row.law_type
    """
    
    # Process the chunks in small groups (batches)
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        rows = []
        
        for idx, c in enumerate(batch):
            # i + idx ensures unique IDs across batches
            global_idx = i + idx
            rows.append({
                "chunk_id": hashlib.md5(f"{filename}{global_idx}".encode()).hexdigest(),
                "text": c['text'],
                "text_normalized": c['text'].lower(),
                "embedding": hf_embeddings.embed_query(c['text']),
                "page": c['page'],
                "title": filename,
                "law_type": law_type
            })
        
        # Send this batch to Neo4j
        try:
            with driver.session() as session:
                session.run(query, rows=rows)
            print(f"   ∟ Progress: {i + len(batch)}/{len(chunks)} chunks uploaded...")
        except Exception as e:
            print(f"   ❌ Batch failed: {e}")

def process_folder(folder_name, law_type):
    # This finds the 'data' folder relative to this script
    base_path = Path(__file__).parent.parent / "data" / folder_name
    
    if not base_path.exists():
        print(f"⚠️ Folder not found: {base_path}")
        return

    for pdf in base_path.glob("*.pdf"):
        print(f"📖 Processing {pdf.name} as {law_type} Law...")
        doc = fitz.open(str(pdf))
        chunks = []
        for page in doc:
            text = page.get_text().strip()
            if text:
                chunks.append({"text": text[:1500], "page": page.number + 1})
        
        store_in_neo4j(chunks, pdf.name, law_type)
        print(f"✅ Uploaded {pdf.name}")

if __name__ == "__main__":
    create_indexes()
    # Run for both types
    process_folder("pakistani", "Pakistani")
    process_folder("islamic", "Islamic")
    print("\n🚀 Database is ready!")