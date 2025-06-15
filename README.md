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

## License
MIT