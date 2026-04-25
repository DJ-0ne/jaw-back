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
from ...services.email.otp_service import OTPService

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
    """Login user - with OTP support for force logout"""
    serializer = UserLoginSerializer(data=request.data, context={'request': request})
    
    if serializer.is_valid():
        user = serializer.validated_data['user']
        
        # Check if user already has an active session
        has_active_session = check_active_session_exists(user)
        
        # Check if this is a force logout request
        force_logout = request.data.get('force_logout', False)
        otp_code = request.data.get('otp_code', None)
        
        # CASE 1: Force logout with OTP verification (step 2)
        if force_logout and otp_code:
            # Verify OTP
            is_valid, message = OTPService.verify_otp(user, otp_code, 'force_logout')
            if not is_valid:
                return Response({
                    'success': False,
                    'error': message,
                    'code': 'INVALID_OTP'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # OTP verified - create new session and login
            tokens = get_tokens_for_user(user)
            session = create_user_session(user, request, tokens)
            user_data = UserSerializer(user).data
            
            return Response({
                'success': True,
                'message': 'Login successful',
                'user': user_data,
                'access': tokens['access'],
                'refresh': tokens['refresh'],
                'session_id': str(session.id),
            }, status=status.HTTP_200_OK)
        
        # CASE 2: Force logout request (step 1 - revoke sessions)
        if force_logout:
            # Revoke all existing sessions for this user
            UserSession.objects.filter(user=user, revoked=False).update(revoked=True)
            
            # Send OTP to user's email
            success, message, _ = OTPService.send_otp(user, 'force_logout')
            
            if success:
                return Response({
                    'success': False,
                    'code': 'OTP_REQUIRED',
                    'message': 'Sessions revoked. Please enter OTP sent to your email.',
                    'email_masked': OTPService.mask_email(user.email)
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'error': 'Failed to send OTP. Please try again.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # CASE 3: Normal login - has active session
        if has_active_session:
            return Response({
                'success': False,
                'error': 'User is already logged in on another device.',
                'code': 'ACTIVE_SESSION_EXISTS',
                'force_logout_available': True
            }, status=status.HTTP_409_CONFLICT)
        
        # CASE 4: Normal login - no active session
        tokens = get_tokens_for_user(user)
        session = create_user_session(user, request, tokens)
        user_data = UserSerializer(user).data
       
        return Response({
            'success': True,
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
    
    
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def resend_force_logout_otp(request):
    """Resend OTP for force logout"""
    serializer = ResendForceLogoutOTPSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    email = serializer.validated_data['email']
    
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    success, message, _ = OTPService.send_otp(user, 'force_logout')
    
    if success:
        return Response({
            'success': True,
            'message': message,
            'email_masked': OTPService.mask_email(user.email)
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            'success': False,
            'error': message
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def request_password_reset_otp(request):
    """Request OTP for password reset"""
    serializer = RequestPasswordResetOTPSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    email = serializer.validated_data['email']
    user = User.objects.get(email__iexact=email)
    
    success, message, _ = OTPService.send_otp(user, 'password_reset')
    
    if success:
        return Response({
            'success': True,
            'message': message,
            'email_masked': OTPService.mask_email(user.email),
            'user_id': str(user.id)
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            'success': False,
            'error': message
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def verify_password_reset_otp(request):
    """Verify OTP for password reset"""
    serializer = VerifyPasswordResetOTPSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    email = serializer.validated_data['email']
    otp_code = serializer.validated_data['otp_code']
    
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    is_valid, message = OTPService.verify_otp(user, otp_code, 'password_reset')
    
    if is_valid:
        return Response({
            'success': True,
            'message': message,
            'user_id': str(user.id)
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            'success': False,
            'error': message
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def reset_password(request):
    """Reset password after OTP verification"""
    serializer = ResetPasswordSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    user_id = serializer.validated_data['user_id']
    new_password = serializer.validated_data['new_password']
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    user.set_password(new_password)
    user.save()
    
    # Revoke all sessions after password change
    UserSession.objects.filter(user=user, revoked=False).update(revoked=True)
    
    return Response({
        'success': True,
        'message': 'Password reset successfully. Please login with your new password.'
    }, status=status.HTTP_200_OK)