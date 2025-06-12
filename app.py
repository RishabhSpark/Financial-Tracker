import os
import io
import tempfile
import pandas as pd
from PyPDF2 import PdfReader
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload
from extractor.run_extraction import run_pipeline
from db.crud import insert_or_replace_po
from functools import wraps
from extractor.pdf_processing.extract_blocks import extract_blocks
from extractor.pdf_processing.extract_tables import extract_tables
from extractor.pdf_processing.format_po import format_po_for_llm
from flask import Flask, request, redirect, session, url_for, render_template,  send_file, render_template_string, jsonify, flash, g
# from auth_utils import login_required
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecret123"
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CLIENT_SECRETS_FILE = 'client_secret.json'

USERS = {
    "admin": generate_password_hash("password012"),
    "fiona.l": generate_password_hash("securepass"),
    "rishabh": generate_password_hash("securepass")
}


def build_credentials(creds_dict):
    return Credentials(**creds_dict)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.before_request
def load_logged_in_user():
    g.user = None
    if 'username' in session:
        g.user = session['username']


@app.route('/')
def index():
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():

    if "logged_in" in session and session['logged_in']:
        return render_template('index.html')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username in USERS and check_password_hash(USERS[username], password):
            session['logged_in'] = True
            session['username'] = username
            flash(f'Logged in successfully as {username}!', 'success')

            return render_template('index.html')
        else:
            flash('Invalid username or password.', 'danger')
            return render_template('login.html')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    session.pop('credentials', None)
    flash('You have been logged out.', 'info')
    session.clear()
    return redirect(url_for('login'))


@app.route('/authorize')
@login_required
def authorize():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    return redirect(auth_url)


@app.route('/oauth2callback')
@login_required
def oauth2callback():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    session['credentials'] = creds_to_dict(creds)
    return redirect(url_for('forecast'))


@app.route('/list')
@login_required
def list_files():

    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)

    results = service.files().list(
        pageSize=10, fields="files(id, name, mimeType)").execute()
    files = results.get('files', [])

    return render_template('list.html', files=files)


@app.route('/drive_tree')
def drive_tree():

    return render_template('folder_tree.html')


@app.route('/get_pdfs')
@login_required
def get_pdfs():

    folder_id = request.args.get('folder_id')
    if not folder_id:
        return jsonify({'error': 'Missing folder_id'}), 400

    creds = build_credentials(session['credentials'])

    try:
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/pdf' and trashed = false",
            fields="files(id, name, mimeType, webViewLink)",
        ).execute()

        return jsonify(results.get('files', []))

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# @app.route('/read_pdf/<file_id>')
# def read_pdf(file_id):
#     if 'credentials' not in session:
#         return redirect(url_for('authorize'))

#     creds = Credentials.from_authorized_user_info(session['credentials'])
#     service = build('drive', 'v3', credentials=creds)

#     file = service.files().get(fileId=file_id, fields='name, mimeType').execute()
#     if file['mimeType'] != 'application/pdf':
#         return "<p>❌ Only PDF files are supported.</p>"

#     request_drive = service.files().get_media(fileId=file_id)
#     fh = io.BytesIO()
#     downloader = MediaIoBaseDownload(fh, request_drive)

#     done = False
#     while not done:
#         status, done = downloader.next_chunk()

#     fh.seek(0)
    # return fh
    # text = ""
    # with pdfplumber.open(fh) as pdf:
    #     for page in pdf.pages:
    #         text += page.extract_text() or ""

    # return f"<pre>{text}</pre>"


@app.route('/process_pdf/<file_id>')
@login_required
def process_pdf(file_id):

    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)

    try:
        file = service.files().get(fileId=file_id, fields='name, mimeType').execute()
        if file['mimeType'] != 'application/pdf':
            return "<p>❌ Only PDF files are supported for processing.</p>"

        request_drive = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request_drive)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        fh.seek(0)

        temp_dir = tempfile.gettempdir()
        temp_pdf_path = os.path.join(temp_dir, f"temp_pdf_{file_id}.pdf")

        with open(temp_pdf_path, 'wb') as f:
            f.write(fh.getvalue())

        try:
            text_blocks = extract_blocks(temp_pdf_path)
            tables = extract_tables(temp_pdf_path)

            llm_formatted_content = format_po_for_llm(text_blocks, tables)

        # TODO: Return `llm_formatted_content` as string that can be passed as prompt to LLM
            return f"""
            <h1>Processed PDF: {file['name']}</h1>
            <h2>LLM Formatted Content (for direct use):</h2>
            <pre>{llm_formatted_content}</pre>
            """

        finally:
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)

    except Exception as e:
        return f"<p>An error occurred: {e}</p>"


@app.route('/download/<file_id>')
@login_required
def download_pdf(file_id):

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


@app.route("/sync", methods=["POST"])
@login_required
def sync_file():

    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)

    file_id_or_path = request.form.get("file_path", "").strip()

    try:
        # Get file metadata
        file = service.files().get(fileId=file_id_or_path, fields="name, mimeType").execute()

        # Check PDF
        if file['mimeType'] != 'application/pdf':
            return "<p>❌ Only PDF files are supported.</p>"

        request_file = service.files().get_media(fileId=file_id_or_path)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request_file)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        # Move to start of file and read content
        fh.seek(0)
        pdf_reader = PdfReader(fh)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""

        # Use existing pipeline to extract and store
        po_json = run_pipeline(text)
        insert_or_replace_po(po_json)

        return "<p>✅ File synced successfully from Google Drive!</p>"

    except Exception as e:
        print(e)
        return f"<p>❌ Error syncing file: {e}</p>"


@app.route("/forecast")
@login_required
def forecast():
    creds = Credentials.from_authorized_user_info(session['credentials'])
    pivot_html = generate_pivot_table_html()
    return render_template("forecast.html", pivot_table=pivot_html)


def generate_pivot_table_html():
    try:
        df = pd.read_csv("forecast_output.csv")

        pivot = df.pivot_table(
            index=["Client Name", "PO No"],
            columns="Month",
            values="Inflow (USD)",
            aggfunc="sum",
            fill_value=0
        ).reset_index()

        return pivot.to_html(classes="table table-striped table-bordered", border=0, index=False)

    except Exception as e:
        return f"<p>Error generating pivot table: {e}</p>"


@app.route("/download-forecast")
@login_required
def download_forecast():
    return send_file("forecast_pivot.xlsx", as_attachment=True)


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
