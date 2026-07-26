from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import ChatSession, ChatMessage, UserProfile
from .rag_service import RAGService
import logging
import os
import re
import uuid

from django.core.files.storage import default_storage
from django.core.cache import cache
from rest_framework.views import APIView
from dotenv import load_dotenv
from .ingestion_service import start_ingestion_thread 









logger = logging.getLogger(__name__)
load_dotenv()
_rag_service = None


def get_rag_service():
    """Initialize heavyweight models on first RAG request, not Django startup."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


def get_conversational_response(question, view_mode):
    """Answer small-talk without loading embeddings, Pinecone, or the LLM."""
    normalized = re.sub(r"[^a-z0-9\s']", " ", question.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    capability_phrases = (
        "what can you provide", "what can you do", "how can you help",
        "who are you", "what do you do",
    )
    is_greeting = bool(re.match(r"^(hi|hello|hey|assalam|salam)\b", normalized))
    name_match = re.search(r"\b(?:i am|i'm|my name is)\s+([a-z][a-z'-]*)", normalized)
    asks_capabilities = any(phrase in normalized for phrase in capability_phrases)
    legal_terms = (
        "property", "land", "house", "inherit", "heir", "hiba", "gift",
        "mutation", "registry", "registration", "tenant", "court", "case",
        "transfer", "sale", "ownership", "document", "limitation", "waqf",
    )
    contains_legal_question = any(term in normalized for term in legal_terms)

    if contains_legal_question or not (is_greeting or name_match or asks_capabilities):
        return None

    name = name_match.group(1).title() if name_match else ""
    greeting = f"Hello, {name}!" if name else "Hello!"
    mode_label = {
        "pakistani": "Pakistani property law",
        "islamic": "Islamic property law",
        "procedure": "property-case procedure",
    }[view_mode]
    answer = (
        f"## {greeting}\n\n"
        "I can help with source-based property-law information in three areas:\n\n"
        "- **Pakistani:** ownership, sale, transfer, registration, mutation, tenancy and succession.\n"
        "- **Islamic:** inheritance, hiba, wasiyyah, waqf and other Sharia property rules.\n"
        "- **Procedure:** courts, evidence, limitation periods, remedies and required documents.\n\n"
        f"Your current source is **{mode_label}**. Select another source from the dropdown beside the chat box whenever needed."
    )
    return {
        "answer": answer,
        "pakistanContent": answer if view_mode == "pakistani" else "",
        "islamicContent": answer if view_mode == "islamic" else "",
        "procedureContent": answer if view_mode == "procedure" else "",
        "sources": [],
        "selected_agents": [],
        "from_memory": False,
        "success": True,
    }


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
        
        suggestions = []
        
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
        if _rag_service is not None:
            connection_status = _rag_service.check_connection()
        else:
            configured = bool(os.getenv('PINECONE_API_KEY') and os.getenv('GROQ_API_KEY'))
            connection_status = {
                'connected': configured,
                'configured_agents': [],
                'initialization': 'deferred',
            }
        return Response(
            {
                'status': 'healthy',
                'service': 'Legal Advisor RAG API',
                'pinecone_connected': connection_status['connected'],
                **connection_status,
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
        view_mode = request.data.get('view_mode', 'pakistani')

        if view_mode not in {'pakistani', 'islamic', 'procedure'}:
            return Response(
                {'error': "view_mode must be 'pakistani', 'islamic', or 'procedure'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        recent_messages = ChatMessage.objects.filter(session=session).order_by('-created_at')[:4]
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
        result = get_conversational_response(question, view_mode)
        if result is None:
            result = get_rag_service().query(
                question,
                view_mode=view_mode,
                chat_history=chat_history,
            )
        if not result.get('success'):
            return Response(result, status=status.HTTP_502_BAD_GATEWAY)

        # Step E: Structure the AI Response for Storage
        response_data = {
            'session_id': str(session.session_id),
            'sources': result.get('sources', []),
            'pakistanContent': result.get('pakistanContent'),
            'islamicContent': result.get('islamicContent'),
            'procedureContent': result.get('procedureContent'),
            'practicalSteps': result.get('practicalSteps', []),
            'missingInformation': result.get('missingInformation', []),
            'disclaimer': result.get('disclaimer'),
            'selected_agents': result.get('selected_agents', []),
            'from_memory': result.get('from_memory', False),
            'viewMode': view_mode,
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
                    'procedureContent': m.content.get('procedureContent'),
                    'practicalSteps': m.content.get('practicalSteps', []),
                    'missingInformation': m.content.get('missingInformation', []),
                    'disclaimer': m.content.get('disclaimer'),
                    'viewMode': m.content.get('viewMode', 'pakistani'),
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
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file_obj = request.FILES.get('file')
        law_type = request.data.get('law_type', 'Pakistani')

        if not file_obj:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)
        if not file_obj.name.lower().endswith(('.md', '.markdown')):
            return Response(
                {"error": "Only Markdown files (.md) are supported by the ingestion pipeline."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
