# cbe_app/services/otp_service.py

import random
import logging
from django.utils import timezone
from datetime import timedelta
from ...models import OTPCode, User
from .email_service import EmailService

logger = logging.getLogger(__name__)


class OTPService:
    """Service for OTP generation, validation, and management"""
    
    @staticmethod
    def generate_otp_code():
        """Generate a 6-digit OTP code"""
        return f"{random.randint(100000, 999999)}"
    
    @staticmethod
    def send_otp(user, otp_type):
        """
        Generate and send OTP to user's email
        otp_type: 'force_logout' or 'password_reset'
        Returns: (success, message, otp_object)
        """
        try:
            # Clean up any existing unused OTPs for this user and type
            OTPCode.objects.filter(
                user=user,
                otp_type=otp_type,
                is_used=False,
                expires_at__gt=timezone.now()
            ).delete()
            
            # Generate new OTP
            otp_code = OTPService.generate_otp_code()
            
            # Create OTP record (expires in 10 minutes)
            otp_object = OTPCode.objects.create(
                user=user,
                otp_code=otp_code,
                otp_type=otp_type,
                expires_at=timezone.now() + timedelta(minutes=10)
            )
            
            # Send email
            email_sent = EmailService.send_otp_email(user.email, otp_code, otp_type)
            
            if email_sent:
                logger.info(f"OTP sent to {user.email} for {otp_type}")
                return True, "OTP sent to your email", otp_object
            else:
                return False, "Failed to send OTP. Please try again.", None
                
        except Exception as e:
            logger.error(f"Error sending OTP: {str(e)}")
            return False, "An error occurred. Please try again.", None
    
    @staticmethod
    def verify_otp(user, otp_code, otp_type):
        """
        Verify OTP code for a user
        Returns: (is_valid, message)
        """
        try:
            # Find valid OTP
            otp = OTPCode.objects.filter(
                user=user,
                otp_code=otp_code,
                otp_type=otp_type,
                is_used=False,
                expires_at__gt=timezone.now()
            ).first()
            
            if not otp:
                return False, "Invalid or expired OTP code"
            
            # Mark as used
            otp.is_used = True
            otp.save()
            
            # Delete any other unused OTPs for this user and type
            OTPCode.objects.filter(
                user=user,
                otp_type=otp_type,
                is_used=False
            ).delete()
            
            logger.info(f"OTP verified for {user.email} for {otp_type}")
            return True, "OTP verified successfully"
            
        except Exception as e:
            logger.error(f"Error verifying OTP: {str(e)}")
            return False, "An error occurred during verification"
    
    @staticmethod
    def resend_otp(user, otp_type):
        """
        Resend OTP to user
        Returns: (success, message)
        """
        # Delete existing unused OTPs
        OTPCode.objects.filter(
            user=user,
            otp_type=otp_type,
            is_used=False
        ).delete()
        
        # Send new OTP
        return OTPService.send_otp(user, otp_type)
    @staticmethod
    def mask_email(email):
        """Mask email for display: j***@gmail.com"""
        if not email:
            return email
        parts = email.split('@')
        if len(parts) != 2:
            return email
        username, domain = parts
        if len(username) <= 3:
            masked_username = username[0] + '***'
        else:
            masked_username = username[:3] + '***'
        return f"{masked_username}@{domain}"