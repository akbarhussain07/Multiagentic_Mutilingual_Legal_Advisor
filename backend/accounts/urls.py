from django.urls import path
from .views import signin_user, signup_user, forgot_password, reset_password, update_user_profile, delete_user_profile

urlpatterns =[
    path('login/', signin_user),
    path('signup/', signup_user),
    path('password-reset/', forgot_password, name='forgot_password'),
    path('password-reset-confirm/', reset_password, name='reset_password'),
    path('<int:pk>/update/', update_user_profile, name='update_user_profile'),
    path('<int:pk>/delete/', delete_user_profile, name='update_user_profile'),
]