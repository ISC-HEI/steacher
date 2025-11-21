import os
import json
import re
from django.core.management.base import BaseCommand
from exercises.models import Course

class Command(BaseCommand):
    help = 'Exports courses from the database to JSON files.'

    def handle(self, *args, **options):
        self.stdout.write("Course Export Tool")
        self.stdout.write("=" * 50)
        
        # Create exports directory if it doesn't exist
        exports_dir = 'exports'
        if not os.path.exists(exports_dir):
            os.makedirs(exports_dir)
            self.stdout.write(self.style.SUCCESS(f"Created exports directory: {exports_dir}"))
        
        # Get all courses
        courses = Course.objects.all().order_by('name')
        
        if not courses:
            self.stderr.write(self.style.ERROR("No courses found in database."))
            return
            
        # Display available courses
        self.stdout.write("\nAvailable courses:")
        for i, course in enumerate(courses, 1):
            module_count = course.modules.count()
            exercise_count = sum(module.exercises.count() for module in course.modules.all())
            self.stdout.write(f"  {i}. {course.name} ({module_count} modules, {exercise_count} exercises)")
        
        # Interactive selection
        while True:
            try:
                selection = input(f"\nSelect course to export (1-{len(courses)}) or 'q' to quit: ")
                if selection.lower() == 'q':
                    self.stdout.write("Export cancelled.")
                    return
                    
                course_index = int(selection) - 1
                if 0 <= course_index < len(courses):
                    selected_course = courses[course_index]
                    break
                else:
                    self.stderr.write(f"Please enter a number between 1 and {len(courses)}")
            except ValueError:
                self.stderr.write("Please enter a valid number or 'q' to quit")
        
        # Check for legacy data and ask user
        legacy_items = self.check_legacy_data(selected_course)
        transform_legacy = False
        if legacy_items:
            self.stdout.write(self.style.WARNING(f"\nLegacy non-i18n data found in course '{selected_course.name}':"))
            for item in legacy_items:
                self.stdout.write(self.style.WARNING(f"  - {item}"))
            self.stdout.write("")
            response = input("Transform to i18n format? (y/N): ")
            transform_legacy = response.lower() == 'y'
        
        # Export the course
        try:
            self.export_course(selected_course, exports_dir, transform_legacy)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Export failed: {e}"))
            return

    def check_legacy_data(self, course):
        """Check if the course has any legacy non-i18n data and return list of found items."""
        legacy_items = []
        
        # Check modules
        for module in course.modules.all():
            # Check exercises
            for exercise in module.exercises.all():
                exercise_title = self.get_display_title(exercise)
                
                if isinstance(exercise.title_i18n, str):
                    legacy_items.append(f"Exercise title: '{exercise_title}' (string instead of i18n dict)")
                elif not exercise.title_i18n:
                    legacy_items.append(f"Exercise {exercise.id}: empty title_i18n field")
                    
                if isinstance(exercise.description_i18n, str) and exercise.description_i18n:
                    desc_preview = exercise.description_i18n[:50] + "..." if len(exercise.description_i18n) > 50 else exercise.description_i18n
                    legacy_items.append(f"Exercise '{exercise_title}' description: '{desc_preview}' (string instead of i18n dict)")
                
                # Check question_i18n field
                if isinstance(exercise.question_i18n, str) and exercise.question_i18n:
                    question_preview = exercise.question_i18n[:50] + "..." if len(exercise.question_i18n) > 50 else exercise.question_i18n
                    legacy_items.append(f"Exercise '{exercise_title}' question: '{question_preview}' (string instead of i18n dict)")
        
        return legacy_items

    def sanitize_filename(self, name):
        """Sanitize course name for use in filename."""
        # Replace spaces with underscores
        name = name.replace(' ', '_')
        # Remove special characters (keep only alphanumeric, underscore, hyphen)
        name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
        # Remove multiple consecutive underscores
        name = re.sub(r'_+', '_', name)
        # Remove leading/trailing underscores
        name = name.strip('_')
        return name

    def get_unique_filename(self, base_path):
        """Get a unique filename by appending number if file exists."""
        if not os.path.exists(base_path):
            return base_path
            
        # Extract directory, name and extension
        directory = os.path.dirname(base_path)
        filename = os.path.basename(base_path)
        name, ext = os.path.splitext(filename)
        
        counter = 2
        while True:
            new_filename = f"{name}_{counter}{ext}"
            new_path = os.path.join(directory, new_filename)
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    def transform_to_i18n(self, value, default_lang='en'):
        """Transform a string value to i18n format."""
        if isinstance(value, dict):
            return value  # Already i18n
        elif isinstance(value, str):
            return {default_lang: value} if value else {}
        else:
            return {}

    def export_course(self, course, exports_dir, transform_legacy):
        """Export a single course to JSON file."""
        self.stdout.write(f"\nExporting course: {course.name}")
        
        # Prepare course data - course name/description are single strings, keep as strings
        course_data = {
            'name': course.name,
            'description': course.description,
            'chat_prompt': course.chat_prompt,
            'modules': []
        }
        
        # Get modules ordered by their order field
        modules = course.modules.all().order_by('order')
        
        if not modules:
            self.stdout.write(self.style.WARNING(f"  Course has no modules. Skipping export."))
            return
        
        for module in modules:
            self.stdout.write(f"  Processing module: {module.name}")
            
            # Module name/description are single strings, keep as strings
            module_data = {
                'name': module.name,
                'description': module.description,
                'exercises': []
            }
            
            # Get exercises ordered by their order field
            exercises = module.exercises.all().order_by('order')
            
            if not exercises:
                self.stdout.write(self.style.NOTICE(f"    Module has no exercises. Including anyway."))
            
            for exercise in exercises:
                self.stdout.write(f"    Processing exercise: {self.get_display_title(exercise)}")
                
                # Exercise fields use i18n - handle legacy transformation for exercises only
                exercise_data = {
                    'title': self.transform_to_i18n(exercise.title_i18n) if transform_legacy else exercise.title_i18n,
                    'description': self.transform_to_i18n(exercise.description_i18n) if transform_legacy else exercise.description_i18n,
                    'question': self.transform_to_i18n(exercise.question_i18n) if transform_legacy else exercise.question_i18n,
                    'exercise_type': exercise.exercise_type,
                    'visible': exercise.visible,
                    'allow_image_upload': exercise.allow_image_upload,
                    'exercise_data': exercise.exercise_data or {},
                    'answer_data': exercise.answer_data or {}
                }
                
                module_data['exercises'].append(exercise_data)
            
            course_data['modules'].append(module_data)
        
        # Create the final JSON structure
        export_data = {
            'courses': [course_data]
        }
        
        # Generate filename
        sanitized_name = self.sanitize_filename(course.name)
        base_filename = f"course_{sanitized_name}.json"
        base_path = os.path.join(exports_dir, base_filename)
        final_path = self.get_unique_filename(base_path)
        
        # Write to file
        try:
            with open(final_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            self.stdout.write(self.style.SUCCESS(f"\nExport completed successfully!"))
            self.stdout.write(self.style.SUCCESS(f"File saved to: {final_path}"))
            
            # Show statistics
            total_modules = len(course_data['modules'])
            total_exercises = sum(len(module['exercises']) for module in course_data['modules'])
            self.stdout.write(f"Exported: 1 course, {total_modules} modules, {total_exercises} exercises")
            
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to write file: {e}"))

    def get_display_title(self, exercise):
        """Get a display title for an exercise (handles both legacy and i18n)."""
        if isinstance(exercise.title_i18n, dict) and exercise.title_i18n:
            return next(iter(exercise.title_i18n.values()))
        elif isinstance(exercise.title_i18n, str):
            return exercise.title_i18n
        else:
            return f"Exercise {exercise.id}"