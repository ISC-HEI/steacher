# Steacher

## Quick Start

### 1. Install PostgreSQL

Make sure PostgreSQL is installed and running on your system

### 2. Create Database

Create the PostgreSQL database:
```bash
# Connect to PostgreSQL as postgres user
psql -U postgres

# Create database
CREATE DATABASE steacher;

# Exit psql
\q
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run Migrations

```bash
python manage.py migrate
```

### 5. Create Sample Data

```bash
python manage.py create_sample_exercises
```

### 6. Create Admin User

```bash
python manage.py createsuperuser --username admin --email admin@example.com --noinput
python set_admin_password.py  # Sets password to 'admin123'
```

### 7. Start Development Server

```bash
# Terminal 1: Django
cd test_django
python manage.py runserver

# Terminal 2: TypeScript compiler
cd test_django  
npm run watch
```




Visit `http://127.0.0.1:8000/` to see the exercise list.




## Database Configuration

The project uses PostgreSQL with the following default settings:
- Database: `steacher`
- Username: `postgres`
- Password: `postgres`
- Host: `localhost`
- Port: `5432`

You can modify these settings in `exam_project/settings.py` if needed.

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

