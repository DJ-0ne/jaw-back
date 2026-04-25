# cbe_app/services/email_service.py

import random
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending emails and managing OTPs"""
    
    @staticmethod
    def generate_otp():
        """Generate a 6-digit OTP code"""
        return f"{random.randint(100000, 999999)}"
    
    @staticmethod
    def send_otp_email(email, otp_code, otp_type):
        """
        Send OTP email to user
        otp_type: 'force_logout' or 'password_reset'
        """
        if otp_type == 'force_logout':
            subject = "Force Login Verification Code - JAWABU SCHOOL"
            message = f"""
            Hello,
            
            You requested to force logout from another device and login to your account.
            
            Your verification code is: {otp_code}
            
            This code will expire in 10 minutes.
            
            If you did not request this, please ignore this email or contact support.
            
            Best regards,
            JAWABU SCHOOL System
            """
        else:  # password_reset
            subject = "Password Reset Verification Code - JAWABU SCHOOL"
            message = f"""
            Hello,
            
            You requested to reset your password.
            
            Your verification code is: {otp_code}
            
            This code will expire in 10 minutes.
            
            If you did not request this, please ignore this email or contact support.
            
            Best regards,
            JAWABU SCHOOL System
            """
        
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            logger.info(f"OTP email sent to {email} for {otp_type}")
            return True
        except Exception as e:
            logger.error(f"Failed to send OTP email to {email}: {str(e)}")
            return False