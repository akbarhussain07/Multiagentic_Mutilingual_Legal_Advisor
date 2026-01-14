from langchain_huggingface import HuggingFaceEmbeddings, ChatHuggingFace, HuggingFaceEndpoint
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langchain_neo4j import Neo4jVector
import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

class RAGService:
    """
    Singleton RAG service that connects to Neo4j vector store
    and provides query functionality using HuggingFace models
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RAGService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        logger.info("Initializing RAG Service...")
        
        # Load environment variables
        load_dotenv()
        
        try:
            # Initialize embeddings 
            logger.info("Loading embeddings model...")
            self.embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-mpnet-base-v2"
            )
            # To this (384 model):
            # self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
            
            # Neo4j connection details
            self.url = os.getenv("NEO4J_URL")
            self.username = os.getenv("NEO4J_USERNAME")
            self.password = os.getenv("NEO4J_PASSWORD")
            self.database = os.getenv("NEO4J_DATABASE", "neo4j")
            
            if not all([self.url, self.username, self.password]):
                raise ValueError("Neo4j credentials not found in environment variables")
            
            # Connect to existing Neo4j vector store
            logger.info("Connecting to Neo4j vector store...")
            self.vector_store = Neo4jVector(
                embedding=self.embeddings,
                url=self.url,
                username=self.username,
                password=self.password,
                database=self.database,
                index_name="vector",
                node_label="Document",
                text_node_property="text",
                embedding_node_property="embedding"
            )
            
            # Initialize retriever
            self.retriever = self.vector_store.as_retriever(
                search_type="similarity",
                search_kwargs={"k": 5}  # Retrieve top 5 most similar documents
            )
            logger.info("Retriever initialized with k=5")
            
            # Initialize LLM with explicit parameters (not in model_kwargs)
            # hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
            # if not hf_token:
            #     raise ValueError("HuggingFace API token not found in environment variables")
            
            # logger.info("Initialiing HuggingFace LLM...")
            # llm = HuggingFaceEndpoint(
            #     repo_id="HuggingFaceH4/zephyr-7b-beta",
            #     task="text-generation",
            #     huggingfacehub_api_token=hf_token,
            #     max_new_tokens=512,  # Explicit parameter
            #     temperature=0.7,      # Explicit parameter
            # )
            
            # self.model = ChatHuggingFace(llm=llm)


            groq_api = os.getenv("GROQ_API_KEY")
            if not groq_api:
                # The exception below will prevent self.model from being created
                raise ValueError("GROQ API token not found in environment variables")
            
            logger.info("Initializing GROQ LLM...")

            # ChatGroq instance 
            self.model = ChatGroq(
                model="llama-3.1-8b-instant",
                temperature=0.3
            )
            # Initialize prompt template
            self.prompt = PromptTemplate(
               template="""
                          You are a precise and reliable legal assistant specializing in Pakistani and Islamic laws.

                          Follow these rules strictly in order:

                          1. **Greetings:** If the user input is a simple greeting (e.g., "Hi", "Hello", "Salam", "Hey"), ignore the context and reply politely: "Hello! How can I assist you with Pakistani or Islamic law today?"

                          2. **Language Restriction:** If the user's question is NOT in English, ignore the context and reply strictly:   "Please enter your query in English."
                 
                          3. **Legal Questions:** For all other inquiries, answer the question **only using the information provided in the context below**.
                             - Do NOT use prior knowledge or external information.
                             - If the context is missing, incomplete, unrelated, or does not contain enough details to answer confidently, reply strictly with: "I don't have enough information in the provided context to answer this question accurately."
                             - Provide clear, concise answers with specific references to articles or clauses when applicable.

                    Context: {context}

                    Question: {question}

                    Answer:""",
               input_variables=['context', 'question']
            )

          
            
            self._initialized = True
            logger.info("RAG Service initialized successfully!")
            
        except Exception as e:
            logger.error(f"Error initializing RAG Service: {str(e)}")
            raise
    
   
    def query(self, question: str) -> dict:
        try:
            logger.info(f"Processing query: {question}")
            
            # Step 1: Retrieve MANY documents (Top 25)
            # We fetch more because the top 10 might be just Table of Contents
            all_docs = self.retriever.invoke(question)
            
            # --- NEW FILTERING LOGIC STARTS HERE ---
            useful_docs = []
            for doc in all_docs:
                content = doc.page_content
                
                # Filter 1: Skip if it explicitly says "CONTENTS" (Case insensitive)
                if "CONTENTS" in content.upper():
                    continue

                # Filter 2: Skip if it looks like a list of sections (e.g., "301. ... 302. ...")
                # We count how many times a pattern like "123. " appears. 
                # If it appears more than 3 times, it's likely an index page.
                import re
                section_matches = len(re.findall(r'\d+\.\s', content))
                if section_matches > 3:
                    continue

                # If it passed the checks, keep it
                useful_docs.append(doc)

            # Step 3: Take the top 5 BEST docs from the filtered list
            # If we filtered everything out (rare), fall back to the original top 3.
            final_docs = useful_docs[:5] if useful_docs else all_docs[:3]
            
            logger.info(f"Retrieved {len(all_docs)} docs, filtered down to {len(final_docs)} useful docs")
            # ---------------------------------------

            # Step 4: Combine context
            context_text = "\n\n".join(doc.page_content for doc in final_docs)
            
            # Step 5: Generate prompt
            final_prompt = self.prompt.invoke({
                "context": context_text,
                "question": question
            })
            
            # Step 6: Get response from LLM
            logger.info("Generating response from LLM...")
            response = self.model.invoke(final_prompt)
            
            # Extract sources (Only from the docs we actually used)
            sources = [
                {
                    "content": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                    "metadata": doc.metadata,
                    "page": doc.metadata.get('page', 'N/A')
                }
                for doc in final_docs
            ]
            
            return {
                "answer": response.content,
                "sources": sources,
                "success": True,
                "num_sources": len(sources)
            }
            
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return {
                "answer": f"An error occurred: {str(e)}",
                "sources": [],
                "success": False,
                "error": str(e)
            }
    
    def get_similar_questions(self, question: str, k: int = 3) -> list:
        """
        Get similar document chunks based on semantic similarity
        Useful for suggestions or exploring related content
        
        Args:
            question: The user's question
            k: Number of similar documents to retrieve
            
        Returns:
            List of similar document contents
        """
        try:
            docs = self.vector_store.similarity_search(question, k=k)
            return [
                doc.page_content[:150] + "..." if len(doc.page_content) > 150 else doc.page_content
                for doc in docs
            ]
        except Exception as e:
            logger.error(f"Error getting similar questions: {str(e)}")
            return []
    
    def check_connection(self) -> dict:
        """
        Check if Neo4j connection is working and documents are loaded
        
        Returns:
            dict with connection status and document count
        """
        try:
            # Try to perform a simple search
            test_docs = self.vector_store.similarity_search("test", k=1)
            return {
                "connected": True,
                "documents_loaded": len(test_docs) > 0,
                "message": "Connection successful"
            }
        except Exception as e:
            logger.error(f"Connection check failed: {str(e)}")
            return {
                "connected": False,
                "documents_loaded": False,
                "message": str(e)
            }