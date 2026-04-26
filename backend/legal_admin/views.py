from django.contrib.auth.models import User
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .serializers import UserSerializer
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from rest_framework.permissions import IsAdminUser

@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_users(request):
    users = User.objects.all()
    serializer = UserSerializer(users, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def user_detail(request, pk):
    user = get_object_or_404(User, pk=pk)
    serializer = UserSerializer(user)
    return Response(serializer.data)


@api_view(['PUT'])
@permission_classes([IsAdminUser])
def update_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    data = request.data
    
    user.first_name = data.get('first', user.first_name)
    #user.last_name = data.get('last', user.last_name)
    user.email = data.get('email', user.email)
    
    password = data.get('password')
    if password:
        user.set_password(password)
        
    user.save()
    return Response({
        "first": user.first_name,
        "email": user.email
    })


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def delete_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    
    # Because your ChatSession ForeignKey has on_delete=models.CASCADE,
    # and your ChatMessage has on_delete=models.CASCADE to the session,
    # deleting the user will clean up the entire tree.
    user.delete()
    
    return Response(
        {"message": "User and related data deleted successfully"}, 
        status=status.HTTP_204_NO_CONTENT
    )