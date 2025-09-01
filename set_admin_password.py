#!/usr/bin/env python
"""
Script to set the admin user's password to 'admin123'
Usage: python set_admin_password.py
"""
import os
import sys
import django

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'exam_project.settings')
django.setup()

from django.contrib.auth import get_user_model

def set_admin_password():
    try:
        # Get the admin user
        User = get_user_model()
        admin_user = User.objects.get(username='admin')
        
        # Set the password
        admin_user.set_password('admin123')
        admin_user.save()
        
        print("✅ Admin password successfully set to 'admin123'")
        print("You can now login to the admin panel with:")
        print("  Username: admin")
        print("  Password: admin123")
        
    except User.DoesNotExist:
        print("❌ Admin user not found. Please create the admin user first using:")
        print("  python manage.py createsuperuser --username admin --email admin@example.com --noinput")
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error setting admin password: {e}")
        sys.exit(1)

if __name__ == '__main__':
    set_admin_password() 