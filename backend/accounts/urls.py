from django.urls import path
from .views import signin_user, signup_user, forgot_password, reset_password, google_oauth

urlpatterns =[
    path('login/', signin_user),
    path('signup/', signup_user),
    path('password-reset/', forgot_password, name='forgot_password'),
    path('password-reset-confirm/', reset_password, name='reset_password'),
    path('google-login/', google_oauth),

]