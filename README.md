# CertiGuard — AI-Powered Certificate Verification System

CertiGuard is an AI-powered certificate verification platform designed to help identify potentially fraudulent certificates through machine learning, certificate data analysis, and a streamlined verification workflow.

The project combines a **FastAPI backend**, a **React + TypeScript frontend**, and a machine learning model to evaluate certificate information and return verification results. Docker Compose makes it easier to run the frontend and backend together.

---

## ✨ Features

- **AI-Powered Verification:** Uses a trained machine learning model to analyze certificate features and predict potential fraud.
- **Certificate Management:** Supports certificate submission and verification workflows.
- **Verification Results:** Displays prediction results and relevant verification information.
- **Audit Logging:** Records application events for traceability.
- **Modern Web Interface:** Responsive frontend built with React, TypeScript, and Vite.
- **REST API:** FastAPI backend exposes endpoints for application functionality.
- **Containerized Deployment:** Docker and Docker Compose simplify local setup and execution.
- **Persistent Storage:** SQLite database, uploaded files, and monitoring logs can persist across container restarts.
- **Health Monitoring:** Health endpoints help confirm that the application and model are running.
- **Nginx Reverse Proxy:** Routes frontend traffic and API requests to the appropriate service.

---

## 🏗️ Technology Stack

### Frontend
- React
- TypeScript
- Vite
- Nginx

### Backend
- Python
- FastAPI
- SQLAlchemy
- SQLite

### Machine Learning
- Scikit-learn
- Random Forest classifier
- Model version: `random_forest_v3`
- 31 model features

### Deployment and Development
- Docker
- Docker Compose
- Git and GitHub

---

## 🧱 Architecture

CertiGuard uses a containerized, two-service architecture.

```text
                   User / Browser
                         |
                         v
                http://localhost:8080
                         |
                         v
                +------------------+
                | Frontend         |
                | React + Vite     |
                | Nginx            |
                +------------------+
                         |
                         | /api/* requests
                         v
                +------------------+
                | Backend          |
                | FastAPI          |
                | Machine Learning |
                +------------------+
                    |          |
                    v          v
                SQLite DB   Uploads /
                            Logs
```

### Services

| Service | Technology | Local URL |
|---|---|---|
| Frontend | React, TypeScript, Nginx | `http://localhost:8080` |
| Backend | FastAPI, Python | `http://localhost:8000` |
| API Documentation | FastAPI Swagger UI | `http://localhost:8000/docs` |
| API Health | FastAPI | `http://localhost:8000/api/health` |

The frontend uses Nginx to serve the built React application and proxy `/api/` requests to the backend over the Docker Compose network.

---

## 🚀 Getting Started with Docker

### Prerequisites

Install the following tools:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Git
- A modern web browser

Ensure Docker Desktop is running before starting the application.

### 1. Clone the Repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd CertiGuard
```

Replace `<YOUR_GITHUB_REPOSITORY_URL>` with your repository's actual Git URL.

### 2. Configure Environment Variables

Review the environment variables required by the backend and frontend.

If the application uses Clerk authentication, configure the appropriate Clerk keys and authentication settings according to the project's existing environment configuration.

**Important:** Never commit `.env` files, API keys, authentication secrets, or private credentials to GitHub.

### 3. Build and Start the Application

Run the following command from the project root:

```bash
docker compose up --build -d
```

Docker Compose builds the frontend and backend images and starts both services.

### 4. Check the Running Containers

```bash
docker compose ps
```

View the application logs:

```bash
docker compose logs -f
```

View only backend logs:

```bash
docker compose logs -f backend
```

View only frontend logs:

```bash
docker compose logs -f frontend
```

### 5. Open the Application

After the containers start, open:

- **Frontend:** http://localhost:8080
- **Backend API:** http://localhost:8000
- **Swagger API Documentation:** http://localhost:8000/docs

### 6. Verify Application Health

Check the backend through the frontend's Nginx proxy:

```bash
curl http://localhost:8080/api/health
```

You can also check the backend directly:

```bash
curl http://localhost:8000/api/health
```

A successful health response should indicate that the application is running and report the model status.

The exact response may vary depending on the backend implementation and configuration.

---

## 🐳 Docker Commands

### Start the Application

```bash
docker compose up -d
```

### Rebuild and Start

Use this after making changes that need to be included in the container images:

```bash
docker compose up --build -d
```

### Stop the Application

```bash
docker compose down
```

This stops and removes the Compose containers and network without explicitly deleting named volumes.

**Avoid `docker compose down -v` unless you deliberately intend to remove the Compose-managed volumes.**

### Restart Services

```bash
docker compose restart
```

### Check Container Status

```bash
docker compose ps
```

### View Logs

```bash
docker compose logs -f
```

### Stop Viewing Logs

Press `Ctrl+C`. This stops following the logs; it does not stop the containers.

---

## 💾 Data Persistence

CertiGuard uses persistent storage for application data.

| Data | Storage |
|---|---|
| Certificate and verification records | SQLite database bind-mounted from the host |
| Uploaded files | Docker named volume |
| Monitoring logs | Docker named volume |

The SQLite database is configured at:

```text
/app/db/certificates.db
```

In the development setup, the database is mapped to:

```text
backend/certificates.db
```

The actual database location depends on the Compose configuration.

### Important Notes

- Keep the SQLite database file safe.
- Back up important data before making database or deployment changes.
- Stopping and recreating containers is different from deleting persistent volumes.
- Do not delete Docker volumes or database files unless you understand their contents and have confirmed that a backup is available.
- Runtime database files should not be committed to GitHub.

---

## 💻 Running Locally Without Docker

You can also run the frontend and backend separately for development.

### Backend Setup

Navigate to the backend directory:

```bash
cd backend
```

Create and activate a Python virtual environment.

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the project's dependencies using the dependency file provided in the repository. For example, if the project contains `requirements.txt`:

```bash
pip install -r requirements.txt
```

Start the FastAPI application using the module and entry point configured in the project.

For example, if the entry point is `main.py`:

```bash
uvicorn main:app --reload --port 8000
```

Backend setup commands may need adjustment if the repository uses a different entry point or dependency manager.

### Frontend Setup

Open another terminal and navigate to the frontend directory:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

Use the local URL printed by Vite in the terminal.

**Note:** Local development may require different API and authentication environment variables from the Docker deployment.

---

## 🔐 Authentication and Configuration

CertiGuard may use Clerk for authentication, depending on the configured application environment.

Before running the application, review the existing environment configuration and ensure that the required keys are available to the appropriate service.

Typical Clerk configuration may include:

- A publishable key for the frontend.
- A secret key for backend authentication verification, if required.
- Any application-specific authentication settings.

Use the actual environment variable names expected by the codebase.

### Security Best Practices

- Never commit secret keys or credentials.
- Keep local environment files out of version control.
- Do not expose backend secret keys to frontend code.
- Validate uploaded files on the server.
- Restrict access to certificate records and uploaded documents.
- Review authentication and authorization before deploying publicly.

---

## 📡 API and Health Checks

The backend is built with FastAPI and exposes REST API endpoints.

### Health Endpoint

```http
GET /api/health
```

This endpoint reports the application's health and model-loading status.

Example request:

```bash
curl http://localhost:8000/api/health
```

### Model Information

```http
GET /api/model/info
```

This endpoint provides information about the loaded machine learning model, subject to the current backend implementation.

Example request:

```bash
curl http://localhost:8000/api/model/info
```

### Interactive API Documentation

Open the following URL while the backend is running:

http://localhost:8000/docs

The Swagger interface displays the API endpoints and allows you to inspect their parameters, request formats, and responses.

For the complete API contract, refer to the FastAPI routes implemented in the backend.

---

## 🧪 Testing

Run tests using the commands and dependency configuration defined in the project.

### Backend Tests

From the backend directory, activate the project's Python environment and run:

```bash
pytest
```

### Frontend Tests

From the frontend directory:

```bash
npm test
```

### Frontend Type Checking

```bash
npm run typecheck
```

Use the actual scripts defined in `frontend/package.json` if they differ.

### Docker Verification Checklist

After building and starting the application, verify:

- [ ] Both containers start successfully.
- [ ] The frontend loads in a browser.
- [ ] The backend health endpoint responds successfully.
- [ ] The model loads correctly.
- [ ] API requests are routed through Nginx.
- [ ] Frontend navigation and deep links work.
- [ ] Authentication works in the configured environment.
- [ ] Certificate submission and verification work.
- [ ] Persistent data remains available after a normal container restart.

---

## 🛡️ Privacy and Security

Certificate verification can involve sensitive personal and educational information.

CertiGuard should be used with appropriate safeguards:

- Protect uploaded documents and certificate records.
- Apply authentication and authorization to sensitive operations.
- Avoid logging unnecessary personal information.
- Keep credentials and secrets out of source control.
- Back up persistent data securely.
- Validate files and request data before processing.
- Review deployment settings before exposing the application to the internet.

The machine learning output should be treated as an assessment to support verification, not as definitive proof that a certificate is genuine or fraudulent.

---

## ⚠️ Limitations

- Machine learning predictions depend on the quality and representativeness of the training data.
- Predictions may contain false positives and false negatives.
- Model performance on unseen certificates may differ from historical evaluation results.
- Database persistence and uploaded-file storage depend on the deployment configuration.
- Authentication behavior depends on the configured identity provider and environment variables.
- The application should not replace independent verification with the issuing institution.

---

## 🔮 Future Improvements

Potential future enhancements include:

- OCR-based certificate data extraction.
- QR code and digital-signature verification.
- Integration with official certificate issuers.
- Improved model explainability.
- Expanded evaluation datasets and monitoring.
- Role-based access control.
- Production deployment and automated CI/CD.
- More comprehensive integration and security testing.

---

## 🤝 Contributing

Contributions, bug reports, and suggestions are welcome.

To contribute:

1. Fork the repository.
2. Create a feature branch.
3. Make your changes.
4. Run the relevant tests.
5. Commit your changes with a clear message.
6. Open a pull request describing the changes.

Please avoid committing credentials, generated artifacts, local databases, or private certificate data.

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## ⚖️ Disclaimer

CertiGuard is an educational and technical project intended to assist certificate verification. Its machine learning predictions are not a substitute for confirmation from the relevant issuing institution. The developers do not guarantee that every certificate will be classified correctly.

---

**Built with Python, FastAPI, React, TypeScript, scikit-learn, and Docker.**
