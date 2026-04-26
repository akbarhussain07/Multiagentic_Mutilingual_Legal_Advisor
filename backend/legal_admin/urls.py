from django.urls import path
from .views import get_users, user_detail, update_user, delete_user


urlpatterns =[
    path('users/', get_users, name='get_users'),
    path('users/<int:pk>/', user_detail, name='user_detail'),
    path('users/<int:pk>/update/', update_user, name='update_user'),
    path('users/<int:pk>/delete/', delete_user, name='delete_user'),
]