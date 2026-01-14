from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import ChatSession, ChatMessage
from rest_framework import status
from .rag_service import RAGService
import logging

# from rest_framework.response import Response
# from rest_framework import status
# from .rag_service import RAGService
# import logging

# logger = logging.getLogger(__name__)

# # Initialize RAG service (singleton)
# rag_service = RAGService()

# @api_view(['POST'])
# def query_rag(request):
#     """
#     Query the RAG system with a legal question
    
#     Request body:
#     {
#         "question": "Your legal question here"
#     }
    
#     Response:
#     {
#         "answer": "The answer from RAG",
#         "sources": [...],
#         "success": true
#     }
#     """
#     try:
#         question = request.data.get('question', '')
        
#         if not question:
#             return Response(
#                 {'error': 'Question is required'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
        
#         # Query RAG system
#         result = rag_service.query(question)
        
#         return Response(result, status=status.HTTP_200_OK)
        
#     except Exception as e:
#         logger.error(f"Error in query_rag: {str(e)}")
#         return Response(
#             {'error': 'Internal server error', 'details': str(e)},
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         )














logger = logging.getLogger(__name__)
rag_service = RAGService()


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






#  Query RAG (Modified to Save History) 
@api_view(['POST'])
@permission_classes([IsAuthenticated]) # Ensures only logged-in users can save chats
def query_rag(request):
    try:
        user = request.user
        question = request.data.get('question', '')
        session_id = request.data.get('session_id') # Frontend will send this if continuing a chat

        if not question:
            return Response({'error': 'Question is required'}, status=400)

        # Step A: Get or Create Session
        if session_id:
            # Continue existing session
            session = get_object_or_404(ChatSession, session_id=session_id, user=user)
        else:
            # Start new session (Title = first 50 chars of question)
            title = question[:50] + "..." if len(question) > 50 else question
            session = ChatSession.objects.create(user=user, title=title)

        # Step B: Save User Message to DB
        ChatMessage.objects.create(
            session=session,
            role='user',
            content=question
        )
           

        # Step C: Get AI Response
        result = rag_service.query(question)
        answer = result.get('answer', 'No answer found.')
        sources = result.get('sources', [])
        # print(sources)
        # Step D: Save AI Message to DB
        ChatMessage.objects.create(
            session=session,
            role='assistant',
            content=answer
        )

        # Step E: Return Response with Session ID (Critical for frontend tracking)
        return Response({
            'session_id': session.session_id,
            'title': session.title,
            'answer': answer,
            'sources': sources
        })

    except Exception as e:
        logger.error(f"Error in query_rag: {str(e)}")
        return Response({'error': str(e)}, status=500)

# Get User's Chat History (For Sidebar) 
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_sessions(request):
    """Fetch all chat sessions for the logged-in user"""
    try:
        sessions = ChatSession.objects.filter(user=request.user).order_by('-updated_at')
        data = [
            {
                'id': str(s.session_id),
                'name': s.title, # Using 'name' to match your React 'chats' state
                'updated_at': s.updated_at
            } for s in sessions
        ]
        return Response(data)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

# Get Messages for a Specific Session (For Loading Chat) 
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_session_messages(request, session_id):
    """Fetch all messages for a specific session ID"""
    try:
        session = get_object_or_404(ChatSession, session_id=session_id, user=request.user)
        messages = ChatMessage.objects.filter(session=session).order_by('created_at')
        
        data = [
            {
                'type': 'user' if m.role == 'user' else 'bot', # Map to your React 'type'
                'content': m.content,
                'timestamp': m.created_at.strftime("%H:%M") # Format time
            } for m in messages
        ]
        return Response(data)
    except Exception as e:
        return Response({'error': str(e)}, status=500)
    




@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_session(request, session_id):
    """Delete a specific chat session"""
    try:
        # Get the session only if it belongs to the current user
        session = get_object_or_404(ChatSession, session_id=session_id, user=request.user)
        session.delete()
        return Response({'message': 'Session deleted successfully'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=500)