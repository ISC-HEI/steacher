#!/usr/bin/env python
"""
Test script for the Mailtrap email backend.
Run with: python test_mailtrap_backend.py
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'exam_project.settings')
django.setup()

from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings

def test_simple_email():
    """Test sending a simple text email."""
    print("Testing simple text email...")
    print(f"Using backend: {settings.EMAIL_BACKEND}")
    print(f"From: {settings.DEFAULT_FROM_EMAIL}")
    
    try:
        send_mail(
            subject='Test Email from Steacher',
            message='This is a test email sent via the new Mailtrap backend.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['renaud.renard@gmail.com'],
            fail_silently=False,
        )
        print("✅ Simple email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send simple email: {e}")
        raise

def test_html_email():
    """Test sending an HTML email."""
    print("\nTesting HTML email...")
    
    try:
        msg = EmailMultiAlternatives(
            subject='HTML Test Email from Steacher',
            body='This is the plain text version.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=['renaud.renard@gmail.com'],
        )
        
        html_content = """
        <html>
            <body>
                <h1>Hello from Steacher!</h1>
                <p>This is an <strong>HTML</strong> email sent via the Mailtrap API backend.</p>
                <p>It should be <em>much faster</em> than SMTP! ⚡</p>
            </body>
        </html>
        """
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        
        print("✅ HTML email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send HTML email: {e}")
        raise


if __name__ == '__main__':
    print("=" * 60)
    print("Mailtrap Backend Test Suite")
    print("=" * 60)
    
    if not settings.MAILTRAP_API_KEY:
        print("❌ MAILTRAP_API_KEY is not set in environment variables!")
        print("Please set it in your .env file and try again.")
        sys.exit(1)
    
    try:
        test_simple_email()
        test_html_email()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ Test suite failed: {e}")
        print("=" * 60)
        sys.exit(1)

