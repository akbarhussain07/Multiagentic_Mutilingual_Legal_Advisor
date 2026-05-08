
import os
import re
import logging
from typing import List, Dict, Any
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langchain_neo4j import Neo4jVector
from dotenv import load_dotenv

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
            # self.embeddings = HuggingFaceEmbeddings(
            #     model_name="sentence-transformers/all-mpnet-base-v2"
            # )

            # Multilingual Embedding Model 
            self.embeddings = HuggingFaceEmbeddings(
                model_name="intfloat/multilingual-e5-large",
                model_kwargs={'device': 'cpu'},  # No 'normalize_embeddings' here
                encode_kwargs={'normalize_embeddings': True},  # Correct parameter name and placement
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
                node_label="Chunk",
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
            self.condense_prompt = PromptTemplate(
                template="""Given the following conversation and a follow-up question, rephrase the follow-up question to be a standalone question.
    
                Chat History:
                {chat_history}
    
                Follow-up Question: {question}
    
                Standalone Question:""",
                input_variables=['chat_history', 'question']
            )

            self.prompt = PromptTemplate(
            template="""
                You are an expert Legal Assistant specializing in Pakistani Law and Islamic Sharia Law.

                ### CONTEXT
                {context}
 
                ### USER QUESTION
                {question}

                ### STRICT INSTRUCTIONS
                1. **Greetings:** If the user says "Hi", "Hello", or similar greetings, ONLY reply with: "Hello! I am your Legal Advisor. How can I assist you with Pakistani or Islamic law today?" Do not provide legal analysis or references for simple greetings.
    
                2. **Off-Topic Filtering:** If the user asks about celebrities, general knowledge, or anything NOT related to Pakistani or Islamic law, reply ONLY with: "I searched in my documents but I couldn't found. I am a specialized legal assistant. I can only provide information regarding Pakistani Law and Islamic Law. Please ask a legal question."
    
                3. **Missing Information:** If the provided context does not contain the answer, say: "I'm sorry, I could not find a specific answer to this in my current legal database." Do not try to make up an answer.
    
                4. **References:** Only show citations or references if you are actually providing a legal answer.

                Answer:""",
                input_variables=['context', 'question']
                )
          
            
            self._initialized = True
            logger.info("Multilingual RAG Service Ready!")
            
        except Exception as e:
            logger.error(f"Error initializing RAG Service: {str(e)}")
            raise
    
   
    def query(self, question: str, view_mode: str = "both", chat_history: list =[]) -> dict:
        try:
            # 1. ADD GREETING CHECK HERE
            greetings = ["hi", "hello", "hey", "salam", "aalaikum", "assalam"]
        # Check if the question is just a greeting (usually 1-2 words)
            if any(greet in question.lower() for greet in greetings) and len(question.split()) < 3:
               greeting_text = "Hello! I am your Legal Advisor. How can I assist you with Pakistani Law or Islamic Law today?"
               return {
                "answer": greeting_text,
                "pakistanContent": greeting_text if view_mode != "islamic" else None,
                "islamicContent": greeting_text if view_mode != "pakistan" else None,
                "sources": [], # Return empty sources for greetings
                "success": True
                }
            
            if chat_history:
               history_str = "\n".join(chat_history)
               condense_input = self.condense_prompt.format(chat_history=history_str, question=question)
               standalone_question = self.model.invoke(condense_input).content
               logger.info(f"Rewritten Question: {standalone_question}")
            else:
               standalone_question = question


            # logic for "Both" mode
            if view_mode == "both":
                # 1. Retrieve Pakistani Context
                pak_docs = self.vector_store.similarity_search(standalone_question, k=3, filter={"law_type": "Pakistani"})
                # 2. Retrieve Islamic Context
                isl_docs = self.vector_store.similarity_search(standalone_question, k=3, filter={"law_type": "Islamic"})

                # 3. Generate answers for both
                pak_answer = self._generate_specialized_answer(question, pak_docs, "Pakistani Law", chat_history)
                isl_answer = self._generate_specialized_answer(question, isl_docs, "Islamic Law", chat_history)

                return {
                    "pakistanContent": pak_answer,
                    "islamicContent": isl_answer,
                    "sources": self._format_sources(pak_docs + isl_docs),
                    "success": True
                }
            
            # Logic for single view (pakistan or islamic)
            else:
                law_label = "Pakistani Law" if view_mode == "pakistan" else "Islamic Law"
                search_filter = {"law_type": "Pakistani"} if view_mode == "pakistan" else {"law_type": "Islamic"}
            
                docs = self.vector_store.similarity_search(question, k=5, filter=search_filter)
            
                # Use specialized answer to ensure domain-specific instructions are followed
                answer = self._generate_specialized_answer(question, docs, law_label, chat_history)

                return {
                       "answer": answer,
                       "pakistanContent": answer if view_mode == "pakistan" else "Information hidden: Pakistani view not selected.",
                       "islamicContent": answer if view_mode == "islamic" else "Information hidden: Islamic view not selected.",
                       "sources": self._format_sources(docs),
                       "success": True
                }
                
        except Exception as e:
            logger.error(f"Query Error: {str(e)}")
            return {"answer": f"System Error: {str(e)}", "success": False}

    # Helper to keep the code clean
    def _format_sources(self, docs):
        return [{
            "content": d.page_content[:200] + "...",
            "title": d.metadata.get('title', 'Unknown'),
            "law_type": d.metadata.get('law_type', 'General'),
            "page": d.metadata.get('page', 'N/A')
        } for d in docs]

    def _generate_specialized_answer(self, question, docs, law_type_label, chat_history = []):
        # Ensure chat_history is a list
        if chat_history is None:
            chat_history = []
        # If no documents were found for this specific law type, do not generate an answer
        if not docs:
           return "I'm sorry, I could not find a specific answer to this in the {} database.".format(law_type_label)
    
        context = "\n\n".join([d.page_content for d in docs])
        history_str = "\n".join(chat_history) if chat_history else "No previous conversation."

        # Create a highly specific prompt for the individual panel
        panel_prompt = f"""
            You are a legal expert specializing ONLY in {law_type_label}.

            ### RECENT CONVERSATION:
            {history_str}

            ### CONTEXT FROM {law_type_label} DATABASE:
            {context}
    
            ### QUESTION:
             {question}
    
             ### STRICT INSTRUCTIONS:
             1. Answer ONLY using the provided {law_type_label} context.
             2. Do NOT mention other legal systems.
             3. If the answer is not in the context, say: "No specific information found in the {law_type_label} database."
             4. CITE specific sections or verses found in the context.
             5. Using the conversation history and the new context, provide a detailed response.

             Answer:"""
    
        return self.model.invoke(panel_prompt).content


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




