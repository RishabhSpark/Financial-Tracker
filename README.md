# Financial Tracker

A web-based platform for tracking, forecasting, and managing purchase orders (POs) and financial inflows for projects. Built with Flask, SQLAlchemy, and Google Drive integration.

## Features

- Upload and extract data from PDF purchase orders
- Assign project leads manually
- Multi-user authentication and session management
- Interactive dashboard with:
  - Multi-select filters for Client Name and PO No
  - Month range filtering with calendar picker
  - Editable PO details
  - Downloadable forecast and pivot tables (CSV/XLSX)
- Google Drive integration for syncing and extracting POs
- Logging and error handling

## Prerequisites

- Python 3.8+
- Git

## Google Drive API Integration (OAuth 2.0)

### 1. Enable Google Drive API

1. Go to the Google Cloud Console.
2. Create a new project or select an existing one.
3. Navigate to APIs & Services > Library.
4. Search for Google Drive API and click Enable.

### 2. Configure OAuth Consent Screen

1. Go to APIs & Services > OAuth consent screen.
2. Choose External or Internal depending on your use case.
3. Fill in:
4. App name
5. User support email
6. Developer contact info
7. Add test users (your own Gmail address for testing).
8. Save and continue (you don't need to publish yet).

### 3. Create OAuth 2.0 Credentials

1. Go to APIs & Services > Credentials.
2. Click Create Credentials → OAuth client ID.
3. Choose Web application.
4. Set an authorized redirect URI:

Add both of these:

```cpp

http://localhost
http://127.0.0.1
```

Example: 
```cpp

http://localhost:5000
http://127.0.0.1:5000
```

✅ Authorized Redirect URIs
Add both of these as well (adjust the port if needed):
Example:
```bash

http://localhost:5000/oauth2callback
http://127.0.0.1:5000/oauth2callback
```
These URIs must exactly match your redirect route used in the app (usually /oauth2callback).

(This must match exactly what your Flask app uses)
5. Download the generated client_secret.json file.


### 4. Add the Secrets File

Place the downloaded file in your project at:

```bash
financial-tracker/client_secret.json
```

✅ Make sure this file is listed in .gitignore and never pushed to GitHub.

### 5. Update Environment Variables
Create or update your .env file inside financial-tracker/ with:
```env
GOOGLE_CLIENT_SECRET_FILE=client_secret.json
SCOPES=https://www.googleapis.com/auth/drive.readonly
```
You can change the scopes as needed.

### 6. Authenticate with Google Drive

When you run the app:

- Visit http://localhost:5000
- Sign in with your Google account
- Approve access to your Drive
- You’ll be redirected back, and your credentials will be stored in the session



## Installation

1. Clone the repository:

```
git clone https://github.com/RishabhSpark/Financial-Tracker.git
```

2. Navigate to the project directory:

```
cd Financial-Tracker
```

3. Create a virtual environment:

On macOS and Linux:
```
python3 -m venv venv
```

On Windows:
```
python -m venv venv
```

4. Activate the virtual environment:

On macOS and Linux:
```
source venv/bin/activate
```

On Windows:
```
.\venv\Scripts\activate
```

5. Install the required packages:
```
pip install -r requirements.txt
```

6. Set up environment variables:
   - Create a `.env` file with user credentials and Google API keys (see `.env.example`)

7. Usage
Once the installation is complete, you can run the application.

```
python app.py
```

8. Access the dashboard:
   - Open [http://localhost:5000](http://localhost:5000) in your browser

## Usage
- **Login** with your credentials
- **Upload or sync** POs from Google Drive
- **Edit and assign** project leads to POs
- **Filter and analyze** financial forecasts using the dashboard
- **Download** reports as needed

## Folder Structure
- `app.py` - Main Flask application
- `db/` - Database models and CRUD logic
- `extractor/` - PDF extraction and processing
- `templates/` - HTML templates (dashboard, forms, etc.)
- `output/` - Generated reports and data