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
