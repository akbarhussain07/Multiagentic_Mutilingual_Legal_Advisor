from django.urls import path
from . import views

urlpatterns = [
    # Query
    path('query/', views.query_rag, name='query_rag'),

    # Chat history
    path('history/', views.get_user_sessions, name='user_sessions'),
    path('history/<str:session_id>/', views.get_session_messages, name='session_messages'),
    path('history/<str:session_id>/delete/', views.delete_session, name='delete_session'),

    #Helth to check is neo4j database connected or not
    path('health/', views.health_check, name='health_check'),

    # Global App Rating
    path('rate-app/', views.rate_app, name='rate_app'),
]