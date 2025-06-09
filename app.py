import os
import io
import pandas as pd
import tempfile
import pdfplumber
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload
from flask import Flask, request, redirect, session, url_for, render_template,  send_file, render_template_string


app = Flask(__name__)
app.secret_key = "your-secret-key"

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CLIENT_SECRETS_FILE = 'client_secret.json'


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/authorize')
def authorize():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    return redirect(auth_url)


@app.route('/oauth2callback')
def oauth2callback():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    session['credentials'] = creds_to_dict(creds)
    return redirect(url_for('list_files'))


@app.route('/list')
def list_files():
    if 'credentials' not in session:
        return redirect('authorize')

    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)

    results = service.files().list(
        pageSize=10, fields="files(id, name, mimeType)").execute()
    files = results.get('files', [])

    return render_template('list.html', files=files)


@app.route('/read_pdf/<file_id>')
def read_pdf(file_id):
    if 'credentials' not in session:
        return redirect(url_for('authorize'))  # Handle OAuth flow

    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)

    # Get file metadata
    file = service.files().get(fileId=file_id, fields='name, mimeType').execute()
    if file['mimeType'] != 'application/pdf':
        return "<p>❌ Only PDF files are supported.</p>"

    # Stream file into memory
    request_drive = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request_drive)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    fh.seek(0)

    # Extract PDF text
    text = ""
    with pdfplumber.open(fh) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""  # Some pages may be empty

    return f"<pre>{text}</pre>"


@app.route('/download/<file_id>')
def download_pdf(file_id):
    if 'credentials' not in session:
        return redirect(url_for('authorize'))

    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)

    file = service.files().get(fileId=file_id, fields='name, mimeType').execute()
    file_name = file['name']
    mime_type = file['mimeType']

    if mime_type != 'application/pdf' and not file_name.endswith('.pdf'):
        return "<p>❌ Only PDF files are supported for download.</p>"

    project_root = os.path.dirname(os.path.abspath(__file__))
    save_dir = os.path.join(project_root, 'input', 'POs')
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, file_name)

    request = service.files().get_media(fileId=file_id)
    with open(save_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

    print(f"✅ PDF saved to: {save_path}")
    return f"<p>✅ PDF downloaded and saved to <code>{save_path}</code></p>"


@app.route("/view-forecast")
def view_forecast():
    csv_path = "forecast_output.csv"

    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        return f"<p>❌ File '{csv_path}' not found.</p>"

    html_table = df.to_html(
        classes='table table-bordered table-striped', index=False)

    return render_template_string(f"""
    <html>
        <head>
            <title>📊 Forecast Output</title>
            <link rel="stylesheet" 
                  href="https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/4.5.2/css/bootstrap.min.css">
        </head>
        <body class="p-4">
            <h2>📈 Forecast Output Table</h2>
            {html_table}
        </body>
    </html>
    """)


def creds_to_dict(creds):
    return {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }


if __name__ == '__main__':
    app.run(debug=True)
