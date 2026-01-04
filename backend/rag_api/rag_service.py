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
                search_kwargs={"k": 4}  # Retrieve top 4 most similar documents
            )
            logger.info("Retriever initialized with k=4")
            
            # Initialize LLM with explicit parameters (not in model_kwargs)
            # hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
            # if not hf_token:
            #     raise ValueError("HuggingFace API token not found in environment variables")
            
            # logger.info("Initializing HuggingFace LLM...")
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
                   You are a precise and reliable legal assistant specializing in Pakistani constitutional law.

                   Your job is to answer the question **only using the information provided in the context below**.
                   - Do NOT use prior knowledge or external information.
                   - If the context is missing, incomplete, unrelated, or does not contain enough details to answer confidently, reply strictly with:
                   "I don't have enough information in the provided context to answer this question accurately."
                   - Do not attempt to infer, assume, or guess anything not explicitly supported by the context.
                     - Provide clear, concise answers with specific references to articles or clauses when applicable.

                    Context:{context}

                    Question:{question}

                   Answer:""",
                input_variables=['context', 'question']
            )
            
            self._initialized = True
            logger.info("RAG Service initialized successfully!")
            
        except Exception as e:
            logger.error(f"Error initializing RAG Service: {str(e)}")
            raise
    
    def query(self, question: str) -> dict:
        """
        Query the RAG system with a question
        
        The process:
        1. Convert question to embedding
        2. Search Neo4j for similar document embeddings
        3. Retrieve top-k most similar documents
        4. Use retrieved context to generate answer with LLM
        
        Args:
            question: The user's question
            
        Returns:
            dict with 'answer', 'sources', and 'success' keys
        """
        try:
            logger.info(f"Processing query: {question}")
            
            # Step 1 & 2: Retrieve relevant documents using embeddings
            # This automatically converts question to embedding and searches
            retrieval_docs = self.retriever.invoke(question)
            logger.info(f"Retrieved {len(retrieval_docs)} relevant documents")
            
            # Step 3: Combine retrieved documents into context
            context_text = "\n\n".join(doc.page_content for doc in retrieval_docs)
            
            # Step 4: Generate prompt with context
            final_prompt = self.prompt.invoke({
                "context": context_text,
                "question": question
            })
            
            # Step 5: Get response from LLM
            logger.info("Generating response from LLM...")
            response = self.model.invoke(final_prompt)
            
            # Extract sources for transparency
            sources = [
                {
                    "content": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                    "metadata": doc.metadata,
                    "page": doc.metadata.get('page', 'N/A')
                }
                for doc in retrieval_docs
            ]
            
            logger.info("Query processed successfully")
            return {
                "answer": response.content,
                "sources": sources,
                "success": True,
                "num_sources": len(sources)
            }
            
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return {
                "answer": f"An error occurred while processing your question: {str(e)}",
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