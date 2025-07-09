# VolunteerHub Backend

This is the new backend for VolunteerHub, refactored for API-first integration with the React frontend.

## Getting Started

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the backend server:
   ```bash
   python app.py
   ```

## Structure
- `routes/` — All API route handlers
- `models/` — Database models and logic
- `auth/` — Authentication logic
- `utils/` — Utility functions

## Features
- RESTful API for all VolunteerHub features
- JWT-based authentication
- Admin and user endpoints
- AI-powered email and resume endpoints

---

For the React frontend, see the `../frontend` folder. 