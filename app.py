import os
import io
import tempfile
import numpy as np
import pandas as pd
from PyPDF2 import PdfReader
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload
from extractor.run_extraction import run_pipeline
from functools import wraps
from db.crud import insert_or_replace_po, upsert_drive_files_sqlalchemy, get_all_drive_files, delete_po_by_drive_file_id, get_po_with_schedule
from db.database import init_db
from flask import Flask, request, redirect, session, url_for, render_template,  send_file, render_template_string, jsonify, flash, g
from extractor.pdf_processing.extract_blocks import extract_blocks
from extractor.pdf_processing.extract_tables import extract_tables
from extractor.pdf_processing.format_po import format_po_for_llm
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()


app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'supersecret123')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CLIENT_SECRETS_FILE = 'client_secret.json'


USERS = {}
for i in range(1, 10):
    username = os.getenv(f'USER_{i}_NAME')
    password = os.getenv(f'USER_{i}_PASSWORD')
    if username and password:
        USERS[username] = password


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


@app.route('/add_client', methods=['GET', 'POST'])
def add_unconfirmed_order():
    if request.method == 'POST':
        # Just print the form data to the terminal for testing
        form_data = request.form.to_dict()
        print("Received Unconfirmed Order:")
        for key, value in form_data.items():
            print(f"{key}: {value}")
        return "<h3>Order received. Check console for printed data.</h3><a href='/test-form'>Back</a>"

    return render_template("add_unconfirmed_order.html")


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
    return redirect(url_for('drive_folder_upload'))  # Changed from 'drive_tree'


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


@app.route("/forecast", methods=["GET"])
@login_required
def forecast():
    creds = Credentials.from_authorized_user_info(session['credentials'])
    def parse_checklist(param):
        val = request.args.get(param, default=None, type=str)
        if val is None or val == '':
            return []
        return [v.strip() for v in val.split(",") if v.strip()]

    client_names_selected = parse_checklist('client_name')
    po_nos_selected = parse_checklist('po_no')
    project_owners_selected = parse_checklist('project_owner')
    start_month_selected = request.args.get('start_month', default=None, type=str)
    end_month_selected = request.args.get('end_month', default=None, type=str)

    df = None
    try:
        df = pd.read_csv("forecast_output.csv")
        if 'Inflow (USD)' in df.columns:
            df['Inflow (USD)'] = pd.to_numeric(
                df['Inflow (USD)'], errors='coerce').fillna(0.0)
    except Exception:
        df = pd.DataFrame()

    # Prepare dropdown options
    client_names = sorted(df['Client Name'].dropna(
    ).unique()) if 'Client Name' in df.columns else []
    po_nos = sorted([str(po) for po in df['PO No'].dropna().unique()]
                    ) if 'PO No' in df.columns else []
    months = sorted(df['Month'].dropna().unique()
                    ) if 'Month' in df.columns else []
    project_owners = sorted(df['Project Owner'].dropna().unique()) if 'Project Owner' in df.columns else []

    # Apply filters (multi-select for client/po/owner, range for months)
    filtered_df = df.copy()
    if client_names_selected:
        filtered_df = filtered_df[filtered_df['Client Name'].isin(
            client_names_selected)]
    if po_nos_selected:
        filtered_df = filtered_df[filtered_df['PO No'].astype(
            str).isin(po_nos_selected)]
    if project_owners_selected:
        filtered_df = filtered_df[filtered_df['Project Owner'].isin(project_owners_selected)]
    if start_month_selected:
        filtered_df = filtered_df[filtered_df['Month'] >= start_month_selected]
    if end_month_selected:
        filtered_df = filtered_df[filtered_df['Month'] <= end_month_selected]

    # Generate filtered pivot table
    pivot_html = generate_pivot_table_html(filtered_df)

    return render_template(
        "forecast.html",
        pivot_table=pivot_html,
        client_names=client_names,
        po_nos=po_nos,
        months=months,
        project_owners=project_owners,
        selected_client=client_names_selected,
        selected_po=po_nos_selected,
        selected_owner=project_owners_selected,
        selected_start_month=[
            start_month_selected] if start_month_selected else [],
        selected_end_month=[end_month_selected] if end_month_selected else []
    )


def generate_pivot_table_html():
    try:
        df = pd.read_csv("forecast_output.csv")
        if 'Inflow (USD)' in df.columns:
            df['Inflow (USD)'] = pd.to_numeric(
                df['Inflow (USD)'], errors='coerce').fillna(0.0)
    except Exception:
        df = pd.DataFrame()

    # Prepare dropdown options
    client_names = sorted(df['Client Name'].dropna(
    ).unique()) if 'Client Name' in df.columns else []
    po_nos = sorted([str(po) for po in df['PO No'].dropna().unique()]
                    ) if 'PO No' in df.columns else []
    months = sorted(df['Month'].dropna().unique()
                    ) if 'Month' in df.columns else []

    # Apply filters (multi-select for client/po, range for months)
    filtered_df = df.copy()
    if client_names_selected:
        filtered_df = filtered_df[filtered_df['Client Name'].isin(
            client_names_selected)]
    if po_nos_selected:
        filtered_df = filtered_df[filtered_df['PO No'].astype(
            str).isin(po_nos_selected)]
    if start_month_selected:
        filtered_df = filtered_df[filtered_df['Month'] >= start_month_selected]
    if end_month_selected:
        filtered_df = filtered_df[filtered_df['Month'] <= end_month_selected]

    # Generate filtered pivot table
    pivot_html = generate_pivot_table_html(filtered_df)

    return render_template(
        "forecast.html",
        pivot_table=pivot_html,
        client_names=client_names,
        po_nos=po_nos,
        months=months,
        selected_client=client_names_selected,
        selected_po=po_nos_selected,
        selected_start_month=[
            start_month_selected] if start_month_selected else [],
        selected_end_month=[end_month_selected] if end_month_selected else []
    )


def generate_pivot_table_html(df=None):
    try:
        if df is None:
            df = pd.read_csv("forecast_output.csv")

        # Ensure 'Inflow (USD)' is numeric and NaNs are 0.0.
        if 'Inflow (USD)' in df.columns:
            df['Inflow (USD)'] = pd.to_numeric(
                df['Inflow (USD)'], errors='coerce').fillna(0.0)
        else:
            df['Inflow (USD)'] = pd.Series(dtype='float64')

        all_months_for_pivot = []
        if 'Month' in df.columns and not df['Month'].dropna().empty:
            month_as_datetime = pd.to_datetime(
                df['Month'], format='%Y-%m', errors='coerce')
            month_as_datetime.dropna(inplace=True)
            if not month_as_datetime.empty:
                min_month = month_as_datetime.min()
                max_month = month_as_datetime.max()
                all_months_for_pivot = pd.date_range(
                    min_month, max_month, freq='MS').strftime('%Y-%m').tolist()

        for col in ["Client Name", "PO No", "Project Owner", "Month"]:
            if col not in df.columns:
                df[col] = pd.Series(dtype='object')

        # --- Pivot Table with Totals ---
        pivot = df.pivot_table(
            index=["Client Name", "PO No", "Project Owner"],
            columns="Month",
            values="Inflow (USD)",
            aggfunc="sum",
            fill_value=0.0
        )
        pivot = pivot.reindex(columns=all_months_for_pivot, fill_value=0.0)
        pivot.reset_index(inplace=True)

        # Format month columns to 'Month YYYY' (e.g., 'May 2025')
        month_col_map = {}
        for m in all_months_for_pivot:
            try:
                dt = pd.to_datetime(m, format="%Y-%m")
                month_col_map[m] = dt.strftime("%b %Y")
            except Exception:
                month_col_map[m] = m
        pivot.rename(columns=month_col_map, inplace=True)
        formatted_month_cols = [month_col_map.get(
            m, m) for m in all_months_for_pivot]

        # Add row-wise total (sum across months for each PO)
        month_cols = formatted_month_cols
        if month_cols:
            pivot['Total'] = pivot[month_cols].sum(axis=1)
            pivot['Total'] = np.ceil(pivot['Total'])
        else:
            pivot['Total'] = 0.0

        # Add a serial number column
        if not pivot.empty:
            pivot.insert(0, 'S.No', range(1, 1 + len(pivot)))
        else:
            if 'S.No' not in pivot.columns:
                pivot['S.No'] = pd.Series(dtype='int')
            if "Client Name" not in pivot.columns:
                pivot["Client Name"] = pd.Series(dtype='object')
            if "PO No" not in pivot.columns:
                pivot["PO No"] = pd.Series(dtype='object')

        # Add a total row at the bottom (sum for each month and for the 'Total' column)
        if not pivot.empty and month_cols:
            total_row = [''] * len(pivot.columns)
            # Find column indices
            s_no_idx = pivot.columns.get_loc(
                'S.No') if 'S.No' in pivot.columns else None
            client_idx = pivot.columns.get_loc(
                'Client Name') if 'Client Name' in pivot.columns else None
            po_idx = pivot.columns.get_loc(
                'PO No') if 'PO No' in pivot.columns else None
            # Label the total row
            if client_idx is not None:
                total_row[client_idx] = 'TOTAL'
            if po_idx is not None:
                total_row[po_idx] = ''
            # Fill month totals
            for m in month_cols:
                col_idx = pivot.columns.get_loc(m)
                total_row[col_idx] = pivot[m].sum()
            # Fill grand total
            total_col_idx = pivot.columns.get_loc('Total')
            total_row[total_col_idx] = pivot['Total'].sum()
            # Insert the total row as a DataFrame
            total_df = pd.DataFrame([total_row], columns=pivot.columns)
            # Concatenate to the pivot
            pivot = pd.concat([pivot, total_df], ignore_index=True)

        # Convert the pivot table to HTML, formatting float values to two decimal places
        def format_float(val):
            try:
                return f"{float(val):.2f}"
            except:
                return val

        def format_usd(val):
            try:
                return "$" + format(float(val), ",.2f")
            except:
                return val
        html = pivot.to_html(
            classes="table table-striped table-bordered",
            border=0,
            index=False,
            formatters={col: format_usd for col in pivot.columns if col not in [
                'S.No', 'Client Name', 'PO No']},
            na_rep=""
        )
        return html
    except FileNotFoundError:
        return "<p>Error: <code>forecast_output.csv</code> not found. Please generate the forecast first.</p>"
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


def get_drive_tree(service, parent_id='root'):
    """
    Recursively builds a tree of files/folders from Google Drive.
    Returns a nested dict structure.
    """
    query = f"'{parent_id}' in parents and trashed = false"
    results = service.files().list(
        q=query, fields="files(id, name, mimeType)", pageSize=1000).execute()
    items = results.get('files', [])
    tree = []
    for item in items:
        node = {
            'id': item['id'],
            'name': item['name'],
            'mimeType': item['mimeType']
        }
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            node['children'] = get_drive_tree(service, item['id'])
        tree.append(node)
    return tree


@app.route('/drive_tree_children/<folder_id>')
@login_required
def drive_tree_children(folder_id):
    if 'credentials' not in session:
        return ''
    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)
    children = get_drive_tree(service, folder_id)

    def render_tree(nodes, parent_path=""):
        html = '<ul style="margin-left:20px">'
        for node in nodes:
            if node['mimeType'] == 'application/vnd.google-apps.folder':
                folder_path = f"{parent_path}/{node['name']}" if parent_path else node['name']
                html += f'<li class="folder"><span class="toggle">+</span> <span class="folder-name">📁 {node["name"]}</span> <button class="select-folder-btn" data-folder-path="{folder_path}">Select Folder</button><div class="children" style="display:none" data-folder-id="{node["id"]}" data-folder-path="{folder_path}"></div></li>'
            else:
                html += f'<li class="file">📄 {node["name"]}</li>'
        html += '</ul>'
        return html
    parent_path = request.args.get('parent_path', '')
    return render_tree(children, parent_path)


@app.route('/drive_tree')
@login_required
def drive_tree():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))

    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)
    tree = get_drive_tree(service)

    def render_tree(nodes, parent_path=""):
        html = '<ul>'
        for node in nodes:
            if node['mimeType'] == 'application/vnd.google-apps.folder':
                folder_path = f"{parent_path}/{node['name']}" if parent_path else node['name']
                html += f'''
                    <li class="folder">
                        <span class="toggle">+</span>
                        <span class="folder-name">📁 {node["name"]}</span>
                        <button class="select-folder-btn" data-folder-path="{folder_path}">Select Folder</button>
                        <div class="children" style="display:none" data-folder-id="{node["id"]}" data-folder-path="{folder_path}"></div>
                    </li>
                '''
            else:
                html += f'<li class="file">📄 {node["name"]}</li>'
        html += '</ul>'
        return html

    tree_html = render_tree(tree)
    return render_template("drive_tree.html", tree_html=tree_html)


def list_all_files_in_folder(service, folder_id):
    """
    Recursively list all files in a Google Drive folder by folder_id.
    Returns a list of dicts: [{id, name, modifiedTime}]
    """
    files = []
    page_token = None
    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
            pageToken=page_token
        ).execute()
        for file in response.get('files', []):
            if file['mimeType'] == 'application/vnd.google-apps.folder':
                files.extend(list_all_files_in_folder(service, file['id']))
            else:
                files.append({
                    'id': file['id'],
                    'name': file['name'],
                    'mimeType': file['mimeType'],
                    'modifiedTime': file.get('modifiedTime', '')
                })
        page_token = response.get('nextPageToken', None)
        if not page_token:
            break
    return files


def render_files_table(files):
    if not files:
        return '<p>No files found in this folder.</p>'
    html = '<table border="1" id="drive-files-table"><tr><th>Filename</th><th>Last Edited</th></tr>'
    for f in files:
        html += f'<tr><td>{f["name"]}</td><td>{f["modifiedTime"]}</td></tr>'
    html += '</table>'
    return html


@app.route('/confirm_folder', methods=['POST'])
def confirm_folder():
    if 'credentials' not in session:
        return '<p>Not authorized.</p>', 401
    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)
    data = request.get_json()
    folder_id = data.get('folder_id')
    if not folder_id:
        return '<p>No folder selected.</p>', 400
    # ensure_drive_files_table() # Removed call to old SQLite function
    files = list_all_files_in_folder(service, folder_id)
    try:
        upsert_drive_files_sqlalchemy(files)  # Use the new SQLAlchemy function
    except Exception as e:
        # Log the error e.g., app.logger.error(f"Error upserting drive files: {e}")
        return f"<p>Error updating database: {e}</p>", 500
    return render_files_table(files)


@app.route('/extract_text_from_drive_folder')
def extract_text_from_drive_folder():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))

    folder_id = request.args.get('folder_id')
    if not folder_id:
        return "Please provide a 'folder_id' query parameter.", 400

    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)

    try:
        # Check if the folder_id is valid by trying to get its metadata
        folder_metadata = service.files().get(
            fileId=folder_id, fields="id, name, mimeType").execute()
        if folder_metadata.get('mimeType') != 'application/vnd.google-apps.folder':
            return f"The provided ID '{folder_id}' is not a folder.", 400
        print(
            f"Accessing folder: {folder_metadata.get('name')} (ID: {folder_id})")
    except Exception as e:
        return f"Invalid folder_id or error accessing folder: {e}", 400

    all_files_in_folder = list_all_files_in_folder(service, folder_id)
    pdf_files_found = False
    extracted_texts_summary = []

    print(f"\nStarting PDF text extraction for folder ID: {folder_id}")
    # 1. Get current DB state for drive files
    db_files = get_all_drive_files()  # {name: (last_edited, id)}
    # 2. Build a set of current drive file names and ids from the folder
    current_drive_file_names = set()
    current_drive_file_ids = set()
    for file_item in all_files_in_folder:
        if file_item.get('mimeType') == 'application/pdf':
            current_drive_file_names.add(file_item['name'])
            current_drive_file_ids.add(file_item['id'])
    # 3. Find files in DB that are no longer in Drive and delete their PO data (by filename)
    db_file_names = set(db_files.keys())
    for db_name, (db_last_edited, db_id) in db_files.items():
        if db_name not in current_drive_file_names:
            print(
                f"File '{db_name}' (id={db_id}) deleted from Drive (by filename). Removing from database...")
            delete_po_by_drive_file_id(db_id)
    # 4. For each file in Drive, decide to skip, update, or add
    for file_item in all_files_in_folder:
        if file_item.get('mimeType') != 'application/pdf':
            continue
        file_name = file_item['name']
        file_id = file_item['id']
        file_last_edited = file_item.get('modifiedTime')
        # Convert modifiedTime to datetime for comparison
        from datetime import datetime
        file_last_edited_dt = None
        if file_last_edited:
            try:
                if file_last_edited.endswith('Z'):
                    file_last_edited_dt = datetime.fromisoformat(
                        file_last_edited[:-1] + '+00:00')
                else:
                    file_last_edited_dt = datetime.fromisoformat(
                        file_last_edited)
            except Exception:
                pass
        db_entry = db_files.get(file_name)
        if db_entry:
            db_last_edited, db_id = db_entry
            if db_last_edited == file_last_edited_dt:
                print(f"Skipping {file_name} (unchanged)")
                continue  # Skip unchanged
            else:
                print(f"Updating {file_name} (timestamp changed)")
                # Remove old PO data for this file id before reprocessing
                delete_po_by_drive_file_id(file_id)
        else:
            print(f"Adding new file {file_name}")
        try:
            # Download the file
            request_file = service.files().get_media(fileId=file_item['id'])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request_file)
            done = False
            while not done:
                status, done = downloader.next_chunk()

            fh.seek(0)

            # --- Integration of extract_blocks and extract_tables ---
            temp_pdf_path = None
            try:
                # Create a temporary file to save the PDF content
                temp_dir = tempfile.gettempdir()
                # Generate a unique filename to avoid conflicts if multiple requests happen concurrently
                temp_pdf_filename = f"temp_drive_pdf_{file_item['id']}_{os.urandom(4).hex()}.pdf"
                temp_pdf_path = os.path.join(temp_dir, temp_pdf_filename)

                with open(temp_pdf_path, 'wb') as f_temp:
                    f_temp.write(fh.getvalue())

                print(
                    f"  PDF content for {file_item['name']} saved to temporary file: {temp_pdf_path}")

                # --- RUN EXTRACTION PIPELINE (like main.py) ---
                print(
                    f"  Running extraction pipeline for {file_item['name']}...")
                po_json_data_for_db = run_pipeline(temp_pdf_path)
                if po_json_data_for_db:
                    insert_or_replace_po(po_json_data_for_db)
                    print(
                        f"  Successfully inserted/replaced PO data for {file_item['name']} into database.")
                    extracted_texts_summary.append(
                        f"Inserted/replaced PO data for: {file_item['name']}")
                else:
                    print(
                        f"  Warning: No data extracted from {file_item['name']}. Skipping database insertion for this file.")
                    extracted_texts_summary.append(
                        f"No data extracted from {file_item['name']}. DB insert skipped.")
                # --- END PIPELINE ---

            finally:
                # Clean up the temporary file
                if temp_pdf_path and os.path.exists(temp_pdf_path):
                    print(f"  Deleting temporary file: {temp_pdf_path}")
                    os.remove(temp_pdf_path)

        except Exception as error:
            error_message = f"Error processing file {file_item['name']} (ID: {file_item['id']}): {error}"
            print(f"{error_message}\n{'-'*80}")
            extracted_texts_summary.append(
                f"Error processing: {file_item['name']} - {error}")
        finally:
            if fh:
                fh.close()
        pdf_files_found = True

    print(f"Finished processing folder ID: {folder_id}\n")

    # --- Export and Forecast steps (like main.py) ---
    print("\n--- Exporting Data to JSON and CSV ---")
    from extractor.export import export_all_pos_json, export_all_csvs
    export_all_pos_json()
    export_all_csvs()
    print("--- Data Export Complete ---")

    print("\n--- Generating Financial Forecast ---")
    from forecast_processor import run_forecast_processing
    run_forecast_processing(input_json_path="./output/purchase_orders.json")
    print("--- Financial Forecast Generation Complete ---")

    print("\nAll processes finished successfully!")

    if not pdf_files_found:
        message = f"No PDF files found in the specified folder '{folder_metadata.get('name')}' (ID: {folder_id})."
        print(message)
        return message
    else:
        response_message = f"PDF text extraction process initiated for folder '{folder_metadata.get('name')}' (ID: {folder_id}). Check your terminal for output. Summary of processed files:<br>"
        response_message += "<br>".join(extracted_texts_summary)
        return response_message


@app.route('/edit_po/<po_id>', methods=['GET', 'POST'])
def edit_po(po_id):
    if request.method == 'POST':
        # Collect updated fields from the form
        po_data = {
            'po_id': po_id,
            'client_name': request.form.get('client_name'),
            'amount': request.form.get('amount'),
            'status': request.form.get('status'),
            'payment_terms': request.form.get('payment_terms'),
            'payment_type': request.form.get('payment_type'),
            'start_date': request.form.get('start_date'),
            'end_date': request.form.get('end_date'),
            'duration_months': request.form.get('duration_months'),
            'payment_frequency': request.form.get('payment_frequency'),
            'project_owner': request.form.get('project_owner'),
        }
        # Handle milestones and payment_schedule
        if po_data['payment_type'] == 'milestone':
            milestones = []
            names = request.form.getlist('milestone_name')
            descs = request.form.getlist('milestone_description')
            dues = request.form.getlist('milestone_due_date')
            pers = request.form.getlist('milestone_percentage')
            for n, d, due, p in zip(names, descs, dues, pers):
                milestones.append({
                    'milestone_name': n,
                    'milestone_description': d,
                    'milestone_due_date': due,
                    'milestone_percentage': p
                })
            po_data['milestones'] = milestones
        elif po_data['payment_type'] == 'distributed':
            schedule = []
            dates = request.form.getlist('payment_date')
            amounts = request.form.getlist('payment_amount')
            descs = request.form.getlist('payment_description')
            for dt, amt, desc in zip(dates, amounts, descs):
                schedule.append({
                    'payment_date': dt,
                    'payment_amount': amt,
                    'payment_description': desc
                })
            po_data['payment_schedule'] = schedule
        # Save changes
        insert_or_replace_po(po_data)
        return redirect(url_for('forecast'))

    # GET: Show form with current PO data
    po = get_po_with_schedule(po_id)
    if not po:
        return f"<p>PO with ID {po_id} not found.</p>"
    return render_template('edit_po.html', po=po)


@app.route('/refresh_charts')
def refresh_charts():
    # Re-run export and forecast processing
    from extractor.export import export_all_pos_json, export_all_csvs
    from forecast_processor import run_forecast_processing
    export_all_pos_json()
    export_all_csvs()
    run_forecast_processing(input_json_path="./output/purchase_orders.json")
    return redirect(url_for('forecast'))


@app.route('/download_xlsx')
def download_xlsx():
    from extractor.export import export_all_pos_json, export_all_csvs
    from forecast_processor import run_forecast_processing
    export_all_pos_json()
    export_all_csvs()
    run_forecast_processing(input_json_path="./output/purchase_orders.json")
    xlsx_path = os.path.abspath("forecast_pivot.xlsx")
    return send_file(xlsx_path, as_attachment=True, download_name="forecast_pivot.xlsx")


@app.route('/drive_folder_upload', methods=['GET', 'POST'])
@login_required
def drive_folder_upload():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))
    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)
    error = None
    pdf_files = []
    folder_id = None
    folder_url = ''
    llm_summary = None
    if request.method == 'POST':
        folder_url = request.form.get('folder_url', '').strip()
        folder_id = request.form.get('folder_id', '').strip()
        run_llm = request.form.get('run_llm')
        # If folder_url is provided, extract folder_id from it
        if folder_url:
            import re
            match = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_url)
            if match:
                folder_id = match.group(1)
            else:
                folder_id = folder_url  # Assume user pasted the ID directly
        if folder_id:
            try:
                folder_metadata = service.files().get(fileId=folder_id, fields="id, name, mimeType").execute()
                if folder_metadata.get('mimeType') != 'application/vnd.google-apps.folder':
                    error = f"The provided ID '{folder_id}' is not a folder."
                    folder_id = None
                else:
                    response = service.files().list(
                        q=f"'{folder_id}' in parents and trashed = false and mimeType = 'application/pdf'",
                        fields="files(id, name, modifiedTime)",
                    ).execute()
                    pdf_files = response.get('files', [])
                    if run_llm and pdf_files:
                        # Run LLM pipeline on all PDFs in the folder
                        all_files_in_folder = list_all_files_in_folder(service, folder_id)
                        pdfs = [f for f in all_files_in_folder if f.get('mimeType') == 'application/pdf']
                        extracted_texts_summary = []
                        for file_item in pdfs:
                            file_name = file_item['name']
                            file_id = file_item['id']
                            try:
                                request_file = service.files().get_media(fileId=file_id)
                                fh = io.BytesIO()
                                downloader = MediaIoBaseDownload(fh, request_file)
                                done = False
                                while not done:
                                    status, done = downloader.next_chunk()
                                fh.seek(0)
                                temp_pdf_path = None
                                try:
                                    temp_dir = tempfile.gettempdir()
                                    temp_pdf_filename = f"temp_drive_pdf_{file_id}_{os.urandom(4).hex()}.pdf"
                                    temp_pdf_path = os.path.join(temp_dir, temp_pdf_filename)
                                    with open(temp_pdf_path, 'wb') as f_temp:
                                        f_temp.write(fh.getvalue())
                                    po_json_data_for_db = run_pipeline(temp_pdf_path)
                                    if po_json_data_for_db:
                                        insert_or_replace_po(po_json_data_for_db)
                                        extracted_texts_summary.append(f"Inserted/replaced PO data for: {file_name}")
                                    else:
                                        extracted_texts_summary.append(f"No data extracted from {file_name}. DB insert skipped.")
                                finally:
                                    if temp_pdf_path and os.path.exists(temp_pdf_path):
                                        os.remove(temp_pdf_path)
                            except Exception as error:
                                extracted_texts_summary.append(f"Error processing: {file_name} - {error}")
                            finally:
                                if fh:
                                    fh.close()
                        from extractor.export import export_all_pos_json, export_all_csvs
                        from forecast_processor import run_forecast_processing
                        export_all_pos_json()
                        export_all_csvs()
                        run_forecast_processing(input_json_path="./output/purchase_orders.json")
                        llm_summary = extracted_texts_summary
            except Exception as e:
                error = f"Invalid folder link or error accessing folder: {e}"
                folder_id = None
    return render_template('drive_folder_upload.html', error=error, pdf_files=pdf_files, folder_id=folder_id, folder_url=folder_url, llm_summary=llm_summary)


if __name__ == '__main__':
    init_db()
    app.run(host="0.0.0.0", debug=True)
