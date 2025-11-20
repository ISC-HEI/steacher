
import os
import json
from django.core.management.base import BaseCommand
from django.db import transaction
from exercises.models import Exercise, Course, Module

class Command(BaseCommand):
    help = 'Imports courses, modules, and exercises from a JSON file into the database.'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Path to the JSON file containing courses and exercises')

    def handle(self, *args, **options):
        self.stdout.write("Starting to import courses, modules, and exercises...")
        
        json_file_path = options['json_file']
        
        # Validate file exists
        if not os.path.exists(json_file_path):
            self.stderr.write(self.style.ERROR(f"JSON file not found at: {json_file_path}"))
            return

        # Load and validate JSON
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            self.stderr.write(self.style.ERROR(f"Invalid JSON: {e}"))
            return
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error reading file: {e}"))
            return

        # Validate JSON structure and collect all errors
        validation_errors = self.validate_json_structure(data)
        if validation_errors:
            self.stderr.write(self.style.ERROR("Validation errors found:"))
            for error in validation_errors:
                self.stderr.write(self.style.ERROR(f"  - {error}"))
            return

        # Check for course name conflicts in database
        conflict_errors = self.check_course_conflicts(data)
        if conflict_errors:
            for error in conflict_errors:
                response = input(f"{error} Continue anyway? (y/N): ")
                if response.lower() != 'y':
                    self.stdout.write("Import cancelled.")
                    return

        # Check for exercise conflicts and get user decisions
        exercise_conflicts = self.check_exercise_conflicts(data)
        overwrite_decisions = {}
        for conflict in exercise_conflicts:
            response = input(f"{conflict} Overwrite existing exercise? (y/N): ")
            overwrite_decisions[conflict] = response.lower() == 'y'

        # Perform the import in a transaction
        try:
            with transaction.atomic():
                self.import_data(data, overwrite_decisions)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Import failed: {e}"))
            return

        self.stdout.write(self.style.SUCCESS("Import completed successfully!"))

    def get_default_chat_prompt(self):
        """Load the default chat prompt from the file."""
        try:
            # Get the directory where this command file is located
            command_dir = os.path.dirname(os.path.abspath(__file__))
            # Navigate to the prompts directory
            prompts_dir = os.path.join(command_dir, '..', '..', 'prompts')
            chat_prompt_path = os.path.join(prompts_dir, 'chat_mode_prompt.md')
            
            if os.path.exists(chat_prompt_path):
                with open(chat_prompt_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not load default chat prompt: {e}"))
        
        return ""

    def validate_json_structure(self, data):
        """Validate the JSON structure and return list of errors."""
        errors = []
        
        if not isinstance(data, dict):
            errors.append("JSON must be an object")
            return errors
            
        if 'courses' not in data:
            errors.append("Missing 'courses' key in JSON")
            return errors
            
        if not isinstance(data['courses'], list):
            errors.append("'courses' must be an array")
            return errors
            
        if not data['courses']:
            errors.append("'courses' array cannot be empty")
            return errors

        # Validate courses
        course_names = []
        for i, course in enumerate(data['courses']):
            course_errors = self.validate_course(course, f"courses[{i}]")
            errors.extend(course_errors)
            
            # Check for duplicate course names within JSON (now course names are direct strings)
            if isinstance(course, dict) and 'name' in course:
                course_name = course['name']
                if isinstance(course_name, str):
                    if course_name in course_names:
                        errors.append(f"Duplicate course name '{course_name}' found in JSON")
                    else:
                        course_names.append(course_name)
        
        return errors

    def validate_course(self, course, path):
        """Validate a course object and return list of errors."""
        errors = []
        
        if not isinstance(course, dict):
            errors.append(f"{path}: Course must be an object")
            return errors
            
        # Validate required fields
        if 'name' not in course:
            errors.append(f"{path}: Missing required 'name' field")
        else:
            # Course name is a direct string, not i18n
            if not isinstance(course['name'], str):
                errors.append(f"{path}.name: Must be a string")
            
        # Validate optional fields
        if 'description' in course:
            # Course description is a direct string, not i18n
            if not isinstance(course['description'], str):
                errors.append(f"{path}.description: Must be a string")
            
        # Validate optional chat_prompt field
        if 'chat_prompt' in course:
            if not isinstance(course['chat_prompt'], str):
                errors.append(f"{path}.chat_prompt: Must be a string")
            
        # Validate modules
        if 'modules' not in course:
            errors.append(f"{path}: Missing 'modules' field")
        elif not isinstance(course['modules'], list):
            errors.append(f"{path}: 'modules' must be an array")
        elif not course['modules']:
            errors.append(f"{path}: 'modules' array cannot be empty")
        else:
            for i, module in enumerate(course['modules']):
                module_errors = self.validate_module(module, f"{path}.modules[{i}]")
                errors.extend(module_errors)
                
        return errors

    def validate_module(self, module, path):
        """Validate a module object and return list of errors."""
        errors = []
        
        if not isinstance(module, dict):
            errors.append(f"{path}: Module must be an object")
            return errors
            
        # Validate required fields
        if 'name' not in module:
            errors.append(f"{path}: Missing required 'name' field")
        else:
            # Module name is a direct string, not i18n
            if not isinstance(module['name'], str):
                errors.append(f"{path}.name: Must be a string")
            
        # Validate optional fields
        if 'description' in module:
            # Module description is a direct string, not i18n
            if not isinstance(module['description'], str):
                errors.append(f"{path}.description: Must be a string")
            
        # Validate exercises
        if 'exercises' not in module:
            errors.append(f"{path}: Missing 'exercises' field")
        elif not isinstance(module['exercises'], list):
            errors.append(f"{path}: 'exercises' must be an array")
        elif not module['exercises']:
            errors.append(f"{path}: 'exercises' array cannot be empty")
        else:
            for i, exercise in enumerate(module['exercises']):
                exercise_errors = self.validate_exercise(exercise, f"{path}.exercises[{i}]")
                errors.extend(exercise_errors)
                
        return errors

    def validate_exercise(self, exercise, path):
        """Validate an exercise object and return list of errors."""
        errors = []
        
        if not isinstance(exercise, dict):
            errors.append(f"{path}: Exercise must be an object")
            return errors
            
        # Validate required fields
        required_fields = ['title', 'exercise_type']
        for field in required_fields:
            if field not in exercise:
                errors.append(f"{path}: Missing required '{field}' field")
                
        # Validate title
        if 'title' in exercise:
            title_errors = self.validate_i18n_field(exercise['title'], f"{path}.title", required=True)
            errors.extend(title_errors)
            
        # Validate optional i18n fields
        for field in ['description']:
            if field in exercise:
                field_errors = self.validate_i18n_field(exercise[field], f"{path}.{field}", required=False)
                errors.extend(field_errors)
                
        # Validate exercise_type
        if 'exercise_type' in exercise:
            valid_types = [choice[0] for choice in Exercise.EXERCISE_TYPE_CHOICES]
            if exercise['exercise_type'] not in valid_types:
                errors.append(f"{path}.exercise_type: Invalid exercise type '{exercise['exercise_type']}'. Valid types: {valid_types}")
                
        # Validate exercise_data
        if 'exercise_data' in exercise:
            if not isinstance(exercise['exercise_data'], dict):
                errors.append(f"{path}.exercise_data: Must be an object")
            else:
                # Validate question field in exercise_data
                if 'question' in exercise['exercise_data']:
                    question_errors = self.validate_i18n_field(exercise['exercise_data']['question'], f"{path}.exercise_data.question", required=False)
                    errors.extend(question_errors)
                    
        # Validate answer_data (should be English only)
        if 'answer_data' in exercise:
            if not isinstance(exercise['answer_data'], dict):
                errors.append(f"{path}.answer_data: Must be an object")
                
        # Validate allow_image_upload (optional boolean)
        if 'allow_image_upload' in exercise:
            if not isinstance(exercise['allow_image_upload'], bool):
                errors.append(f"{path}.allow_image_upload: Must be a boolean (true/false)")
                
        return errors

    def validate_i18n_field(self, field_value, path, required=True):
        """Validate an i18n field (should be dict with language codes as keys)."""
        errors = []
        
        if field_value is None:
            if required:
                errors.append(f"{path}: Cannot be null")
            return errors
            
        if not isinstance(field_value, dict):
            errors.append(f"{path}: Must be an object with language codes as keys")
            return errors
            
        if required and not field_value:
            errors.append(f"{path}: Must contain at least one language")
            return errors
            
        # Validate that all values are strings
        for lang_code, value in field_value.items():
            if not isinstance(value, str):
                errors.append(f"{path}.{lang_code}: Value must be a string")
                
        return errors

    def check_course_conflicts(self, data):
        """Check for course name conflicts with existing database entries."""
        conflicts = []
        
        for course in data['courses']:
            if 'name' in course and isinstance(course['name'], str):
                # Course names are now direct strings
                course_name = course['name']
                if Course.objects.filter(name=course_name).exists():
                    conflicts.append(f"Course '{course_name}' already exists in database.")
                        
        return conflicts

    def check_exercise_conflicts(self, data):
        """Check for exercise conflicts and return list of conflict descriptions."""
        conflicts = []
        
        for course in data['courses']:
            if 'name' not in course or 'modules' not in course:
                continue
                
            course_name = course['name'] if isinstance(course['name'], str) else None
            if not course_name:
                continue
                
            for module in course['modules']:
                if 'name' not in module or 'exercises' not in module:
                    continue
                    
                module_name = module['name'] if isinstance(module['name'], str) else None
                if not module_name:
                    continue
                    
                for exercise in module['exercises']:
                    if 'title' not in exercise:
                        continue
                        
                    exercise_title = self.get_first_language_value(exercise['title'])
                    if not exercise_title:
                        continue
                        
                    # Check if exercise with this title exists in any module of any course with this name
                    existing_courses = Course.objects.filter(name=course_name)
                    for existing_course in existing_courses:
                        for existing_module in existing_course.modules.all():
                            if Exercise.objects.filter(
                                module=existing_module,
                                title_i18n__has_any_keys=[lang for lang in exercise['title'].keys()]
                            ).filter(
                                **{f"title_i18n__{lang}": exercise['title'][lang] for lang in exercise['title'].keys()}
                            ).exists():
                                conflicts.append(f"Exercise '{exercise_title}' in module '{module_name}' of course '{course_name}'")
                                
        return conflicts

    def get_first_language_value(self, i18n_dict):
        """Get the first available language value from an i18n dictionary."""
        if not isinstance(i18n_dict, dict) or not i18n_dict:
            return None
        return next(iter(i18n_dict.values()))

    def import_data(self, data, overwrite_decisions):
        """Import the validated data into the database."""
        stats = {'courses_created': 0, 'modules_created': 0, 'exercises_created': 0, 'exercises_updated': 0}
        
        for course_data in data['courses']:
            self.stdout.write(f"Processing course: {course_data['name']}")
            
            # Create or get course (course name is now a direct string)
            course_name = course_data['name']
            default_chat_prompt = self.get_default_chat_prompt()
            
            course, created = Course.objects.get_or_create(
                name=course_name,
                defaults={
                    'description': course_data.get('description', ''),
                    'chat_prompt': course_data.get('chat_prompt', default_chat_prompt)
                }
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f"  Created course: {course_name}"))
                stats['courses_created'] += 1
            else:
                self.stdout.write(self.style.NOTICE(f"  Using existing course: {course_name}"))
            
            # Process modules
            for module_order, module_data in enumerate(course_data['modules'], 1):
                module_name = module_data['name']
                self.stdout.write(f"  Processing module: {module_name}")
                
                module, created = Module.objects.get_or_create(
                    course=course,
                    name=module_name,
                    defaults={
                        'description': module_data.get('description', ''),
                        'order': module_order
                    }
                )
                
                if created:
                    self.stdout.write(self.style.SUCCESS(f"    Created module: {module_name}"))
                    stats['modules_created'] += 1
                else:
                    self.stdout.write(self.style.NOTICE(f"    Using existing module: {module_name}"))
                
                # Process exercises
                for exercise_order, exercise_data in enumerate(module_data['exercises'], 1):
                    exercise_title = self.get_first_language_value(exercise_data['title'])
                    self.stdout.write(f"    Processing exercise: {exercise_title}")
                    
                    # Check if exercise exists and handle accordingly
                    existing_exercise = None
                    for lang, title in exercise_data['title'].items():
                        existing_exercise = Exercise.objects.filter(
                            module=module,
                            **{f"title_i18n__{lang}": title}
                        ).first()
                        if existing_exercise:
                            break
                    
                    if existing_exercise:
                        conflict_key = f"Exercise '{exercise_title}' in module '{module_name}' of course '{course_name}'"
                        if overwrite_decisions.get(conflict_key, False):
                            existing_exercise.delete()
                            self.stdout.write(self.style.WARNING(f"      Deleted existing exercise: {exercise_title}"))
                        else:
                            self.stdout.write(self.style.NOTICE(f"      Skipped existing exercise: {exercise_title}"))
                            continue
                    
                    # Create new exercise
                    exercise = Exercise.objects.create(
                        module=module,
                        title_i18n=exercise_data['title'],
                        description_i18n=exercise_data.get('description', {}),
                        exercise_type=exercise_data['exercise_type'],
                        order=exercise_order,
                        exercise_data=exercise_data.get('exercise_data', {}),
                        answer_data=exercise_data.get('answer_data', {}),
                        visible=exercise_data.get('visible', True),
                        allow_image_upload=exercise_data.get('allow_image_upload', False)
                    )
                    
                    self.stdout.write(self.style.SUCCESS(f"      Created exercise: {exercise_title}"))
                    stats['exercises_created'] += 1
        
        # Print final statistics
        self.stdout.write(self.style.SUCCESS(f"\nImport Summary:"))
        self.stdout.write(self.style.SUCCESS(f"  Courses created: {stats['courses_created']}"))
        self.stdout.write(self.style.SUCCESS(f"  Modules created: {stats['modules_created']}"))
        self.stdout.write(self.style.SUCCESS(f"  Exercises created: {stats['exercises_created']}"))
        if stats['exercises_updated']:
            self.stdout.write(self.style.SUCCESS(f"  Exercises updated: {stats['exercises_updated']}"))
