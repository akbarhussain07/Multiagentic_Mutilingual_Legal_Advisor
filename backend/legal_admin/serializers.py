# from rest_framework import serializers
# from django.contrib.auth.models import User

# class UserSerializer(serializers.ModelSerializer):
#     first = serializers.CharField(source='first_name')
#     last = serializers.CharField(source='last_name')

#     class Meta:
#         model = User
#         fields = ['id','username', 'email', 'first', 'last', 'date_joined']




from rest_framework import serializers
from django.contrib.auth.models import User
from rag_api.models import ChatSession, ChatMessage

class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['message_id', 'role', 'content', 'created_at']

class ChatSessionSerializer(serializers.ModelSerializer):
    # This nests the messages inside each session
    messages = ChatMessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = ChatSession
        fields = ['session_id', 'title', 'created_at', 'updated_at', 'messages']

class UserSerializer(serializers.ModelSerializer):
    first = serializers.CharField(source='first_name')
    last = serializers.CharField(source='last_name')
    # Using the related_name from your model
    queries = ChatSessionSerializer(many=True, read_only=True, source='chat_sessions')

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first', 'last', 'queries']