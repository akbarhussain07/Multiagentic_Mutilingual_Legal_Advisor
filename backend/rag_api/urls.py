from django.urls import path
from . import views

urlpatterns = [
    # Query
    path('query/', views.query_rag, name='query_rag'),

    # Chat history
    path('history/', views.get_user_sessions, name='user_sessions'),
    path('history/<str:session_id>/', views.get_session_messages, name='session_messages'),
    path('history/<str:session_id>/delete/', views.delete_session, name='delete_session'),

    # Health check for API and Qdrant
    path('health/', views.health_check, name='health_check'),

    # Route for document upload
    path('upload-doc/', views.UploadDocumentView.as_view(), name='upload_document'),
    path('upload-status/<str:task_id>/', views.get_upload_status, name='upload_status'),
    
    # Global App Rating
    path('rate-app/', views.rate_app, name='rate_app'),
]