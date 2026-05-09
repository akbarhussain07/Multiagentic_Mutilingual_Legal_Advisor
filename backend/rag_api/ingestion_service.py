import fitz
import hashlib
import os
import threading
from django.core.cache import cache
from langchain_huggingface import HuggingFaceEmbeddings
from neo4j import GraphDatabase

# Configuration (Ensure these match your .env or settings)
NEO4J_URI = os.getenv("NEO4J_URL")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
hf_embeddings = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-large")

def process_pdf_worker(file_path, filename, law_type, task_id):
    """
    Worker function that runs in a background thread.
    Updates Django cache with progress percentages.
    """
    doc = None
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        
        # Initialize progress
        cache.set(f"task_{task_id}", {"status": "processing", "progress": 0}, 3600)

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

        for i, page in enumerate(doc):
            text = page.get_text().strip()
            if text:
                # 1. Generate Embedding
                embedding = hf_embeddings.embed_query(text[:1500])
                
                # 2. Prepare Data Row
                row = {
                    "chunk_id": hashlib.md5(f"{filename}{i}".encode()).hexdigest(),
                    "text": text[:1500],
                    "text_normalized": text[:1500].lower(),
                    "embedding": embedding,
                    "page": page.number + 1,
                    "title": filename,
                    "law_type": law_type
                }

                # 3. Store in Neo4j
                with driver.session() as session:
                    session.run(query, rows=[row])

            # 4. Update Progress in Cache
            progress = int(((i + 1) / total_pages) * 100)
            cache.set(f"task_{task_id}", {
                "status": "processing", 
                "progress": progress,
                "current": i + 1,
                "total": total_pages
            }, 3600)

        # Finalize
        cache.set(f"task_{task_id}", {"status": "completed", "progress": 100}, 3600)

    except Exception as e:
        print(f"Background Task Error: {str(e)}")
        cache.set(f"task_{task_id}", {"status": "failed", "error": str(e)}, 3600)
    
    finally:
        # Close the PyMuPDF 
        if doc:
            doc.close()

        # Clean up the temporary file after processing
        if os.path.exists(file_path):
            try:
              os.remove(file_path)
            except Exception as cleanup_error:
                print(f"Cleanup Error: {cleanup_error}")  

def start_ingestion_thread(file_path, filename, law_type, task_id):
    """Entry point to trigger the background thread."""
    thread = threading.Thread(
        target=process_pdf_worker, 
        args=(file_path, filename, law_type, task_id)
    )
    thread.start()