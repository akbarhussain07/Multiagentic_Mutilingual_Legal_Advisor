from django.urls import path
from . import views

urlpatterns = [
    path('query/', views.query_rag, name='query_rag'),


    
    path('suggestions/', views.get_suggestions, name='get_suggestions'),
    path('health/', views.health_check, name='health_check'),
]