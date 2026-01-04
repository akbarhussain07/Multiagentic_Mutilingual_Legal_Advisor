from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .rag_service import RAGService
import logging

logger = logging.getLogger(__name__)

# Initialize RAG service (singleton)
rag_service = RAGService()

@api_view(['POST'])
def query_rag(request):
    """
    Query the RAG system with a legal question
    
    Request body:
    {
        "question": "Your legal question here"
    }
    
    Response:
    {
        "answer": "The answer from RAG",
        "sources": [...],
        "success": true
    }
    """
    try:
        question = request.data.get('question', '')
        
        if not question:
            return Response(
                {'error': 'Question is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Query RAG system
        result = rag_service.query(question)
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in query_rag: {str(e)}")
        return Response(
            {'error': 'Internal server error', 'details': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

















@api_view(['POST'])
def get_suggestions(request):
    """
    Get similar questions/topics based on input
    
    Request body:
    {
        "question": "Your partial question",
        "k": 4  
    }
    
    Response:
    {
        "suggestions": [...]
    }
    """
    try:
        question = request.data.get('question', '')
        k = request.data.get('k', 4)
        
        if not question:
            return Response(
                {'error': 'Question is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        suggestions = rag_service.get_similar_questions(question, k)
        
        return Response(
            {'suggestions': suggestions},
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Error in get_suggestions: {str(e)}")
        return Response(
            {'error': 'Internal server error', 'details': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def health_check(request):
    """
    Health check endpoint - checks API and Neo4j connection
    """
    try:
        connection_status = rag_service.check_connection()
        return Response(
            {
                'status': 'healthy',
                'service': 'Legal Advisor RAG API',
                'neo4j_connected': connection_status['connected'],
                'documents_loaded': connection_status['documents_loaded'],
                'message': connection_status['message']
            },
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {
                'status': 'unhealthy',
                'service': 'Legal Advisor RAG API',
                'error': str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )