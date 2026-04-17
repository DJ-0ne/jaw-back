# api/views/auth_views.py   

from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from django.contrib.auth import authenticate
from django.utils import timezone
from django.core.exceptions import ValidationError
import uuid
import logging

from ...models import User, UserSession
from cbe_app.serializers.auth_serializers.auth_serializers import *

logger = logging.getLogger(__name__)


def get_tokens_for_user(user):
    """Generate JWT tokens with custom claims"""
    refresh = RefreshToken.for_user(user)
    
    # custom claims (role can be empty for legacy superusers)
    refresh['role'] = user.role or None
    refresh['email'] = user.email
    refresh['is_staff'] = user.is_staff
    refresh['is_superuser'] = user.is_superuser
    
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def check_active_session_exists(user):
    """Check if user already has an active session"""
    return UserSession.objects.filter(
        user=user,
        revoked=False ,
        expires_at__gt=timezone.now()
    ).exists()


def create_user_session(user, request, tokens):
    """Create a new user session"""
    session = UserSession.objects.create(
        user=user,
        access_token=tokens['access'],
        refresh_token=tokens['refresh'],
        client_ip=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        expires_at=timezone.now() + timezone.timedelta(days=7)
    )
    return session


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register(request):
    """Register a new user"""
    serializer = UserRegistrationSerializer(data=request.data)
    
    if serializer.is_valid():
        try:
            user = serializer.save()
            
            tokens = get_tokens_for_user(user)
            session = create_user_session(user, request, tokens)
            user_data = UserSerializer(user).data
            
            return Response({
                'message': 'User registered successfully',
                'user': user_data,
                'access': tokens['access'],
                'refresh': tokens['refresh'],
                'session_id': str(session.id)
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login(request):
    """Login user - REJECT if already logged in elsewhere"""
    serializer = UserLoginSerializer(data=request.data, context={'request': request})
    
    if serializer.is_valid():
        user = serializer.validated_data['user']
        
        # CHECK IF USER ALREADY HAS AN ACTIVE SESSION
        # if check_active_session_exists(user):
        #     return Response({
        #         'error': 'User is already logged in on another device.',
        #         'code': 'ACTIVE_SESSION_EXISTS'
        #     }, status=status.HTTP_409_CONFLICT)
        
        # Generate tokens
        tokens = get_tokens_for_user(user)
        session = create_user_session(user, request, tokens)
        user_data = UserSerializer(user).data
       
        return Response({
            'message': 'Login successful',
            'user': user_data,
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'session_id': str(session.id),
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout(request):
    """Logout user and invalidate session - FIXED VERSION"""
    try:
        # Get the access token from the request header
        auth_header = request.headers.get('Authorization', '')
        access_token = auth_header.replace('Bearer ', '')
        
        # Get the refresh token from request body
        refresh_token = request.data.get('refresh_token')
        
        if not access_token and not refresh_token:
            return Response({'error': 'No token provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Find and revoke the session using either access or refresh token
        session = None
        
        if refresh_token:
            session = UserSession.objects.filter(
                user=request.user,
                refresh_token=refresh_token,
                revoked=False
            ).first()
        
        if not session and access_token:
            session = UserSession.objects.filter(
                user=request.user,
                access_token=access_token,
                revoked=False
            ).first()
        
        if session:
            # Revoke the session
            session.revoked = True
            session.save()
            
            # Blacklist the refresh token if it exists
            if session.refresh_token:
                try:
                    token = RefreshToken(session.refresh_token)
                    token.blacklist()
                except Exception:
                    pass
            
            return Response({
                'message': 'Logout successful',
                'session_revoked': True
            }, status=status.HTTP_200_OK)
        else:
            # If no specific session found, revoke all sessions for this user
            # (This handles edge cases)
            sessions_revoked = UserSession.objects.filter(
                user=request.user, 
                revoked=False
            ).update(revoked=True)
            
            return Response({
                'message': f'Logout successful. {sessions_revoked} session(s) revoked.',
                'session_revoked': True
            }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def refresh_token(request):
    """Refresh access token"""
    refresh_token = request.data.get('refresh_token')
    
    if not refresh_token:
        return Response({'error': 'Refresh token is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Check if session exists and is not revoked
        session = UserSession.objects.filter(
            refresh_token=refresh_token,
            revoked=False,
            expires_at__gt=timezone.now()
        ).first()
        
        if not session:
            return Response({
                'error': 'Session expired or revoked. Please login again.'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        token = RefreshToken(refresh_token)
        user_id = token.payload.get('user_id')
        user = User.objects.get(id=user_id)
        
        new_tokens = get_tokens_for_user(user)
        
        # Update session with new tokens
        session.access_token = new_tokens['access']
        session.refresh_token = new_tokens['refresh']
        session.last_activity = timezone.now()
        session.save()
        
        return Response({
            'access': new_tokens['access'],
            'refresh': new_tokens['refresh']
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Refresh token error: {str(e)}")
        return Response({'error': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def validate_token(request):
    """Validate token and return full user info"""
    # Check if the session is still valid
    auth_header = request.headers.get('Authorization', '')
    access_token = auth_header.replace('Bearer ', '')
    
    session = UserSession.objects.filter(
        user=request.user,
        access_token=access_token,
        revoked=False,
        expires_at__gt=timezone.now()
    ).first()
    
    if not session:
        return Response({
            'valid': False,
            'error': 'Session expired or revoked'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    # Update last activity
    session.last_activity = timezone.now()
    session.save(update_fields=['last_activity'])
    
    user_data = UserSerializer(request.user).data
    return Response({
        'valid': True,
        'user': user_data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def check_username(request):
    """Check if username is available"""
    username = request.query_params.get('username', '')
    
    if len(username) < 3:
        return Response({
            'available': False,
            'error': 'Username must be at least 3 characters long'
        })
    
    exists = User.objects.filter(username=username).exists()
    return Response({
        'username': username,
        'available': not exists
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_user_profile(request):
    """Get current user profile"""
    return Response(UserSerializer(request.user).data)


@api_view(['PUT', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
def update_user_profile(request):
    """Update user profile"""
    serializer = UserSerializer(request.user, data=request.data, partial=True)
    
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_active_sessions(request):
    """Get all active sessions for the user"""
    sessions = UserSession.objects.filter(
        user=request.user,
        revoked=False,
        expires_at__gt=timezone.now()
    ).order_by('-last_activity')
    
    serializer = UserSessionSerializer(sessions, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def revoke_session(request, session_id):
    """Revoke a specific session"""
    try:
        session = UserSession.objects.get(id=session_id, user=request.user)
        
        # Don't allow revoking current session
        auth_header = request.headers.get('Authorization', '')
        current_token = auth_header.replace('Bearer ', '')
        
        if session.access_token == current_token:
            return Response({
                'error': 'Cannot revoke current session. Use logout instead.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        session.revoked = True
        session.save()
        
        return Response({'message': 'Session revoked successfully'})
    except UserSession.DoesNotExist:
        return Response({'error': 'Session not found'}, status=status.HTTP_404_NOT_FOUND)