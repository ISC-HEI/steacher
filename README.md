# Steacher

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run Migrations

```bash
python manage.py migrate
```

### 3. Create Sample Data

```bash
python manage.py create_sample_exercises
```

### 4. Create Admin User

```bash
python manage.py createsuperuser --username admin --email admin@example.com --noinput
python set_admin_password.py  # Sets password to 'admin123'
```

### 5. Start Development Server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` to see the exercise list.

## Admin Access

- URL: `http://127.0.0.1:8000/admin/`
- Username: `admin`
- Password: `admin123`


## Exercise Data Structure

Exercises are stored with flexible JSON data. Example multiple choice exercise:

```json
{
  "title": "Python Basics: Variables",
  "description": "Test your knowledge of Python variable declarations.",
  "exercise_type": "multiple_choice",
  "exercise_data": {
    "question": "Which of the following is the correct way to declare a variable in Python?",
    "choices": [
      {
        "id": "a",
        "text": "int x = 5",
        "is_correct": false
      },
      {
        "id": "b", 
        "text": "x = 5",
        "is_correct": true
      }
    ]
  }
}
```

## Adding New Exercise Types

1. **Backend**: No changes needed - the Exercise model uses JSON fields
2. **Frontend**: Create a new Vue.js component with exact same name as exercise_type
3. **Component Registration**: Add the component using the exact database exercise_type string

Example: If your exercise_type is `'turtle'`, create a component named `turtle` and register it as `'turtle': turtle`

## Vue.js Architecture

- **MPA Approach**: Each page is a separate Django template with embedded Vue.js
- **Component-Based**: Different exercise types use different Vue.js components
- **1:1 Mapping**: Component names match database exercise_type strings exactly
- **State Management**: Simple - state resets on each page load
- **API Integration**: Uses fetch API for answer submission

