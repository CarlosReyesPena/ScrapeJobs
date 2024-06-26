import os
import json
import base64
import mimetypes
from email.message import EmailMessage
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
import threading  # Importation du module threading

# Charger les informations de l'email à partir d'un fichier
def load_email_info(file_path='Text_Files/email_info.txt'):
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

# Charger les informations d'identification à partir du fichier credentials.json
def load_credentials():
    SCOPES = ['https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/gmail.compose']
    creds = None
    token_path = 'token.json'
    cred_path = 'Json_Files/credentials.json'

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

def build_file_part(file):
    """Creates a MIME part for a file.

    Args:
        file: The path to the file to be attached.

    Returns:
        A MIME part that can be attached to a message.
    """
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

def gmail_create_draft_with_attachment(to_emails, cc_emails, subject, body, attachments):
    """Create and insert a draft email with attachment.
    Print the returned draft's message and id.
    Returns: Draft object, including draft id and message meta data.
    """
    creds = load_credentials()

    try:
        # create gmail api client
        service = build("gmail", "v1", credentials=creds)
        mime_message = MIMEMultipart()  # Use MIMEMultipart for messages with attachments

        # headers
        mime_message["To"] = to_emails
        mime_message["Cci"] = cc_emails
        mime_message["Subject"] = subject

        # text
        mime_message.attach(MIMEText(body, 'plain'))

        # attachment
        for file in attachments:
            mime_message.attach(build_file_part(file))

        encoded_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()

        create_draft_request_body = {"message": {"raw": encoded_message}}
        # pylint: disable=E1101
        draft = (
            service.users()
            .drafts()
            .create(userId="me", body=create_draft_request_body)
            .execute()
        )
        print(f'Draft id: {draft["id"]}\nDraft message: {draft["message"]}')
    except HttpError as error:
        print(f"An error occurred: {error}")
        draft = None
    return draft

def gmail_send_draft(draft_id):
    """Send a draft email.
    Print the returned message id.
    Returns: Message object, including message id.
    """
    creds = load_credentials()

    try:
        # create gmail api client
        service = build("gmail", "v1", credentials=creds)

        # pylint: disable=E1101
        send_draft = (
            service.users()
            .drafts()
            .send(userId="me", body={"id": draft_id})
            .execute()
        )
        print(f'Message Id: {send_draft["id"]}')
    except HttpError as error:
        print(f"An error occurred: {error}")
        send_draft = None
    return send_draft

def check_draft_existence(service, draft_id):
    """Check if a draft exists.
    Returns True if the draft exists, False otherwise.
    """
    try:
        draft = service.users().drafts().get(userId="me", id=draft_id).execute()
        return draft is not None
    except HttpError as error:
        if error.resp.status == 404:
            return False
        else:
            print(f"An error occurred: {error}")
            return False

def rebuild_cover_letter(company_name):
    """Rebuild the cover letter PDF for the specified company."""
    pdf_path = os.path.join('Cover_PDF', f"{company_name}.pdf")
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    
    # Call CoverBuilder to rebuild the letter
    subprocess.run(['python', 'CoverBuilder.py', company_name], check=True)

class ResultsFileModifiedHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback
        self.processed_companies = set()

    def on_modified(self, event):
        if event.src_path.endswith('results.json'):
            self.callback(self.processed_companies)

def process_new_companies(processed_companies):
    subject, body = load_email_info('Text_Files/email_info.txt')

    with open('Json_Files/results.json', 'r', encoding='utf-8') as file:
        results = json.load(file)

    creds = load_credentials()
    service = build("gmail", "v1", credentials=creds)

    draft_ids = []

    for result in results:
        company_name = result['company_name']
        if company_name not in processed_companies:
            to_emails = result['mails'][0]  # Le meilleur e-mail en tant que destinataire
            cc_emails = ', '.join(result['mails'][1:])  # Les autres e-mails en CC

            # Charger tous les fichiers du dossier attachments
            attachments = [os.path.join('attachments', f) for f in os.listdir('attachments')]

            # Créer le PDF de la lettre de motivation s'il n'existe pas
            pdf_path = os.path.join('Cover_PDF', f"{result['company_name']}.pdf")
            if not os.path.exists(pdf_path):
                rebuild_cover_letter(result['company_name'])

            # Ajouter la lettre de motivation en premier
            attachments.insert(0, pdf_path)

            # Créer le brouillon
            draft = gmail_create_draft_with_attachment(to_emails, cc_emails, subject, body, attachments)

            if draft:
                processed_companies.add(company_name)
                print(f"Draft created for {company_name}")
                draft_ids.append((draft['id'], company_name, result))

    def check_drafts():
        while True:
            for draft_id, company, result in draft_ids.copy():
                if not check_draft_existence(service, draft_id):
                    print(f"Draft with ID {draft_id} has been deleted.")
                    draft_ids.remove((draft_id, company, result))
                    # Rebuild the cover letter
                    rebuild_cover_letter(company)
                    # Create a new draft
                    new_attachments.insert(0, os.path.join('Cover_PDF', f"{company}.pdf"))
                    new_attachments = [os.path.join('attachments', f) for f in os.listdir('attachments')]
                    new_draft = gmail_create_draft_with_attachment(result['mails'][0], ', '.join(result['mails'][1:]), subject, body, new_attachments)
                    if new_draft:
                        draft_ids.append((new_draft['id'], company, result))
            time.sleep(10)

    check_thread = threading.Thread(target=check_drafts)
    check_thread.start()

def main(company_name=None):
    observer = Observer()
    event_handler = ResultsFileModifiedHandler(callback=process_new_companies)
    observer.schedule(event_handler, path='Json_Files', recursive=False)
    observer.start()

    try:
        if company_name:
            process_new_companies(set([company_name]))
        else:
            process_new_companies(set())
        
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()

if __name__ == "__main__":
    import sys
    company_name = sys.argv[1] if len(sys.argv) > 1 else None
    main(company_name)
