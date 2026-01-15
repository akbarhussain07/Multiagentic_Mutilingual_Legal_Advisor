from django.urls import path
from .views import signin_user, signup_user, forgot_password, reset_password

urlpatterns =[
    path('login/', signin_user),
    path('signup/', signup_user),
   # ✅ FIXED: This string must be 'password-reset/' to match React
    path('password-reset/', forgot_password, name='forgot_password'),
    
    # This is for the second step (setting the new password)
    path('password-reset-confirm/', reset_password, name='reset_password'),

]