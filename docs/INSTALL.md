# Installing Steacher

## Prerequisites

Install Python 3.12, Node.js 20, and Docker with the Compose plugin.
On Windows, use Docker Desktop with Linux containers.

## Local installation

### 1. Get the project

```bash
git clone https://github.com/ISC-HEI/steacher.git
cd steacher
```

### 2. Configure the environment

Create a `.env` file in `steacher_app/`, beside `manage.py`:

```ini
POSTGRES_DB=steacher
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
OPENAI_API_KEY=your_openai_api_key
GEMINI_API_KEY=your_gemini_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
REDIS_URL=redis://127.0.0.1:6379/0
```

Use the same database password here and in the Docker command below.
`postgres` is an example password for local development.
`GEMINI_API_KEY` is required for tutoring. `OPENAI_API_KEY` is reserved in
settings, and `OPENROUTER_API_KEY` is optional for model evaluation.
The local setup uses Django's development defaults.

### 3. Start PostgreSQL and Redis

Run once to create the containers:

```bash
docker run --name my-local-postgres -e POSTGRES_PASSWORD=postgres -p 127.0.0.1:5432:5432 -d postgres:17
docker run --name my-local-redis -p 127.0.0.1:6379:6379 -d redis:7-alpine
```

Once PostgreSQL is ready, create the database:

```bash
docker exec -i my-local-postgres psql -U postgres -c "CREATE DATABASE steacher;"
```

For later sessions, start the existing containers:

```bash
docker start my-local-postgres my-local-redis
```

### 4. Install Python dependencies

```bash
cd steacher_app
python -m venv .venv
```

Activate the environment in your terminal:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS / WSL
source .venv/bin/activate
```

Then install the dependencies and create the log directory:

```bash
python -m pip install -r requirements.txt
mkdir logs
```

The log directory is `steacher_app/logs`, beside `manage.py`.

### 5. Build the frontend

In a separate terminal, from `steacher_app/`:

```bash
npm install
npm run watch
```

Leave `npm run watch` running while developing. Install dependencies once,
and again when the project's dependencies change.

### 6. Prepare the database and start Django

In the terminal with the Python environment active, from `steacher_app/`:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Create the superuser once per database. Open `http://127.0.0.1:8000/` for the
platform and `http://127.0.0.1:8000/admin/` for administration.

For subsequent sessions, start PostgreSQL and Redis, activate the Python
environment, and run `npm run watch` and `python manage.py runserver` in
separate terminals.

### Optional: Scala exercises

For Django running locally, run these commands from the repository root:

```bash
docker build --build-arg BUILD_PLATFORM=linux/amd64 -t steacher-scala ./scala_interpreter
docker run -d --name steacher-scala -p 127.0.0.1:8642:8642 --memory 1g --cpus 1 --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges steacher-scala
```

Django uses `SCALA_INTERPRETER_URL=http://localhost:8642` by default.
For later sessions, use `docker start steacher-scala`.

When Django runs inside the production Compose stack, start Scala with
`docker compose up -d scala_interpreter`; that service is reachable on the
internal Docker network.

### Optional: live quizzes and voice input

For live quiz WebSockets, start Django with ASGI in the Python terminal:

```bash
uvicorn exam_project.asgi:application --host 127.0.0.1 --port 8000 --reload
```

Mobile voice transcription uses `GROQ_API_KEY`, which you can add to `.env`.

## First steps after installing

In the Django admin, create a course, module, and exercise. Assign
`CourseMembership` roles (`owner` or `editor`) to authors and
`CohortMembership` roles to teachers and students. Assign these memberships
to administrator accounts as well when using the course interfaces.

See the [teacher guide](Teachers.md), [student guide](Students.md), and
[prompt configuration](PROMPTS.md) for classroom use.
Sample material is available in [import_tools/samples](../import_tools/samples).

## Verifying the installation

Log in, open a Python exercise as an enrolled student, run a short program,
and request a hint. Check that the reply and interaction trace appear.
Allow the browser to finish loading its Python runtime before the first run.

From `steacher_app/`, with the Python environment active:

```bash
python -m pytest --ds=exam_project.settings exercises/tests tests/test_mailtrap_backend.py evaluation/tests.py
```

Database tests require PostgreSQL and permission to create the test database.
For live quizzes, also verify a session with the ASGI server running.

## What you will be running

Django serves the application, PostgreSQL stores persistent data, and Redis
supports quiz state and WebSockets. Python, SQL, and turtle run in the browser;
Scala runs in its interpreter service.

Python exercises with unit tests also execute submissions in a child process
with the application's permissions. Configure execution isolation when
accepting untrusted code. See [API.md](API.md#websocket) for quiz connection
access.

## Production installation

Use the [deployment guide](../DEPLOY.md) for VM provisioning, DNS, backups,
and operations. Production uses the repository's Docker Compose stack with
Nginx, PostgreSQL, Redis, Scala, and optional Metabase.

1. Create `.env.production` in the repository root using the database and
   provider variable names above. Set `POSTGRES_HOST=db`,
   `REDIS_URL=redis://redis:6379/0`, a strong database password,
   `DJANGO_DEBUG=False`, and a random `DJANGO_SECRET_KEY`.
2. Set `DJANGO_ALLOWED_HOSTS` to your domain,
   `DJANGO_CSRF_TRUSTED_ORIGINS` to its HTTPS origin, and
   `DJANGO_SECURE_SSL_REDIRECT=True`. Update the domain and certificate paths
   in `nginx/nginx.conf`, and `DOMAIN` and `EMAIL` in `init-letsencrypt.sh`.
3. From the repository root, create `logs` and start the application services:

```bash
mkdir logs
docker compose build
docker compose up -d db redis scala_interpreter web
```

Once PostgreSQL is healthy (`docker compose ps`), initialize Django:

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py createsuperuser
```

For first-time TLS issuance, run `./init-letsencrypt.sh` in Bash. The script
starts the proxy with a temporary certificate and obtains the real one.
If certificate data already exists, it offers to delete and replace it.
Schedule renewal from the repository root with a host cron job or timer:

```bash
docker compose run --rm certbot renew --quiet && docker compose restart proxy
```

Keep environment files containing credentials outside version control.
For email delivery, configure `EMAIL_BACKEND` and `DEFAULT_FROM_EMAIL`;
the Mailtrap backend additionally uses `MAILTRAP_API_KEY`. Set `MAIL_DOMAIN`
to your domain for mobile login links. For analytics setup, see
[bi/README.md](../bi/README.md).

## Troubleshooting

- **Logs:** check that `steacher_app/logs` exists beside `manage.py`.
- **Frontend:** check the output of `npm run watch`; in production, build the
  web image and run `collectstatic`.
- **Tutor:** check `GEMINI_API_KEY` and the application logs.
- **Database:** check that the container is running and its password matches
  `.env`.
- **Scala:** check `docker logs steacher-scala` and the published port `8642`.
