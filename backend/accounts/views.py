from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import IntegrityError

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
# Create your views here.

@api_view(['POST'])
def signin_user(request):
    email = request.data.get('email')
    password = request.data.get('password')
    
    # 1. Check if email exists in database
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"success": False, "error": "User with this email does not exist"}, status=404)

    # 2. Check if the password matches
    # Note: For production, you should use hashed passwords (check_password), 
    # but for now we are checking plain text based on your previous code.
    if user.check_password(password):
       # GET OR CREATE TOKEN
       token, _ = Token.objects.get_or_create(user=user)
       return Response({
            "token":token.key,
            "success": True, 
            "user": {
                "name": user.first_name,  
                "email": user.email
            }
        })
    else:
        return Response({"success": False, "error": "Invalid password"}, status=400)

@api_view(['POST'])
def signup_user(request):
    display_name = request.data.get('username')
    email = request.data.get('email')
    password = request.data.get('password')

    # Basic Validation
    if not display_name or not email or not password:
        return Response({"success":False, "error":"All fields are required"})
    # Check if email already exists
    if User.objects.filter(email=email).exists():
        return Response({"success":False, "error":"Email already registered try another email" }, status=400)
    

    try:
        # Create user 
        user = User.objects.create_user(username=email, email=email, password=password, first_name=display_name)

        # Create a token for each user 
        token = Token.objects.create(user=user)

        return Response({
            "success":True,
            "token":token.key,
            "user":{
                "username":user.username,
                "email":user.email
            }
        }, status=201)

    except IntegrityError:
        return Response({"success":False, "error":"Database error occured"}, status=500)
    except Exception as e:
        return Response({"success":False, "error":str(e)}, status=500)



@api_view(['POST'])
def forgot_password(request):
    email = request.data.get('email')

    if not email:
        return Response({"success": False, "error": "Email is required"}, status=400)

    # CHECK: If email exists in database
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # This is the specific error you wanted
        return Response({
            "success": False, 
            "error": "This email account does not exist"
        }, status=404)

    # If email exists, proceed with sending the link
    try:
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        # Ensure this matches your React App's running port (usually 3000 or 5173)
        reset_link = f"http://localhost:5173/reset-password/{uid}/{token}"

        send_mail(
            subject='Reset Your Password - Legal Advisor',
            message=f'Click the link below to reset your password:\n\n{reset_link}',
            from_email=settings.EMAIL_HOST_USER, 
            recipient_list=[email],
            fail_silently=False,
        )
        return Response({"success": True, "message": "Password reset link sent to email"})
        
    except Exception as e:
        return Response({"success": False, "error": f"Failed to send email: {str(e)}"}, status=500)



@api_view(['PATCH'])
def reset_password(request):
    # We expect these values from the React Frontend (ResetPassword.js)
    uidb64 = request.data.get('uidb64')
    token = request.data.get('token')
    password = request.data.get('password')
    confirm_password = request.data.get('confirm_password')

    # 1. Basic Validation
    if not uidb64 or not token or not password:
        return Response({"success": False, "error": "Missing required fields"}, status=400)

    if password != confirm_password:
        return Response({"success": False, "error": "Passwords do not match"}, status=400)

    # 2. Decode the User ID
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({"success": False, "error": "Invalid reset link"}, status=400)

    # 3. Check if the Token is valid and belongs to this user
    if not default_token_generator.check_token(user, token):
        return Response({"success": False, "error": "Invalid or expired token"}, status=400)

    # 4. Set the new password
    user.set_password(password)
    user.save()

    return Response({"success": True, "message": "Password has been reset successfully"})