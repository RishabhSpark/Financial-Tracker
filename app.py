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
from db.crud import insert_or_replace_po
from flask import Flask, request, redirect, session, url_for, render_template,  send_file, render_template_string
from extractor.pdf_processing.extract_blocks import extract_blocks
from extractor.pdf_processing.extract_tables import extract_tables
from extractor.pdf_processing.format_po import format_po_for_llm


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
    return redirect(url_for('forecast'))


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


@app.route("/sync", methods=["POST"])
def sync_file():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))

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
def forecast():
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
        </div>
        <a href="/">Back to Home</a>
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
                document.getElementById('selected-folder-input').value = folderPath;
            }
        });
        </script>
        </body>
        </html>
    """, tree_html=tree_html)


if __name__ == '__main__':
    app.run(debug=True)
