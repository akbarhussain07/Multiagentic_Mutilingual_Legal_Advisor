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
from django.shortcuts import get_object_or_404
from rest_framework import status
from rag_api.models import UserProfile
from dotenv import load_dotenv
import os
# Create your views here.

load_dotenv()

@api_view(['POST'])
def signin_user(request):
    email = request.data.get('email')
    password = request.data.get('password')
    
    # Check if email exists in database
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"success": False, "error": "User with this email does not exist"}, status=404)

    #  Check if the password matches
    if user.check_password(password):
       # GET OR CREATE TOKEN
       token, _ = Token.objects.get_or_create(user=user)
      
       profile, _ = UserProfile.objects.get_or_create(user=user)
       
       return Response({
            "token":token.key,
            "success": True, 
            "user": {
                "id":user.id,
                "name": user.first_name,  
                "email": user.email,
                "is_superuser":user.is_superuser,
                "rating":profile.rating
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
        
        # this matches React App's running port (usually 5173)
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
    # We expect these values from the React Frontend (ResetPassword.jxs)
    uidb64 = request.data.get('uidb64')
    token = request.data.get('token')
    password = request.data.get('password')
    confirm_password = request.data.get('confirm_password')

    #  Basic Validation
    if not uidb64 or not token or not password:
        return Response({"success": False, "error": "Missing required fields"}, status=400)

    if password != confirm_password:
        return Response({"success": False, "error": "Passwords do not match"}, status=400)

    # Decoding the User ID
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({"success": False, "error": "Invalid reset link"}, status=400)

    # Check if the Token is valid and belongs to this user
    if not default_token_generator.check_token(user, token):
        return Response({"success": False, "error": "Invalid or expired token"}, status=400)

    #  Set the new password
    user.set_password(password)
    user.save()

    return Response({"success": True, "message": "Password has been reset successfully"})


@api_view(['PUT'])
def update_user_profile(request, pk):
    user = get_object_or_404(User, pk=pk)
    data = request.data
    
    # 1. Update Username (first_name)
    user.first_name = data.get('username', user.first_name)
    
    # 2. Update Email only if provided and not empty
    email = data.get('email')
    if email and email.strip():
        user.email = email
        
    # 3. Update Password 
    password = data.get('password')
    if password and password.strip(): # Only set if string is not empty
        user.set_password(password)
        
    user.save()
    
    return Response({
        "username": user.first_name,
        "email": user.email
    })

@api_view(['DELETE'])
def delete_user_profile(request, pk):
    user = get_object_or_404(User, pk=pk)
    
    # Because your ChatSession ForeignKey has on_delete=models.CASCADE,
    # and your ChatMessage has on_delete=models.CASCADE to the session,
    # deleting the user will clean up the entire tree.
    user.delete()
    
    return Response(
        {"message": "User and related data deleted successfully"}, 
        status=status.HTTP_204_NO_CONTENT
    )