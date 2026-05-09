from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import ChatSession, ChatMessage, UserProfile
from rest_framework import status
from .rag_service import RAGService
import logging
import uuid

from django.core.files.storage import default_storage
from django.core.cache import cache
from rest_framework.views import APIView
from .ingestion_service import start_ingestion_thread 









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
@permission_classes([IsAuthenticated])
def query_rag(request):
    try:
        user = request.user
        question = request.data.get('question', '')
        session_id = request.data.get('session_id')
        view_mode = request.data.get('view_mode', 'both')

        if not question:
            return Response({'error': 'Question is required'}, status=400)

        # Step A: Get or Create Session
        if session_id and session_id != 'new':
            session = get_object_or_404(ChatSession, session_id=session_id, user=user)
        else:
            title = question[:25] + "..." if len(question) > 25 else question
            session = ChatSession.objects.create(user=user, title=title)

        # --- NEW: Step B: Fetch Chat History for Memory ---
        # We fetch the last 4 messages to keep the context without overwhelming the LLM
        recent_messages = ChatMessage.objects.filter(session=session).order_by('-created_at')[1:5]
        chat_history = []
        
        # We reverse them to get them in chronological order
        for msg in reversed(recent_messages):
            role = "User" if msg.role == 'user' else "Assistant"
            # Since content is a JSONField, we need to handle both strings and dictionaries
            if isinstance(msg.content, dict):
                content = msg.content.get('answer') or msg.content.get('pakistanContent') or ""
            else:
                content = msg.content
            chat_history.append(f"{role}: {content}")

        # Step C: Save current User Message to DB
        ChatMessage.objects.create(
            session=session,
            role='user',
            content=question
        )
  
        # Step D: Get AI Response (Now passing chat_history)
        result = rag_service.query(question, view_mode=view_mode, chat_history=chat_history)

        # Step E: Structure the AI Response for Storage
        response_data = {
            'session_id': str(session.session_id),
            'sources': result.get('sources', []),
            'pakistanContent': result.get('pakistanContent'),
            'islamicContent': result.get('islamicContent'),
            'answer': result.get('answer') 
        }

        # Step F: Save Structured JSON to History
        ChatMessage.objects.create(
            session=session, 
            role='assistant', 
            content=response_data 
        )

        return Response(response_data)
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
    """Fetch all messages for a specific session ID and unpack JSON content"""
    try:
        session = get_object_or_404(ChatSession, session_id=session_id, user=request.user)
        messages = ChatMessage.objects.filter(session=session).order_by('created_at')
        
        data = []
        for m in messages:
            if m.role == 'user':
                data.append({
                    'type': 'user',
                    'content': m.content, # Just the stored string
                    'timestamp': m.created_at.strftime("%H:%M")
                })
            else:
                # Unpack the assistant's JSON dictionary into the response
                data.append({
                    'type': 'bot',
                    'pakistanContent': m.content.get('pakistanContent'),
                    'islamicContent': m.content.get('islamicContent'),
                    'answer': m.content.get('answer'),
                    'sources': m.content.get('sources', []),
                    'timestamp': m.created_at.strftime("%H:%M")
                })
        
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
    


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rate_app(request):
    """Save a global 1-5 star rating for the logged-in user"""
    try:
        user = request.user
        rating_value = request.data.get('rating')

        if rating_value is not None and 1 <= int(rating_value) <= 5:
            # get_or_create ensures the user has a profile to save the rating to
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.rating = int(rating_value)
            profile.save()
            return Response({'message': 'Global rating saved'}, status=200)
            
        return Response({'error': 'Invalid rating value'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=500)
    


class UploadDocumentView(APIView):
    """
    Saves the file and starts the background indexing process.
    Returns a task_id immediately.
    """
    def post(self, request):
        file_obj = request.FILES.get('file')
        law_type = request.data.get('law_type', 'Pakistani')

        if not file_obj:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Generate a unique task ID
        task_id = str(uuid.uuid4())
        
        # 2. Save the file temporarily to the 'media/tmp' folder
        # This is necessary because the background thread needs a physical file path
        path = default_storage.save(f"tmp/{task_id}_{file_obj.name}", file_obj)
        full_path = default_storage.path(path)

        # 3. Initialize the progress in cache (Set to 0%)
        cache.set(f"task_{task_id}", {
            "status": "starting", 
            "progress": 0, 
            "fileName": file_obj.name
        }, 3600)

        # 4. Start the background thread (from ingestion_service.py)
        # This does NOT block the request
        start_ingestion_thread(full_path, file_obj.name, law_type, task_id)

        # 5. Return the task_id to React immediately
        return Response({
            "task_id": task_id, 
            "message": "Upload successful. Indexing started in background."
        }, status=status.HTTP_202_ACCEPTED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_upload_status(request, task_id):
    """
    Endpoint for the frontend to poll for progress updates.
    """
    status_data = cache.get(f"task_{task_id}")
    if not status_data:
        return Response({"error": "Task not found or expired"}, status=404)
    
    return Response(status_data)