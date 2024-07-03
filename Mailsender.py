import os
import json
import base64
import mimetypes
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import threading
import sys
from queue import Queue
from glob import glob


RETRY_ATTEMPTS = 5
RETRY_DELAY = 20
EMAIL_INFO_PATH = 'Text_Files/email_info.txt'
CREDENTIALS_PATH = 'Json_Files/credentials.json'
TOKEN_PATH = 'token.json'
RESULTS_PATH = 'Json_Files/results.json'
ATTACHMENTS_DIRS = ['attachments/CV', 'attachments/Others']

def load_email_info(file_path=EMAIL_INFO_PATH):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            subject = ""
            body = ""
            is_body = False
            for line in lines:
                if line.startswith("Subject:"):
                    subject = line[len("Subject:"):].strip()
                elif line.startswith("Body:"):
                    is_body = True
                    body += line[len("Body:"):].strip() + "\n"
                elif is_body:
                    body += line.strip() + "\n"
        return subject, body.strip()
    except Exception as e:
        print(f"Error loading email info: {e}")
        return "", ""

def load_credentials():
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.compose',
        'https://www.googleapis.com/auth/gmail.readonly'
    ]
    creds = None
    token_path = TOKEN_PATH
    cred_path = CREDENTIALS_PATH

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    
    return creds

def initialize_gmail_service():
    creds = load_credentials()
    try:
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        print(f"Error initializing Gmail service: {e}")
        return None

def build_file_part(file):
    content_type, encoding = mimetypes.guess_type(file)
    if content_type is None or encoding is not None:
        content_type = "application/octet-stream"
    main_type, sub_type = content_type.split("/", 1)

    with open(file, "rb") as f:
        if main_type == "text":
            msg = MIMEText(f.read().decode(), _subtype=sub_type)
        elif main_type == "image":
            msg = MIMEImage(f.read(), _subtype=sub_type)
        elif main_type == "audio":
            msg = MIMEAudio(f.read(), _subtype=sub_type)
        else:
            msg = MIMEBase(main_type, sub_type)
            msg.set_payload(f.read())
            encoders.encode_base64(msg)

    filename = os.path.basename(file)
    msg.add_header("Content-Disposition", "attachment", filename=filename)
    return msg

def load_attachments(company_name):
    attachments = []

    # Charger les fichiers PDF générés
    generated_files = glob(os.path.join('Cover_PDF', f"*{company_name}*.pdf"))
    pdf_path = next((file for file in generated_files if os.path.exists(file) and "OLD" not in file), None)

    if not pdf_path:
        pdf_path = rebuild_cover_letter(company_name)
    else:
        print(f"Using existing PDF for {company_name}")

    # Ajouter la lettre de motivation en premier
    attachments.append(pdf_path)

    # Charger les autres pièces jointes
    for attachment_dir in ATTACHMENTS_DIRS:
        if os.path.exists(attachment_dir) and os.listdir(attachment_dir):
            attachments.extend([os.path.join(attachment_dir, f) for f in os.listdir(attachment_dir)])
    return attachments


def create_draft_with_attachment(service, to_emails, subject, body, attachments, cc_emails=None, bcc_emails=None):
    mime_message = MIMEMultipart()
    mime_message["To"] = to_emails
    if cc_emails:
        mime_message["Cc"] = cc_emails
    if bcc_emails:
        mime_message["Bcc"] = bcc_emails
    mime_message["Subject"] = subject
    mime_message.attach(MIMEText(body, 'plain'))

    for file in attachments:
        mime_message.attach(build_file_part(file))

    encoded_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
    create_draft_request_body = {"message": {"raw": encoded_message}}

    for attempt in range(RETRY_ATTEMPTS):
        try:
            draft = service.users().drafts().create(userId="me", body=create_draft_request_body).execute()
            print(f"Draft created with ID: {draft['id']}")
            return draft
        except HttpError as error:
            print(f"An error occurred: {error}")
            time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"Unexpected error: {e}")
            break
    return None

def check_draft_existence(service, draft_id):
    for attempt in range(RETRY_ATTEMPTS):
        try:
            draft = service.users().drafts().get(userId="me", id=draft_id).execute()
            if draft:
                return True
        except HttpError as error:
            if error.resp.status == 404:
                return False
            else:
                print(f"An error occurred while checking draft existence: {error}")
                time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"Unexpected error: {e}")
            break
    return False


def rebuild_cover_letter(company_name, timeout=300, interval=5):
    pdf_path_pattern = os.path.join('Cover_PDF', f"*{company_name}*.pdf")
    existing_files = glob(pdf_path_pattern)
    for file_path in existing_files:
        os.remove(file_path)

    subprocess.run(['python', 'CoverBuilder.py', company_name], check=True)

    start_time = time.time()
    while time.time() - start_time < timeout:
        generated_files = glob(os.path.join('Cover_PDF', f"*{company_name}.pdf"))
        for generated_file in generated_files:
            if os.path.exists(generated_file) and "OLD" not in generated_file:
                return generated_file
        time.sleep(interval)

    raise TimeoutError(f"PDF generation for {company_name} timed out after {timeout} seconds.")

class ResultsFileModifiedHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback
        self.processed_companies = set()

    def on_modified(self, event):
        if event.src_path.endswith('results.json'):
            self.callback(self.processed_companies)

def process_new_companies(processed_companies, queue):
    try:
        with open(RESULTS_PATH, 'r', encoding='utf-8') as file:
            results = json.load(file)
    except Exception as e:
        print(f"Error loading results.json: {e}")
        return

    for result in results:
        company_name = result['company_name']
        if company_name not in processed_companies:
            print(f"Processing new company: {company_name}")
            queue.put((company_name, result))
            processed_companies.add(company_name)
            
def check_if_message_with_pdf_sent(service, to_emails, company_name):
    try:
        # Rechercher les messages envoyés à l'adresse email donnée
        query = f"to:{to_emails} in:sent"
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])

        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            parts = msg.get('payload', {}).get('parts', [])
            for part in parts:
                filename = part.get('filename')
                if filename and company_name in filename and filename.endswith('.pdf'):
                    return True
        return False
    except Exception as e:
        print(f"An error occurred while checking if message with PDF was sent: {e}")
        return False


def check_drafts(draft_ids, queue):
    service = initialize_gmail_service()
    while True:
        for draft_id, company, result in draft_ids:
            draft_exists = check_draft_existence(service, draft_id)

            to_emails = result['mails'][0]  # Le meilleur e-mail en tant que destinataire
            if not draft_exists:
                if check_if_message_with_pdf_sent(service, to_emails, company):
                    print(f"Message to {to_emails} for {company} with PDF has already been sent and will not be recreated.")
                    draft_ids.remove((draft_id, company, result))
                else:
                    print(f"creating new: {draft_id}")
                    draft_ids.remove((draft_id, company, result))
                    pdf_path_pattern = os.path.join('Cover_PDF', f"*{company}*.pdf")
                    existing_files = glob(pdf_path_pattern)
                    for file_path in existing_files:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    queue.put((company, result))
        time.sleep(10)

def create_and_send_draft(company, result):
    attachments = load_attachments(company)
    to_emails = result['mails'][0]
    bcc_emails = ', '.join(result['mails'][1:])
    subject, body = load_email_info()
    service = initialize_gmail_service()
    
    if not check_if_message_with_pdf_sent(service, to_emails, company):
        draft = create_draft_with_attachment(service, to_emails, subject, body, attachments, None, bcc_emails)
        if draft:
            draft_id = draft['id']
            return draft_id
    else:
        print(f"Message to {to_emails} for {company} with PDF has already been sent. No draft will be created.")
    return None

def main(company_name=None):
    queue = Queue()
    draft_ids = []
    processed_companies = set()
    
    observer = Observer()
    event_handler = ResultsFileModifiedHandler(callback=lambda processed_companies: process_new_companies(processed_companies, queue))
    observer.schedule(event_handler, path='Json_Files', recursive=False)
    observer.start()

    check_thread = threading.Thread(target=check_drafts, args=(draft_ids, queue))
    check_thread.start()

    try:
        if company_name:
            process_new_companies(set([company_name]), queue)
        else:
            process_new_companies(processed_companies, queue)
        while True:
            if not queue.empty():
                company, result = queue.get()
                draft_id = create_and_send_draft(company, result)
                if draft_id:
                    time.sleep(2)
                    draft_ids.append((draft_id, company, result))
                else:
                    queue.put((company, result))
                    
    except KeyboardInterrupt:
        observer.stop()
    except Exception as e:
        print(f"Unexpected error in main loop: {e}")
    finally:
        observer.join()
        check_thread.join()  # Ensure the thread ends properly

if __name__ == "__main__":
    company_name = sys.argv[1] if len(sys.argv) > 1 else None
    main(company_name)
