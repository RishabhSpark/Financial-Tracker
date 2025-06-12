import os
import io
import tempfile
import pandas as pd
import pdfplumber
from PyPDF2 import PdfReader
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload
from extractor.run_extraction import run_pipeline
from db.crud import insert_or_replace_po, upsert_drive_files_sqlalchemy, get_all_drive_files, delete_po_by_drive_file_id
from db.database import init_db
from flask import Flask, request, redirect, session, url_for, render_template,  send_file, render_template_string
from extractor.pdf_processing.extract_blocks import extract_blocks
from extractor.pdf_processing.extract_tables import extract_tables
from extractor.pdf_processing.format_po import format_po_for_llm
from flask import jsonify
import sqlite3


app = Flask(__name__)
app.secret_key = "your-secret-key"

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
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
    return redirect(url_for('drive_tree')) # Changed from 'forecast'


@app.route('/process_pdf/<file_id>')
def process_pdf(file_id):
    if 'credentials' not in session:
        return redirect(url_for('authorize'))

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

        fh.seek(0)  # Rewind the BytesIO object to the beginning

        # Create a temporary file to save the PDF content
        # This is necessary because PyMuPDF and pdfplumber typically work with file paths.
        temp_dir = tempfile.gettempdir()
        temp_pdf_path = os.path.join(temp_dir, f"temp_pdf_{file_id}.pdf")

        with open(temp_pdf_path, 'wb') as f:
            f.write(fh.getvalue())

        try:
            # Extract text blocks and tables
            text_blocks = extract_blocks(temp_pdf_path)
            tables = extract_tables(temp_pdf_path)

            # Format for LLM
            llm_formatted_content = format_po_for_llm(text_blocks, tables)

            # You can now save `llm_formatted_content` to a database, a file,
            # or pass it to an LLM directly. For this example, let's just display it.
            return f"""
            <h1>Processed PDF: {file['name']}</h1>
            <h2>LLM Formatted Content (for direct use):</h2>
            <pre>{llm_formatted_content}</pre>
            """

        finally:
            # Clean up the temporary file
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)

    except Exception as e:
        return f"<p>An error occurred: {e}</p>"


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


# @app.route("/sync", methods=["POST"])
# def sync_file():
#     if 'credentials' not in session:
#         return redirect(url_for('authorize'))

#     creds = Credentials.from_authorized_user_info(session['credentials'])
#     service = build('drive', 'v3', credentials=creds)

#     file_id_or_path = request.form.get("file_path", "").strip()

#     try:
#         # Get file metadata
#         file = service.files().get(fileId=file_id_or_path, fields="name, mimeType").execute()

#         # Check PDF
#         if file['mimeType'] != 'application/pdf':
#             return "<p>❌ Only PDF files are supported.</p>"

#         request_file = service.files().get_media(fileId=file_id_or_path)
#         fh = io.BytesIO()
#         downloader = MediaIoBaseDownload(fh, request_file)
#         done = False
#         while not done:
#             status, done = downloader.next_chunk()

#         # Move to start of file and read content
#         fh.seek(0)
#         pdf_reader = PdfReader(fh)
#         text = ""
#         for page in pdf_reader.pages:
#             text += page.extract_text() or ""

#         # Use existing pipeline to extract and store
#         po_json = run_pipeline(text)
#         insert_or_replace_po(po_json)

#         return "<p>✅ File synced successfully from Google Drive!</p>"

#     except Exception as e:
#         print(e)
#         return f"<p>❌ Error syncing file: {e}</p>"


@app.route("/forecast", methods=["GET"])
def forecast():
    # Get filter values from query params
    client_name = request.args.get('client_name', default=None, type=str)
    po_no = request.args.get('po_no', default=None, type=str)
    start_month = request.args.get('start_month', default=None, type=str)
    end_month = request.args.get('end_month', default=None, type=str)

    df = None
    try:
        df = pd.read_csv("forecast_output.csv")
        if 'Inflow (USD)' in df.columns:
            df['Inflow (USD)'] = pd.to_numeric(df['Inflow (USD)'], errors='coerce').fillna(0.0)
    except Exception:
        df = pd.DataFrame()

    # Prepare dropdown options
    client_names = sorted(df['Client Name'].dropna().unique()) if 'Client Name' in df.columns else []
    po_nos = sorted([str(po) for po in df['PO No'].dropna().unique()]) if 'PO No' in df.columns else []
    months = sorted(df['Month'].dropna().unique()) if 'Month' in df.columns else []

    # Apply filters
    filtered_df = df.copy()
    if client_name:
        filtered_df = filtered_df[filtered_df['Client Name'] == client_name]
    if po_no:
        filtered_df = filtered_df[filtered_df['PO No'].astype(str) == po_no]
    if start_month:
        filtered_df = filtered_df[filtered_df['Month'] >= start_month]
    if end_month:
        filtered_df = filtered_df[filtered_df['Month'] <= end_month]

    # Generate filtered pivot table
    pivot_html = generate_pivot_table_html(filtered_df)

    return render_template(
        "forecast.html",
        pivot_table=pivot_html,
        client_names=client_names,
        po_nos=po_nos,
        months=months,
        selected_client=client_name,
        selected_po=po_no,
        selected_start_month=start_month,
        selected_end_month=end_month
    )


def generate_pivot_table_html(df=None):
    try:
        if df is None:
            df = pd.read_csv("forecast_output.csv")

        # Ensure 'Inflow (USD)' is numeric and NaNs are 0.0.
        if 'Inflow (USD)' in df.columns:
            df['Inflow (USD)'] = pd.to_numeric(df['Inflow (USD)'], errors='coerce').fillna(0.0)
        else:
            df['Inflow (USD)'] = pd.Series(dtype='float64')

        all_months_for_pivot = []
        if 'Month' in df.columns and not df['Month'].dropna().empty:
            month_as_datetime = pd.to_datetime(df['Month'], format='%Y-%m', errors='coerce')
            month_as_datetime.dropna(inplace=True)
            if not month_as_datetime.empty:
                min_month = month_as_datetime.min()
                max_month = month_as_datetime.max()
                all_months_for_pivot = pd.date_range(min_month, max_month, freq='MS').strftime('%Y-%m').tolist()

        for col in ["Client Name", "PO No", "Month"]:
            if col not in df.columns:
                df[col] = pd.Series(dtype='object')

        # --- Pivot Table with Totals ---
        pivot = df.pivot_table(
            index=["Client Name", "PO No"],
            columns="Month",
            values="Inflow (USD)",
            aggfunc="sum",
            fill_value=0.0
        )
        pivot = pivot.reindex(columns=all_months_for_pivot, fill_value=0.0)
        pivot.reset_index(inplace=True)

        # Add row-wise total (sum across months for each PO)
        month_cols = all_months_for_pivot
        if month_cols:
            pivot['Total'] = pivot[month_cols].sum(axis=1)
        else:
            pivot['Total'] = 0.0

        # Add a serial number column
        if not pivot.empty:
            pivot.insert(0, 'S.No', range(1, 1 + len(pivot)))
        else:
            if 'S.No' not in pivot.columns: pivot['S.No'] = pd.Series(dtype='int')
            if "Client Name" not in pivot.columns: pivot["Client Name"] = pd.Series(dtype='object')
            if "PO No" not in pivot.columns: pivot["PO No"] = pd.Series(dtype='object')

        # Add a total row at the bottom (sum for each month and for the 'Total' column)
        if not pivot.empty and month_cols:
            total_row = [''] * len(pivot.columns)
            # Find column indices
            s_no_idx = pivot.columns.get_loc('S.No') if 'S.No' in pivot.columns else None
            client_idx = pivot.columns.get_loc('Client Name') if 'Client Name' in pivot.columns else None
            po_idx = pivot.columns.get_loc('PO No') if 'PO No' in pivot.columns else None
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
        html = pivot.to_html(
            classes="table table-striped table-bordered",
            border=0,
            index=False,
            float_format='%.2f',
            na_rep=""
        )
        return html
    except FileNotFoundError:
        return "<p>Error: <code>forecast_output.csv</code> not found. Please generate the forecast first.</p>"
    except Exception as e:
        return f"<p>Error generating pivot table: {e}</p>"


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
    results = service.files().list(q=query, fields="files(id, name, mimeType)", pageSize=1000).execute()
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
                html += f'<li class="folder"><span class="toggle">+</span> <span class="folder-name">📁 {node["name"]}</span> <button class="select-folder-btn" data-folder-path="{folder_path}">Select Folder</button><div class="children" style="display:none" data-folder-id="{node["id"]}" data-folder-path="{folder_path}"></div></li>'
            else:
                html += f'<li class="file">📄 {node["name"]}</li>'
        html += '</ul>'
        return html
    tree_html = render_tree(tree)
    return render_template_string("""
        <html>
        <head>
        <style>
        ul { list-style-type: none; }
        .folder { font-weight: bold; }
        .file { margin-left: 20px; }
        .toggle { cursor: pointer; color: #007bff; margin-right: 5px; }
        .folder-name { cursor: pointer; }
        .select-folder-btn { margin-left: 10px; font-size: 0.9em; }
        #selected-folder-box { margin-top: 30px; font-size: 1.1em; }
        #selected-folder-input { width: 60%; font-size: 1em; background: #f5f5f5; border: 1px solid #ccc; padding: 6px; border-radius: 4px; }
        #confirm-folder-btn { margin-top: 10px; font-size: 1em; padding: 6px 16px; background: #007bff; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
        #confirm-folder-btn:disabled { background: #aaa; cursor: not-allowed; }
        #result-table { margin-top: 30px; }
        #go-to-dashboard-btn { margin-left: 10px, font-size: 1em, padding: 6px 16px, background: #28a745, color: #fff, border: none, border-radius: 4px, cursor: pointer, text-decoration: none, display: inline-block; }
        </style>
        </head>
        <body>
        <h1>Google Drive Folder Tree</h1>
        <div id="drive-tree">
            {{ tree_html|safe }}
        </div>
        <div id="selected-folder-box">
            <label for="selected-folder-input"><b>Folder selected:</b></label>
            <input type="text" id="selected-folder-input" value="" readonly />
            <button id="confirm-folder-btn" disabled>Confirm Folder</button>
        </div>
        <div id="result-table"></div>
        <!-- <a href="/">Back to Home</a> -->  <!-- Removed Back to Home link -->
        <a href="{{ url_for('forecast') }}" id="go-to-dashboard-btn" style="display:none;">Go to Forecast/Dashboard</a>
        <script>
        // Tree expand/collapse logic
        document.addEventListener('click', function(e) {
            if (e.target.classList.contains('toggle') || e.target.classList.contains('folder-name')) {
                var li = e.target.closest('li.folder');
                var childrenDiv = li.querySelector('.children');
                var folderId = childrenDiv.getAttribute('data-folder-id');
                var folderPath = childrenDiv.getAttribute('data-folder-path');
                if (childrenDiv.style.display === 'none') {
                    if (!childrenDiv.hasChildNodes()) {
                        fetch('/drive_tree_children/' + folderId + '?parent_path=' + encodeURIComponent(folderPath))
                            .then(resp => resp.text())
                            .then(html => {
                                childrenDiv.innerHTML = html;
                                childrenDiv.style.display = 'block';
                                li.querySelector('.toggle').textContent = '-';
                            });
                    } else {
                        childrenDiv.style.display = 'block';
                        li.querySelector('.toggle').textContent = '-';
                    }
                } else {
                    childrenDiv.style.display = 'none';
                    li.querySelector('.toggle').textContent = '+';
                }
            }
            // Folder select logic
            if (e.target.classList.contains('select-folder-btn')) {
                var folderPath = e.target.getAttribute('data-folder-path');
                var folderId = e.target.parentElement.querySelector('.children').getAttribute('data-folder-id');
                document.getElementById('selected-folder-input').value = folderPath;
                document.getElementById('selected-folder-input').setAttribute('data-folder-id', folderId);
                document.getElementById('confirm-folder-btn').disabled = false;
            }
        });
        // Confirm folder logic
        document.getElementById('confirm-folder-btn').addEventListener('click', function() {
            var folderId = document.getElementById('selected-folder-input').getAttribute('data-folder-id');
            if (!folderId) return;
            var btn = this;
            btn.disabled = true;
            btn.textContent = 'Processing...';
            fetch('/confirm_folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_id: folderId })
            })
            .then(response => {
                if (response.redirected) {
                    window.location.href = response.url; // Handle redirect from /confirm_folder
                    return null; // Stop further processing if redirected
                }
                return response.text();
            })
            .then(html => {
                if (html) { // Only process if not redirected
                    document.getElementById('result-table').innerHTML = html;
                    // Show the "Go to Forecast/Dashboard" button after successful confirmation
                    var dashboardBtn = document.getElementById('go-to-dashboard-btn');
                    dashboardBtn.style.display = 'block'; // Ensure it's block for layout
                    dashboardBtn.style.marginTop = '10px';


                    // ---- NEW CODE INTEGRATION START ----
                    // Remove existing extract button and result div if any, to prevent duplicates on re-confirm
                    let existingExtractBtn = document.getElementById('extract-pdf-text-btn');
                    if (existingExtractBtn) existingExtractBtn.remove();
                    let existingExtractResultDiv = document.getElementById('extract-pdf-result-div');
                    if (existingExtractResultDiv) existingExtractResultDiv.remove();

                    var extractButton = document.createElement('button');
                    extractButton.id = 'extract-pdf-text-btn';
                    extractButton.textContent = 'Extract Text from PDFs in this Folder';
                    extractButton.style.display = 'block';
                    extractButton.style.marginTop = '10px';
                    extractButton.style.padding = '6px 16px'; // Basic styling
                    extractButton.style.backgroundColor = '#17a2b8'; // Info color
                    extractButton.style.color = 'white';
                    extractButton.style.border = 'none';
                    extractButton.style.borderRadius = '4px';
                    extractButton.style.cursor = 'pointer';


                    var extractResultDisplayDiv = document.createElement('div');
                    extractResultDisplayDiv.id = 'extract-pdf-result-div';
                    extractResultDisplayDiv.style.marginTop = '10px';
                    extractResultDisplayDiv.style.padding = '10px';
                    extractResultDisplayDiv.style.border = '1px solid #eee';
                    extractResultDisplayDiv.style.backgroundColor = '#f9f9f9';


                    extractButton.onclick = function() {
                        this.disabled = true;
                        this.textContent = 'Extracting...';
                        this.style.backgroundColor = '#aaa';
                        var currentFolderId = document.getElementById('selected-folder-input').getAttribute('data-folder-id');
                        if (!currentFolderId) {
                            extractResultDisplayDiv.innerHTML = '<p style="color:red;">Error: Folder ID not found. Please select a folder again.</p>';
                            this.disabled = false;
                            this.textContent = 'Extract Text from PDFs in this Folder';
                            this.style.backgroundColor = '#17a2b8';
                            return;
                        }

                        fetch('/extract_text_from_drive_folder?folder_id=' + currentFolderId)
                            .then(response => response.text())
                            .then(resultHtml => {
                                extractResultDisplayDiv.innerHTML = resultHtml;
                                this.disabled = false;
                                this.textContent = 'Extract Text from PDFs in this Folder';
                                this.style.backgroundColor = '#17a2b8';
                            })
                            .catch(error => {
                                console.error('Error extracting PDF text:', error);
                                extractResultDisplayDiv.innerHTML = '<p style="color:red;">Error during PDF text extraction. Check console and terminal.</p>';
                                this.disabled = false;
                                this.textContent = 'Extract Text from PDFs in this Folder';
                                this.style.backgroundColor = '#17a2b8';
                            });
                    };

                    // Insert the new button before the dashboard button
                    dashboardBtn.parentNode.insertBefore(extractButton, dashboardBtn);
                    // Insert the result display div after the new button
                    extractButton.insertAdjacentElement('afterend', extractResultDisplayDiv);
                    // ---- NEW CODE INTEGRATION END ----
                }
                btn.disabled = false;
                btn.textContent = 'Confirm Folder';
            })
            .catch(error => {
                console.error('Error confirming folder:', error);
                document.getElementById('result-table').innerHTML = '<p>Error confirming folder. Please try again.</p>';
                btn.disabled = false;
                btn.textContent = 'Confirm Folder';
            });
        });
        </script>
        </body>
        </html>
    """, tree_html=tree_html)


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
        upsert_drive_files_sqlalchemy(files) # Use the new SQLAlchemy function
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
        folder_metadata = service.files().get(fileId=folder_id, fields="id, name, mimeType").execute()
        if folder_metadata.get('mimeType') != 'application/vnd.google-apps.folder':
            return f"The provided ID '{folder_id}' is not a folder.", 400
        print(f"Accessing folder: {folder_metadata.get('name')} (ID: {folder_id})")
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
            print(f"File '{db_name}' (id={db_id}) deleted from Drive (by filename). Removing from database...")
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
                    file_last_edited_dt = datetime.fromisoformat(file_last_edited[:-1] + '+00:00')
                else:
                    file_last_edited_dt = datetime.fromisoformat(file_last_edited)
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
                temp_pdf_path = os.path.join(temp_dir, temp_pdf_filename);

                with open(temp_pdf_path, 'wb') as f_temp:
                    f_temp.write(fh.getvalue())
                
                print(f"  PDF content for {file_item['name']} saved to temporary file: {temp_pdf_path}")

                # --- RUN EXTRACTION PIPELINE (like main.py) ---
                print(f"  Running extraction pipeline for {file_item['name']}...")
                po_json_data_for_db = run_pipeline(temp_pdf_path)
                if po_json_data_for_db:
                    insert_or_replace_po(po_json_data_for_db)
                    print(f"  Successfully inserted/replaced PO data for {file_item['name']} into database.")
                    extracted_texts_summary.append(f"Inserted/replaced PO data for: {file_item['name']}")
                else:
                    print(f"  Warning: No data extracted from {file_item['name']}. Skipping database insertion for this file.")
                    extracted_texts_summary.append(f"No data extracted from {file_item['name']}. DB insert skipped.")
                # --- END PIPELINE ---

            finally:
                # Clean up the temporary file
                if temp_pdf_path and os.path.exists(temp_pdf_path):
                    print(f"  Deleting temporary file: {temp_pdf_path}")
                    os.remove(temp_pdf_path)

        except Exception as error:
            error_message = f"Error processing file {file_item['name']} (ID: {file_item['id']}): {error}"
            print(f"{error_message}\n{'-'*80}")
            extracted_texts_summary.append(f"Error processing: {file_item['name']} - {error}")
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

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
