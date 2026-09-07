# Steacher — ELITE

[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/code-MIT-green)](LICENSE)
[![Documentation: CC BY 4.0](https://img.shields.io/badge/docs-CC_BY_4.0-lightgrey)](LICENSE-DOCS)

**Empowering Learning through Co-Designed LLM Mediation**

HES-SO R&I project **ELITE, 140090/RI-PSTRAT25-05**

[Project website](https://elite.histlab.hevs.ch/) · [Hosted platform](https://steacher.org/)

Steacher is the learning platform developed within ELITE. It helps students
work through programming and mathematics exercises with an AI tutor configured
by their educators. The default tutor is instructed to acknowledge correct
steps, identify difficulties, and ask guiding questions that support reflection
and independent problem solving.

This repository contains the platform, reusable prompt templates, sample
classroom material, and technical documentation. Access to the hosted platform
is by invitation; a self-hosted installation starts with your own accounts and
course content.

## What it does

- Organizes courses, modules, exercises, and cohorts, with separate student
  and educator interfaces and permissions.
- Supports Python, SQL, turtle graphics, Scala, and open questions, including
  photographs of handwritten work.
- Provides contextual tutoring, hints, and a solution-reveal action unlocked
  after five recorded code or answer submissions. Socratic guidance is a prompt
  policy; the application enforces the reveal threshold.
- Lets educators configure course and exercise-type instructions, author or
  translate exercises with AI assistance, and import or export modules.
- Records interaction traces and feedback, and provides educator analytics,
  live quizzes, and a mobile companion interface.

See the [teacher guide](docs/Teachers.md) and [student guide](docs/Students.md)
for classroom workflows, and [Prompt schema and answer policy](docs/PROMPTS.md)
for the tutoring approach and course configuration.

## Requirements

- Python 3.12 and Node.js 20 for local development, matching the Docker build.
- PostgreSQL 17 and Redis 7; Docker can provide both locally.
- A Gemini API key and network access to the model provider for tutoring and
  authoring. Mobile voice transcription additionally needs a Groq API key.
- A modern browser with WebAssembly support for Python, SQL, and turtle.
  Scala uses a separate interpreter service.

Production uses Docker Compose on a Linux host with a domain and HTTPS.
See [Installation](docs/INSTALL.md#what-you-will-be-running) for the service
architecture and deployment configuration.

## Installation

```bash
git clone https://github.com/ISC-HEI/steacher.git
cd steacher
```

Follow [Local installation](docs/INSTALL.md#local-installation) to create
`steacher_app/.env`, start PostgreSQL and Redis, install dependencies, and
create the database and administrator. Then, from `steacher_app/`, use two
terminals:

```bash
# Frontend terminal
npm run watch
```

```bash
# Python terminal, with the virtual environment active
python manage.py runserver
```

Open `http://127.0.0.1:8000/`; administration is at
`http://127.0.0.1:8000/admin/`.

For a hosted deployment, follow
[Production installation](docs/INSTALL.md#production-installation), including
domain configuration, initial certificate issuance, and scheduled renewal.
The supplied Compose configuration builds the application from source.

## Documentation

| Guide | Contents |
| --- | --- |
| [Installation](docs/INSTALL.md) | Requirements, local and production setup, configuration, verification, and troubleshooting |
| [API](docs/API.md) | Internal HTTP routes, authentication, payloads, WebSockets, and permissions |
| [Prompt schema and answer policy](docs/PROMPTS.md) | Prompt composition, course configuration, response schemas, and reflection mechanisms |
| [Teacher guide](docs/Teachers.md) | Course preparation and educator workflows |
| [Student guide](docs/Students.md) | Exercises and interaction with the tutor |
| [Operations](DEPLOY.md) | VM provisioning, deployment, backups, and TLS operations |

## Development

The application uses Django, PostgreSQL, Redis, and Vue components mounted on
server-rendered pages. Application code and frontend sources live in
`steacher_app/`; the Scala execution service is in `scala_interpreter/`.
`import_tools/samples/` contains reusable classroom material.

After completing local installation, run the non-browser tests from
`steacher_app/` with the virtual environment active:

```bash
python -m pytest --ds=exam_project.settings exercises/tests tests/test_mailtrap_backend.py evaluation/tests.py
```

Database tests need a reachable PostgreSQL server and a user allowed to create
the test database. Browser tests require additional setup and exercise the live
model integration; see [Verification](docs/INSTALL.md#verifying-the-installation).
For frontend development, keep `npm run watch` running in a separate terminal.

## Project and licensing

Developed at **HES-SO Valais-Wallis, Haute École d'Ingénierie**, within
**ELITE — Co-concevoir une médiation IA pour renforcer les apprentissages en
programmation (140090/RI-PSTRAT25-05)**. The platform and these guides support
the open-source framework deliverable (D2). See the
[project website](https://elite.histlab.hevs.ch/) for project information.

| Material | License |
| --- | --- |
| Source code | [MIT](LICENSE) |
| Documentation, instructional prompt templates, and sample classroom material | [CC BY 4.0](LICENSE-DOCS) |

The license files define their scope; third-party materials retain their own
licenses. Copyright 2026 HES-SO Valais-Wallis.
