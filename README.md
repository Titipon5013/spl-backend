# spl-backend

This is the backend for the Smart Parking Lot application, built with FastAPI. It provides a robust API for managing parking spaces, users, authentication, and real-time updates through MQTT.

## Features

- **Real-time Parking Monitoring**: Integrates with an MQTT broker to receive live data from parking sensors, allowing for immediate updates on parking space occupancy.
- **User and Admin Management**: Complete CRUD (Create, Read, Update, Delete) operations for both regular users and administrators.
- **Secure Authentication**: Implements JWT (JSON Web Tokens) for securing API endpoints, ensuring that only authorized users can access protected routes.
- **User Registration Workflow**: A comprehensive registration process where users can sign up, upload necessary identification documents to an AWS S3 bucket, and await approval from an administrator.
- **Parking Space Management**: Full control over parking spaces, including tracking their history to monitor usage patterns over time.
- **License Plate Management**: Functionality to add, view, and manage user license plates, linking them to specific user accounts.
- **Database Migrations**: Utilizes Alembic to handle database schema migrations, making it easy to evolve the data model over time.
- **MCP Server (Feature 2)**: Exposes live and historical parking data as Model Context Protocol tools for AI agents, over stdio (Claude Desktop) and HTTP at `/mcp`. Includes automatic detection of stuck slots, pipeline outages and offline devices. See [docs/feature2-mcp-server.md](docs/feature2-mcp-server.md).
- **Admin LINE Bot (Feature 4)**: Separate admin LINE channel for linked operators. Queries go through the Feature 2 MCP client; anomaly pushes use subscription + delivery dedupe. See [docs/feature4-admin-line.md](docs/feature4-admin-line.md).
- **Windows local testing**: [docs/windows-local-test-guide.md](docs/windows-local-test-guide.md) — pull `dev`, run MCP + admin LINE with ngrok.

## Technologies Used

- **Python**: The core programming language.
- **FastAPI**: A modern, high-performance web framework for building APIs.
- **SQLAlchemy**: A powerful SQL toolkit and Object-Relational Mapper (ORM) for database interactions.
- **PostgreSQL**: The relational database used for data storage.
- **Alembic**: A lightweight database migration tool for SQLAlchemy.
- **Paho-MQTT**: The client library for connecting to the MQTT broker.
- **Docker**: For containerizing the application and its services.
- **AWS S3**: For storing user-uploaded files like identification documents.

## API Endpoints

The following are the primary API endpoints provided by the backend:

- `/api/auth/token`: Handles user login and the generation of access tokens.
- `/api/admins`: For managing administrator accounts.
- `/api/register`: The endpoint for new user registrations.
- `/api/requests`: Allows administrators to manage user registration requests (approve or deny).
- `/api/parking-spaces`: For managing parking spaces and their real-time status.
- `/api/plates`: For managing user license plates.
- `/mcp/`: The MCP server endpoint for AI agents. Requires a bearer token from `MCP_API_TOKENS`.
- `/webhook/line/admin`: Admin LINE webhook (Feature 4). Requires `ADMIN_LINE_*` and a linked subscription for queries.
- `/webhook/line/user`: Commuter LINE webhook (Feature 6).

## Setup and Installation

### Prerequisites

- Python 3.9 or higher
- An active AWS S3 bucket with corresponding credentials
- Docker and Docker Compose installed

### Installation Steps

1.  **Navigate to the backend directory**:
    ```bash
    cd spl-backend
    ```

2.  **Create and activate a virtual environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install the required dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure your environment variables**:
    - Make a copy of the example `.env` file: `cp .env.example .env`
    - Open the `.env` file and fill in your specific details for the database connection, JWT secret key, AWS credentials, and MQTT broker.

5.  **Apply database migrations**:
    ```bash
    alembic upgrade head
    ```

6.  **Run the application**:
    ```bash
    uvicorn main:app --reload
    ```

The backend server will now be running and accessible at `http://localhost:8000`.

### Simulate Camera Ingestion Locally

Use this when the Orange Pi / camera detector is not available but you want to
prove that dashboard data is persisted through the real ingestion API.

```bash
python scripts/simulate_camera_events.py --api-url http://127.0.0.1:8000 --count 5 --interval 5
```

The simulator sends:

- `POST /api/analytics/heartbeat`
- `POST /api/analytics/camera/events`

Use `--dry-run` to print payloads without sending them.

## Running the Backend with Docker

Use this section when running the backend container locally against PostgreSQL on your machine.

### 1. Build the backend image

```bash
docker build -t spl-backend:local .
```

### 2. Configure `.env`

The app reads database settings from `DATABASE_URL`.

Linux local PostgreSQL:

```env
DATABASE_URL=postgresql+psycopg2://postgres:<password>@127.0.0.1:5432/smartparkinglot
```

Windows Docker Desktop local PostgreSQL:

```env
DATABASE_URL=postgresql+psycopg2://postgres:<password>@host.docker.internal:5432/smartparkinglot
```

If your PostgreSQL uses a different exposed port, replace `5432` with that port.

### 3. Run on Linux

When PostgreSQL is running directly on Linux and only listens on localhost, run the backend container with host networking:

```bash
docker rm -f spl-backend 2>/dev/null || true
docker run --rm -d --name spl-backend --network host --env-file .env spl-backend:local
```

The API will be available at:

```text
http://127.0.0.1:8000
```

### 4. Run on Windows

On Windows Docker Desktop, keep normal port publishing and use `host.docker.internal` in `DATABASE_URL`:

```powershell
docker rm -f spl-backend
docker run --rm -d --name spl-backend --env-file .env -p 8000:8000 spl-backend:local
```

The API will be available at:

```text
http://127.0.0.1:8000
```

### 5. Verify the backend

Open the docs:

```bash
curl http://127.0.0.1:8000/docs
```

Test login with the seeded admin account:

```bash
curl -X POST http://127.0.0.1:8000/api/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=<SEED_EMAIL>" \
  --data-urlencode "password=<SEED_PASSWORD>"
```

Expected result: HTTP `200 OK` with an `access_token`.

## Notes for Windows `.env` Files

If your `.env` came from a Windows machine, Linux may not run with the same `DATABASE_URL`.

- Windows Docker Desktop can usually use `host.docker.internal`.
- Linux Docker often cannot resolve `host.docker.internal` unless it is configured manually.
- If PostgreSQL runs on the Linux host and listens only on `127.0.0.1`, use `DATABASE_URL=...@127.0.0.1:5432/...` and run the backend with `--network host`.
- If PostgreSQL runs in another Docker container, do not use `127.0.0.1`; put both containers on the same Docker network and use the PostgreSQL container/service name as the host.
- `SEED_EMAIL`, `SEED_USERNAME`, and `SEED_PASSWORD` are credentials used for the admin account, but this codebase does not automatically create that admin row on startup. The `admins` table must already contain that email with a bcrypt-hashed password.

For the current local Linux setup, the working combination is:

```env
DATABASE_URL=postgresql+psycopg2://postgres:<password>@127.0.0.1:5432/smartparkinglot
```

```bash
docker run --rm -d --name spl-backend --network host --env-file .env spl-backend:local
```
