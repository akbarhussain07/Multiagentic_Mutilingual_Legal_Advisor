import os
from PyPDF2 import PdfReader
from langchain_text_splitters import CharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_neo4j import Neo4jVector
from langchain_core.documents import Document
from dotenv import load_dotenv

def run_setup():
    # 1. Configuration & Environment
    load_dotenv()
    
    # Path to PDF - 
    # pdf_path = 'PEC2016.pdf'
    # pdf_path = 'PPC.pdf'
    pdf_path = 'the-anti-terrorism-act-1997.pdf' 
    
    url = os.getenv('NEO4J_URL')
    username = os.getenv('NEO4J_USERNAME')
    password = os.getenv('NEO4J_PASSWORD')
    
    if not all([url, username, password]):
        print("Error: Neo4j credentials missing in .env file.")
        return

    try:
        # 2. Read PDF 
        print(f"Reading PDF: {pdf_path}...")
        reader = PdfReader(pdf_path)
        raw_text = ""
        for page in reader.pages:
            content = page.extract_text()
            if content:
                raw_text += content

        # 3. Chunking 
        print("Splitting text into chunks...")
        text_splitter = Character_splitter = Character_text_splitter = CharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separator="\n"
        )
        texts = text_splitter.split_text(raw_text)
        docs = [Document(page_content=t) for t in texts]

        # 4. Embeddings 
        print("Initializing Embedding Model (all-mpnet-base-v2)...")
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2"
        )

        # 5. Load into Neo4j
        print("Creating Vector Index and uploading to Neo4j...")
        Neo4jVector.from_documents(
            docs,
            embeddings,
            url=url,
            username=username,
            password=password,
            index_name="vector",
            node_label="Document",
            text_node_property="text",
            embedding_node_property="embedding"
        )

        print("\nSuccess! Your vector database is created.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    run_setup()