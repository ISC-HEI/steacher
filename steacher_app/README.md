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

### 6.1 Create sample data
```bash
python manage.py create_sample_exercises
python manage.py create_students_from_autograder
python manage.py import_questions
# setup exercice id in mgmt script
python manage.py populate_traces
```


### 7. Start Development Server

```bash
# Terminal 1: Django
python manage.py runserver

# Terminal 2: TypeScript compiler
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

## CodeMirror v6 Bundling

### Why Bundling?

CodeMirror v6 has a complex dependency tree with many separate ES modules. Using import maps for all dependencies would require mapping 15+ packages individually, leading to:
- Dependency hell with "bare specifier" errors
- Multiple HTTP requests (slower loading)
- Complex import map maintenance

### Solution: Single Bundle

We use Rollup to bundle all CodeMirror dependencies into a single file.

### Setup

**1. Install bundling dependencies:**
```bash
npm install --save-dev rollup @rollup/plugin-node-resolve @rollup/plugin-commonjs
```

**2. Bundle configuration:**
- File: `rollup.codemirror.config.mjs`
- Input: `frontend/codemirror-bundle.js` (exports all needed CodeMirror modules)
- Output: `static/js/dist/codemirror-bundle.js`

**3. Build the bundle:**
```bash
npx rollup -c rollup.codemirror.config.mjs
```

### Import Map Configuration

Instead of mapping 15+ CodeMirror packages individually:
```html
<script type="importmap">
{
  "imports": {
    "./codemirror-bundle.js": "{% static 'js/dist/codemirror-bundle.js' %}"
  }
}
</script>
```

### Component Usage

CodeMirrorEditor.ts imports everything from the bundle:
```typescript
import { EditorView, basicSetup, EditorState, sql } from './codemirror-bundle.js';
```

### Rebuilding the Bundle

When updating CodeMirror or adding new language support:

1. **Update the bundle source** (`frontend/codemirror-bundle.js`):
   ```javascript
   export { EditorView, basicSetup } from 'codemirror';
   export { EditorState } from '@codemirror/state';
   export { sql } from '@codemirror/lang-sql';
   export { javascript } from '@codemirror/lang-javascript'; // New language
   ```

2. **Rebuild the bundle:**
   ```bash
   npx rollup -c rollup.codemirror.config.mjs
   ```

3. **No import map changes needed** - the bundle handles all dependencies internally.

### Benefits

- ✅ **Single HTTP request** instead of 15+ requests
- ✅ **No dependency errors** - everything bundled together  
- ✅ **Simple import map** - just one entry
- ✅ **Production ready** - optimized bundle
- ✅ **Easy maintenance** - update bundle source and rebuild

## End-to-End Testing (pytest + Playwright)

### Install (browser binaries)

   ```bash
   pip install -r requirements.txt
   python -m playwright install
   ```

### Configuration

`pytest.ini` sets up Django and enables headed + slow motion by default:

### Run tests

```bash
# Run all tests (headed + slowmo per pytest.ini)
pytest

# Run a single file
pytest tests/e2e/test_smoke.py -q

# Useful flags
pytest --browser=chromium            # or: firefox, webkit
pytest --video=on --screenshot=only-on-failure --tracing=on
```

### Watch the browser / debug

- Step-through with Inspector:
  - Add `page.pause()` in a test
  - Run:
    ```bash
    PWDEBUG=1 pytest --headed
    ```
- Slow actions for visibility: `--slowmo=200`

### Notes

- Tests run against a temporary Django test database; data is isolated per run.
- `live_server` serves the app during tests; you don’t need `runserver`.
- TypeScript auto-recompiles via `npm run watch` if needed for UI behavior.

