# CertiGuard

### AI-Powered Certificate Verification & Fraud Detection

CertiGuard is an AI-assisted certificate analysis platform that examines uploaded documents for potential inconsistencies and suspicious characteristics. It combines document processing, machine-learning inference, forensic and consistency checks, and evidence aggregation to help users review certificates.

> **Important:** CertiGuard provides decision support, not an official determination of authenticity. A model prediction or forensic indicator is not proof of fraud, and a favorable result is not proof that a certificate is genuine. Where necessary, confirm certificates directly with the issuing institution.

---

## Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Objectives](#objectives)
- [Features](#features)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Machine Learning](#machine-learning)
- [Issuer Verification](#issuer-verification)
- [Audit Trail and Records](#audit-trail-and-records)
- [Technology Stack](#technology-stack)
- [Repository Layout](#repository-layout)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Data and Evaluation](#data-and-evaluation)
- [Testing](#testing)
- [Security and Privacy](#security-and-privacy)
- [Limitations](#limitations)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Overview

Digital certificates are used to represent educational qualifications, professional achievements, and training completion. Manually reviewing certificates can take time, particularly when documents come from different issuers or use different formats.

CertiGuard is intended to assist with the initial review by extracting document information, analyzing a range of signals, and presenting a structured assessment for human review.

## Problem Statement

Manual certificate review can be difficult to scale and may require reviewers to inspect document content, formatting, and other characteristics individually. CertiGuard aims to organize parts of this process into a repeatable analysis workflow while making clear that automated analysis cannot replace official issuer confirmation.

## Objectives

- Automate initial certificate document analysis.
- Extract information from supported documents.
- Identify potential inconsistencies and suspicious characteristics.
- Combine machine-learning output with additional analysis signals.
- Present structured information to support human review.
- Maintain traceability through verification records and audit events.
- Provide a foundation for evaluation and improvement using appropriately labeled data.

## Features

### Document processing

- PDF text extraction.
- OCR fallback where required by the document-processing workflow.
- Preparation of extracted information for downstream analysis.

### Machine-learning analysis

- Random Forest classifier for certificate assessment.
- A 31-feature model input schema.
- Model inference used as one signal within the broader workflow.

### Consistency and forensic checks

The analysis pipeline includes consistency/intelligence, forensic, visual, and potential tampering checks. The interpretation of each signal should account for uncertainty and possible false positives.

### Evidence aggregation

Available analysis outputs are combined into a structured assessment. Model output, issuer-verification status, and other document signals should be understood as distinct sources of evidence.

### Issuer-verification status handling

The system defines the following issuer-verification statuses:

| Status | Meaning |
|---|---|
| `VERIFIED_BY_ISSUER` | The issuer-verification process reports successful verification. |
| `NOT_VERIFIED` | The issuer-verification process did not verify the certificate. |
| `VERIFICATION_UNAVAILABLE` | The issuer-verification process could not be completed. |
| `ISSUER_UNKNOWN` | The issuer could not be identified or matched to a supported issuer. |

These statuses describe the issuer-verification layer; they are not interchangeable with the model's prediction. An unknown issuer or unavailable service must not automatically be interpreted as fraud.

### Verification records and audit events

The backend includes verification persistence and audit-event functionality. The documented audit route is:

```http
GET /api/verifications/{id}/audit
```

Confirm the route and its access controls in the running application before relying on it.

## How It Works

The intended high-level workflow is:

1. **Upload** a certificate document.
2. **Extract text** from the document, using OCR when necessary.
3. **Generate features** in the format expected by the model.
4. **Run model inference** using the configured classifier.
5. **Perform additional analysis**, including applicable consistency, forensic, visual, and tampering checks.
6. **Handle issuer verification**, when an issuer-verification service is available.
7. **Aggregate evidence** from the available analysis stages.
8. **Present an assessment** for human review.
9. **Record verification activity** and applicable audit events.

Actual processing and availability depend on the current code and runtime configuration.

## Architecture

```text
┌─────────────────────────┐
│ React + TypeScript UI   │
└────────────┬────────────┘
             │ HTTP/API
             ▼
┌─────────────────────────┐
│ FastAPI backend          │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│ PDF text extraction/OCR │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│ Feature generation      │
│ 31-feature model schema │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│ ML and document checks  │
│ Consistency/forensics   │
│ Visual/tampering signals│
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│ Evidence aggregation    │
│ Issuer status, if usable│
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│ Assessment and records  │
│ Audit events            │
└─────────────────────────┘
```

This is a conceptual overview, not a guarantee that every stage is enabled in every deployment.

## Machine Learning

### Documented model configuration

| Property | Configuration |
|---|---|
| Classifier | Random Forest |
| Model identifier | `random_forest_v3` |
| Artifact path | `models/artifacts/model.joblib` |
| Feature count | 31 |
| Decision threshold | `0.5` |

The model artifact, preprocessing steps, feature names and order, and threshold form a versioned interface. Changes should be evaluated before being promoted.

### Interpretation

A model prediction is probabilistic and may be wrong. Performance on synthetic or narrow evaluation data may not represent performance on documents from new institutions, formats, scanners, or regions. Results should be interpreted with the available supporting evidence and reviewed by a person.

## Issuer Verification

Issuer verification is conceptually separate from model inference and document analysis. In the documented development state, issuer-side verification endpoints were not configured for known issuers, so independent confirmation may be unavailable.

Do not interpret `ISSUER_UNKNOWN` or `VERIFICATION_UNAVAILABLE` as evidence that a certificate is fraudulent.

## Audit Trail and Records

The backend includes verification persistence and audit-event functionality. The documented audit endpoint is:

```http
GET /api/verifications/{id}/audit
```

Verify the current route definitions and authorization behavior in the codebase. Records and uploaded files may have separate lifecycles, so retention and deletion behavior should be explicitly reviewed before deployment.

## Technology Stack

| Area | Technology |
|---|---|
| Backend API | Python, FastAPI |
| Frontend | React, TypeScript |
| Machine learning | Scikit-learn Random Forest inference |
| Model serialization | Joblib |
| Document processing | PDF text extraction and OCR fallback |
| Testing | Backend automated tests; frontend type checking |

Refer to the repository's dependency files for exact versions and package-manager instructions.

## Repository Layout

The following is a **partial, illustrative** layout of documented modules. Use the actual checked-out repository as the source of truth; paths may vary.

```text
CertiGuard/
├── backend/
│   └── ...
├── frontend/
│   └── src/
│       └── ...
├── models/
│   └── artifacts/
│       └── model.joblib
├── data/
│   ├── real_dataset/
│   │   ├── genuine/
│   │   ├── suspicious/
│   │   └── uncertain/
│   └── processed/
├── README.md
└── LICENSE
```

The real-data tooling has included modules named `ingest.py`, `feature_alignment.py`, `schema_validation.py`, and `leakage.py` under `backend/src/real_data/`. Confirm their presence and invocation path in the current checkout.

## Getting Started

### Prerequisites

Install versions compatible with the repository's dependency files:

- Python
- Node.js
- npm or the package manager specified by the frontend
- Git

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd CertiGuard
```

Replace the URL and directory name with your repository's actual values.

### 2. Install backend dependencies

Create and activate a virtual environment from the appropriate backend directory.

**Windows PowerShell example:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies using the requirements or project file that actually exists in the backend:

```powershell
pip install -r requirements.txt
```

Run the installation command from the directory containing that file. If the project uses `pyproject.toml`, a lockfile, or another package manager, follow its documented workflow instead.

### 3. Configure the environment

Create the required local environment file(s) based on the project's configuration references or example files. Do not commit populated secrets or credentials.

### 4. Run the backend

Use the actual FastAPI application module and working directory from the repository. For example, if `main.py` is importable as `main`:

```bash
uvicorn main:app --reload --port 8000
```

This example assumes the module path is correct for your checkout. The local address is commonly `http://127.0.0.1:8000` when using this command.

### 5. Run the frontend

From the frontend directory:

```bash
npm install
npm run dev
```

Use the scripts and package manager declared by the frontend's `package.json`. Open the development URL printed in the terminal.

## Configuration

Configuration varies by environment. Review the current source and example environment files for required settings, which may include:

- Backend API URL.
- Database or persistence configuration.
- Model and inference settings.
- Issuer-verification settings.
- External-service credentials, if applicable.

A variable being set does not establish that its service is connected or working. Validate service health and responses before relying on it.

## API Reference

The documented audit route is:

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/verifications/{id}/audit` | Retrieve audit events for a verification record. |

For the complete API reference, inspect the current FastAPI route definitions. If enabled, FastAPI's interactive documentation is often available at:

```text
http://127.0.0.1:8000/docs
```

The URL above assumes the backend is running on port `8000` and exposes the standard documentation route.

## Data and Evaluation

The project has used synthetic training data and an external PDF validation set during development. Previously reported evaluation figures included:

| Metric | Historical reported value |
|---|---:|
| External validation accuracy | 0.963 |
| Genuine recall | 0.9286 |
| Suspicious recall | 1.0 |
| False positives reported | 1 |
| False negatives reported | 0 |

These are historical figures from development notes, not independently reproduced results in this README. They should not be presented as a guarantee of performance. The reported external set contained 27 PDFs and had limited representation of real certificates, which restricts conclusions about real-world generalization.

### Real-data ingestion

The documented ingestion workflow uses class folders such as:

```text
data/real_dataset/
├── genuine/
├── suspicious/
└── uncertain/
```

Its supporting modules include ingestion, feature alignment, schema validation, and leakage checks. Uncertain labels are intended to be excluded from supervised training.

A previously documented example invocation is:

```bash
python -m src.real_data.ingest --base-dir ./data/real_dataset
```

Run this only from a directory where the `src` package is importable, and verify the CLI options against the current implementation before use.

Before training or evaluating with real documents:

1. Ensure the documents were collected and may be used lawfully.
2. Use a documented, reliable labeling process.
3. Review generated features and schema-validation results.
4. Keep a separate, frozen evaluation set.
5. Check for duplicates and data leakage.
6. Evaluate performance across relevant document sources and classes.
7. Review results before considering any model or threshold change.

Successful ingestion does not itself validate a model or justify replacing the production artifact.

## Testing

Use the test and quality-check commands defined by the current repository.

Examples, if supported by the project:

```bash
pytest
```

```bash
npx tsc --noEmit
```

Historical development reports described different test checkpoints, so those counts are intentionally not stated as current results here. A passing test suite does not independently establish real-world model accuracy, issuer confirmation, or production readiness.

## Security and Privacy

Certificates can contain personal and confidential information. Before deploying CertiGuard:

- Require authentication and authorization for protected operations.
- Restrict access to uploaded files, verification history, and audit data.
- Keep secrets and credentials out of source control.
- Do not publish private certificates or datasets without a lawful basis and appropriate safeguards.
- Define retention and deletion policies for both files and database records.
- Validate file types, file sizes, and processing limits.
- Avoid leaking sensitive document contents through logs or error messages.
- Review dependency security and deployment configuration.
- Clearly communicate the limitations of automated results.

An earlier architecture review identified access control as a deployment concern. Reassess the current implementation before exposing the application to untrusted users.

## Limitations

The following points were identified during development and should be checked against the current version:

- **Real-world evaluation:** Synthetic data and a small external PDF set are insufficient to establish broad generalization.
- **Issuer integrations:** Issuer-side verification was not configured for known issuers in the documented state.
- **Data pipeline validation:** Real-data ingestion requires testing with appropriately labeled documents and review of its outputs.
- **Access control:** Authentication and authorization need to be verified before deployment.
- **Data lifecycle:** Uploaded files and database records may have different retention behavior.
- **Frontend experience:** Progress handling, cancellation, timeout behavior, and automated UI coverage were identified as improvement areas.
- **Operational readiness:** CI, dependency alignment, configuration validation, and deployment documentation should be reviewed.

These are historical development observations, not a claim that every item remains unresolved.

## Roadmap

Potential areas for future work:

- Expand the diverse, human-verified real-world certificate dataset.
- Maintain a frozen real-world evaluation set.
- Improve calibration and document the evaluation methodology.
- Add authorized issuer integrations where available.
- Strengthen authentication, authorization, and privacy controls.
- Improve retention and deletion workflows.
- Add robust upload limits and error handling.
- Improve progress reporting, cancellation, and timeout handling.
- Expand frontend automated tests.
- Add CI and dependency/security checks.
- Improve monitoring, auditability, and deployment documentation.

## Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a focused feature branch.
3. Make your changes.
4. Add or update tests where appropriate.
5. Run the relevant checks.
6. Submit a pull request describing the change and its impact.

Changes to the model, feature schema, threshold, or evaluation data should include a clear validation methodology and results. Avoid promoting model changes without deliberate review.

## License

This project is licensed under the **MIT License**. See the [`LICENSE`](LICENSE) file for details.

## Disclaimer

CertiGuard is an AI-assisted certificate analysis and decision-support project. Automated predictions and forensic indicators may contain errors. A suspicious indicator is not proof of fraud, and a favorable result is not proof of authenticity. Obtain independent confirmation from the issuing institution when required and handle certificate data responsibly.

---

**CertiGuard — Certificate analysis supported by machine learning and evidence.**
