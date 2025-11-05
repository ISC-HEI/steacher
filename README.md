# Steacher

FIXME work this out with Sébastien

**Steacher** is a web-based educational platform designed to help users learn and practice various subjects through interactive exercises. It features a Django backend, a PostgreSQL database, and a modern frontend built with TypeScript and Vue.js. The platform supports different types of exercises, including multiple-choice, SQL, and Python, and leverages the OpenAI API to provide AI-powered guidance and feedback to users.

## Development

### Config

Create a `.env` file in the `steacher_app` root with the following variables:
```
POSTGRES_DB=steacher
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres  # change this to a secure password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
OPENAI_API_KEY=your_openai_api_key
GEMINI_API_KEY=your_gemini_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
```

### Start Database in Docker

set "[password]" and use command below

```bash
docker run --name my-local-postgres -e POSTGRES_PASSWORD=[password] -p 5432:5432 -d postgres
```

### Refresh js files

Run in a separate terminal from the `steacher_app` root.

(one time)
```bash
npm install
```

```bash
npm run watch
```


### Run migrations

```bash
python manage.py migrate
```


### Create the database

```bash
docker exec -i my-local-postgres psql -U postgres -c "CREATE DATABASE steacher;"
```

### Create a superuser

One time setup, unless you wipe out the database.

```bash
python manage.py createsuperuser
```


### Start the Web Server

Run in a separate terminal from the `steacher_app` root.

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` to see the homepage.

Visit `http://127.0.0.1:8000/admin` once logged in to create exercices.

Optionally, run the following command to start scala interpreter server.
```bash
docker compose up -d scala_interpreter
```


