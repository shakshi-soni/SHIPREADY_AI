# Project Application

This is a Python-based web service designed to run containerized workloads.

## Setup
To set up the project locally, install the dependencies:
```bash
pip install -r requirements.txt
```

## Usage
To run the application locally:
```bash
uvicorn main:app --host 127.0.0.1 --port 8080
```

## Architecture
The application uses FastAPI to serve HTTP requests, including a `/health` endpoint. It is containerized using Docker and deployed to Google Cloud Run.