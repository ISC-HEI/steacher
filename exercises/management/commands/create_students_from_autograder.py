
import os
import sys
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

# --- BEGIN COPIED LOGIC from autograder_study ---
# This section is copied from your autograder_study project to parse student data.
# In a real-world scenario, this might be refactored into a shared library.

import pandas as pd
from bs4 import BeautifulSoup

def extract_data_from_html(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    rows = soup.find_all('tr')
    
    headers = [th.text.strip() for th in rows[0].find_all('th')]
    
    data = []
    for row in rows[1:]:
        cells = row.find_all('td')
        row_data = [cell.text.strip() for cell in cells]
        data.append(row_data)
    
    df = pd.DataFrame(data, columns=headers)
    return df

def parse_student_answers(df):
    num_questions = len([header for header in df.columns if header.startswith("Réponse")])
    answers = {}
    for index, row in df.iterrows():
        student_email_user = row.get('Adresse de courriel', '').replace('@students.hevs.ch', '')
        if not student_email_user or not isinstance(student_email_user, str):
            continue

        parts = student_email_user.split('.')
        student_name_formatted = ' '.join(part.capitalize() for part in parts[::-1])
        
        student_answers = {}
        for i in range(1, num_questions + 1):
            student_answers[i] = row.get(f"Réponse {i}")

        answers[student_email_user] = {"name": student_name_formatted, "answers": student_answers}
    return answers

# --- END COPIED LOGIC ---

class Command(BaseCommand):
    help = 'Creates students from the autograder HTML file.'

    def handle(self, *args, **options):
        self.stdout.write("Starting to create students from autograder file...")

        # Path to the autograder project.
        # This should be configured more robustly in a real application.
        root_path = '/Users/ren/switchdrive/backup/dev/autograder_study'
        student_answers_file = os.path.join(
            root_path,
            "24_25_HES-SO-VS_Informatique_TC-[20242025] Examen semestriel Semesterprüfung-réponses.html"
        )

        if not os.path.exists(student_answers_file):
            self.stderr.write(self.style.ERROR(f"File not found: {student_answers_file}"))
            return

        try:
            df = extract_data_from_html(student_answers_file)
            answers = parse_student_answers(df)
            student_usernames = list(answers.keys())
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to parse student answers: {e}"))
            return

        User = get_user_model()
        created_count = 0
        for username in student_usernames:
            username = username.replace('@hevs.ch', '')
            if not username or '.' not in username:
                self.stdout.write(self.style.WARNING(f"Skipping invalid username: {username}"))
                continue

            # Check if user already exists
            if User.objects.filter(username=username).exists():
                self.stdout.write(self.style.NOTICE(f"User '{username}' already exists. Skipping."))
                continue
            
            # Parse first and last names
            parts = username.split('.')
            first_name = parts[0].capitalize()
            last_name = '.'.join(parts[1:]).capitalize()
            email = f"{username}@test.ch"
            
            try:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password='p' # All users get a default password
                )
                user.first_name = first_name
                user.last_name = last_name
                user.save()
                
                self.stdout.write(self.style.SUCCESS(f"Successfully created user: {username}"))
                created_count += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to create user {username}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. Created {created_count} new users."))
