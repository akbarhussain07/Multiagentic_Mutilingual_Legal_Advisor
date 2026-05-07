import json
import os
from neo4j import GraphDatabase
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv

# 1. LOAD THE .ENV FILE
load_dotenv()

# --- Configuration ---
NEO4J_URI = os.getenv("NEO4J_URL")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
JSON_FILE_PATH = "PEC.json"  # Ensure path is correct

# Name of the index your App is looking for (based on your error message)
VECTOR_INDEX_NAME = "vector" 

def load_data_into_graph(tx, part_data):
    """
    Parses the JSON data and creates nodes and relationships in Neo4j.
    """
    part_name = part_data.get("part_name", "Unknown Part")
    part_page = part_data.get("part_page_number")
    
    print(f"   Processing Part: {part_name}")
    
    tx.run("""
        MERGE (p:Part {name: $name})
        SET p.page = $page
    """, {"name": part_name, "page": part_page})

    chapters = part_data.get("chapters", {})
    for ch_key, chapter in chapters.items():
        ch_title = chapter.get("chapter_title", "Untitled")
        ch_page = chapter.get("chapter_page_number")

        tx.run("""
            MERGE (c:Chapter {name: $name})
            SET c.title = $title, c.page = $page
            WITH c
            MATCH (p:Part {name: $part})
            MERGE (p)-[:HAS_CHAPTER]->(c)
        """, {"name": ch_key, "title": ch_title, "page": ch_page, "part": part_name})

        for art in chapter.get("articles", []):
            art_title = art.get("title", "Untitled Article")
            art_page = art.get("page")

            tx.run("""
                MERGE (a:Article {title: $title})
                SET a.page = $page
                WITH a
                MATCH (c:Chapter {name: $chapter})
                MERGE (c)-[:HAS_ARTICLE]->(a)
            """, {"title": art_title, "page": art_page, "chapter": ch_key})

            content = art.get("content", {})
            for cl in content.get("clauses", []):
                cl_num = cl.get("clause_number")
                cl_text = cl.get("clause_text", "")

                tx.run("""
                    MERGE (cl:Clause {number: $num, article_title: $article})
                    SET cl.text = $text
                    WITH cl
                    MATCH (a:Article {title: $article})
                    MERGE (a)-[:HAS_CLAUSE]->(cl)
                """, {"num": cl_num, "text": cl_text, "article": art_title})

                for sub in cl.get("sub_clauses", []):
                    sub_num = sub.get("sub_clause_number")
                    sub_text = sub.get("sub_clause_text", "")
                    
                    if not sub_text.strip():
                        continue

                    tx.run("""
                        MERGE (s:SubClause {number: $num, clause_number: $clause, article_title: $article})
                        SET s.text = $text
                        WITH s
                        MATCH (cl:Clause {number: $clause, article_title: $article})
                        MERGE (cl)-[:HAS_SUBCLAUSE]->(s)
                    """, {"num": sub_num, "text": sub_text, "clause": cl_num, "article": art_title})

def create_vector_indices(driver):
    """
    Creates the vector index in Neo4j so the app can query it.
    """
    print(f"  Creating Vector Index named '{VECTOR_INDEX_NAME}'...")
    
    # We create the index specifically on 'Clause' nodes because they contain the main legal text.
    # The dimensions (768) match the 'sentence-transformers/all-mpnet-base-v2' model.
    query_index = f"""
    CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS
    FOR (n:Clause)
    ON (n.embedding)
    OPTIONS {{indexConfig: {{
      `vector.dimensions`: 768,
      `vector.similarity_function`: 'cosine'
    }}}}
    """
    
    try:
        with driver.session() as session:
            session.run(query_index)
        print(f" Vector Index '{VECTOR_INDEX_NAME}' created successfully on :Clause nodes.")
    except Exception as e:
        print(f"  Warning: Could not create index (it might already exist or have a conflict). \nError: {e}")

def main():
    if not NEO4J_URI:
        print(" Error: NEO4J_URL not found. Please check your .env file.")
        return

    print(" Connecting to Neo4j...")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        driver.verify_connectivity()
        print(" Connected.")
    except Exception as e:
        print(f" Connection Failed: {e}")
        return

    # 1. Load JSON Data
    print(f" Loading data from {JSON_FILE_PATH}...")
    try:
        with open(JSON_FILE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f" Error: File {JSON_FILE_PATH} not found.")
        return

    # 2. Create Graph Structure
    print(" Constructing Graph Structure...")
    with driver.session() as session:
        if isinstance(data, list):
            for part in data:
                session.execute_write(load_data_into_graph, part)
        else:
            session.execute_write(load_data_into_graph, data)
    print(" Graph structure created.")

    # 3. Generate Embeddings
    print(" Generating Embeddings (this may take a moment)...")
    embedder = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")
    
    # We focus on generating embeddings for Clauses as they are the primary search target
    # If you need SubClauses searched too, add "SubClause" to this list.
    node_types = ["Clause", "SubClause", "Article"] 

    with driver.session() as session:
        for label in node_types:
            print(f"    Processing {label} nodes...")
            
            records = session.run(f"MATCH (n:{label}) RETURN elementId(n) AS id, n.text AS text, n.title AS title")
            
            for row in records:
                text_content = row["text"] or row["title"]
                node_id = row["id"]

                if not text_content: continue
                
                vector = embedder.embed_query(text_content)
                
                session.run(
                    "MATCH (n) WHERE elementId(n) = $id SET n.embedding = $vec", 
                    {"id": node_id, "vec": vector}
                )

    # 4. Create Index (CRITICAL STEP)
    create_vector_indices(driver)

    print(" Success! Data loaded, embeddings generated, and INDEX created.")
    driver.close()

if __name__ == "__main__":
    main()