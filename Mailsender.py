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
import asyncio
from glob import glob
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import aiofiles
import sys

import CoverBuilder  # Import direct de CoverBuilder pour appel direct

# Constantes
RETRY_ATTEMPTS = 5
RETRY_DELAY = 3
EMAIL_INFO_PATH = 'Json_Files/email_info.json'
CREDENTIALS_PATH = 'Json_Files/credentials.json'
TOKEN_PATH = 'token.json'
RESULTS_PATH = 'Json_Files/results.json'
ATTACHMENTS_DIRS = ['attachments/CV', 'attachments/Others']
DRAFTS_JSON_PATH = 'Json_Files/drafts.json'
MAX_CONCURRENT_DRAFTS = 5  # Nombre maximal de brouillons pouvant être créés simultanément

LANGUAGE_PHRASES = {
    "English": "Cover letter",
    "French": "Lettre de motivation",
    "Spanish": "Carta de presentación",
    "German": "Anschreiben",
    "Italian": "Lettera di presentazione",
    "Portuguese": "Carta de apresentação"
}

SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.readonly'
]

class EmailManager:
    async def load_credentials(self):
        creds = None
        if os.path.exists(TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
                creds = await asyncio.to_thread(flow.run_local_server, port=0)
            async with aiofiles.open(TOKEN_PATH, 'w') as token:
                await token.write(creds.to_json())
        return creds

    async def initialize_gmail_service(self):
        creds = await self.load_credentials()
        try:
            return build("gmail", "v1", credentials=creds)
        except Exception as e:
            print(f"Error initializing Gmail service: {e}")
            return None

    async def load_email_info(self, attachments):
        try:
            language = await self.detect_language(attachments)
            async with aiofiles.open(EMAIL_INFO_PATH, 'r', encoding='utf-8') as file:
                email_info_data = json.loads(await file.read())
                for email_info in email_info_data['emails']:
                    if email_info['language'] == language:
                        subject = email_info.get('subject', '')
                        body = email_info.get('body', '')
                        return subject, body
            return "Default Subject", "Default Body"
        except Exception as e:
            print(f"Error loading email info: {e}")
            return "", ""

    async def detect_language(self, attachments):
        for attachment in attachments:
            for lang, phrase in LANGUAGE_PHRASES.items():
                if phrase in attachment:
                    return lang
        return "English"  # Default to English

    async def build_file_part(self, file):
        content_type, encoding = mimetypes.guess_type(file)
        if content_type is None or encoding is not None:
            content_type = "application/octet-stream"
        main_type, sub_type = content_type.split("/", 1)
        async with aiofiles.open(file, "rb") as f:
            if main_type == "text":
                msg = MIMEText(await f.read().decode(), _subtype=sub_type)
            elif main_type == "image":
                msg = MIMEImage(await f.read(), _subtype=sub_type)
            elif main_type == "audio":
                msg = MIMEAudio(await f.read(), _subtype=sub_type)
            else:
                msg = MIMEBase(main_type, sub_type)
                msg.set_payload(await f.read())
                encoders.encode_base64(msg)
        filename = os.path.basename(file)
        msg.add_header("Content-Disposition", "attachment", filename=filename)
        return msg

    async def load_attachments(self, company_name):
        attachments = []
        generated_files = glob(os.path.join('Cover_PDF', f"*{company_name}*.pdf"))
        pdf_path = next((file for file in generated_files if os.path.exists(file) and "OLD" not in file), None)
        if not pdf_path:
            raise FileNotFoundError(f"No PDF found for {company_name}")
        attachments.append(pdf_path)
        for attachment_dir in ATTACHMENTS_DIRS:
            if os.path.exists(attachment_dir) and os.listdir(attachment_dir):
                attachments.extend([os.path.join(attachment_dir, f) for f in os.listdir(attachment_dir)])
        return attachments

class DraftManager(EmailManager):
    def __init__(self):
        super().__init__()
        self.rebuild_lock = asyncio.Lock()
        self.draft_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DRAFTS)
        self.failed_drafts = set()
        self.draft_ids = []

    @staticmethod
    def load_drafts_json():
        if not os.path.exists(DRAFTS_JSON_PATH):
            return {}
        with open(DRAFTS_JSON_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def save_drafts_json(drafts):
        with open(DRAFTS_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(drafts, f, indent=4)

    async def verify_and_cleanup_drafts(self, service, drafts):
        valid_drafts = {}
        for draft_id, company in drafts.items():
            if await check_draft_existence(service, draft_id):
                valid_drafts[draft_id] = company
            else:
                print(f"Draft {draft_id} for {company} does not exist anymore. Removing from JSON.")
        self.save_drafts_json(valid_drafts)
        return valid_drafts

    async def rebuild_cover_letter(self, company_name):
        async with self.rebuild_lock:
            for attempt in range(RETRY_ATTEMPTS):
                try:
                    pdf_path_pattern = os.path.join('Cover_PDF', f"*{company_name}*.pdf")
                    existing_files = glob(pdf_path_pattern)
                    for file_path in existing_files:
                        os.remove(file_path)
                    await CoverBuilder.build_covers('Json_Files/results.json', specific_company_name=company_name)
                    generated_files = glob(os.path.join('Cover_PDF', f"*{company_name}.pdf"))
                    for generated_file in generated_files:
                        if os.path.exists(generated_file) and "OLD" not in generated_file:
                            return generated_file
                    raise FileNotFoundError(f"PDF generation for {company_name} failed to produce a valid file.")
                except FileNotFoundError as fnf_error:
                    print(f"Attempt {attempt + 1}/{RETRY_ATTEMPTS} - {fnf_error}")
                    if attempt + 1 < RETRY_ATTEMPTS:
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        self.failed_drafts.add(company_name)
                        raise
                except Exception as e:
                    print(f"An error occurred while rebuilding cover letter for {company_name}: {e}")
                    if attempt + 1 < RETRY_ATTEMPTS:
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        self.failed_drafts.add(company_name)
                        raise
            raise FileNotFoundError(f"Failed to generate PDF for {company_name} after {RETRY_ATTEMPTS} attempts.")

    async def create_draft_with_attachment(self, service, to_emails, subject, body, attachments, cc_emails=None, bcc_emails=None):
        mime_message = MIMEMultipart()
        mime_message["To"] = to_emails
        if cc_emails:
            mime_message["Cc"] = cc_emails
        if bcc_emails:
            mime_message["Bcc"] = bcc_emails
        mime_message["Subject"] = subject
        mime_message.attach(MIMEText(body, 'plain'))
        for file in attachments:
            mime_message.attach(await self.build_file_part(file))
        encoded_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
        create_draft_request_body = {"message": {"raw": encoded_message}}
        for attempt in range(RETRY_ATTEMPTS):
            try:
                draft = await asyncio.to_thread(service.users().drafts().create(userId="me", body=create_draft_request_body).execute)
                print(f"Draft created with ID: {draft['id']}")
                return draft
            except HttpError as error:
                print(f"An error occurred: {error}")
                await asyncio.sleep(RETRY_DELAY)
            except Exception as e:
                print(f"Unexpected error: {e}")
                break
        return None

    async def create_and_send_draft(self, company, result):
        async with self.draft_semaphore:
            try:
                attachments = await self.load_attachments(company)
            except FileNotFoundError:
                await self.rebuild_cover_letter(company)
                attachments = await self.load_attachments(company)
            
            to_emails = result['mails'][0]
            bcc_emails = ', '.join(result['mails'][1:])
            subject, body = await self.load_email_info(attachments)
            service = await self.initialize_gmail_service()
            subject = f"{subject} {company}"
            if not await check_if_message_with_pdf_sent(service, to_emails, company):
                draft = await self.create_draft_with_attachment(service, to_emails, subject, body, attachments, None, bcc_emails)
                if draft:
                    draft_id = draft['id']
                    drafts = self.load_drafts_json()
                    drafts[draft_id] = company
                    self.save_drafts_json(drafts)
                    return draft_id
            else:
                print(f"Message to {to_emails} for {company} with PDF has already been sent. No draft will be created.")
            return None

    async def process_queue(self, queue, processed_companies, company_name):
        if company_name:
            await process_new_companies(set([company_name]), queue)
        else:
            await process_new_companies(processed_companies, queue)
        while True:
            if not queue.empty():
                company, result = await queue.get()
                if company in self.failed_drafts:
                    print(f"Draft creation for {company} has previously failed. Skipping.")
                elif any(company == draft_company for _, draft_company, _ in self.draft_ids):
                    print(f"Draft for {company} already exists. Skipping.")
                else:
                    draft_id = await self.create_and_send_draft(company, result)
                    if draft_id:
                        self.draft_ids.append((draft_id, company, result))
                    else:
                        print(f"Draft creation failed for {company}")
                        await queue.put((company, result))
            await asyncio.sleep(0)

    async def check_drafts(self, queue):
        service = await self.initialize_gmail_service()
        while True:
            for draft_id, company, result in self.draft_ids[:]:
                draft_exists = await check_draft_existence(service, draft_id)
                to_emails = result['mails'][0] if result else None
                if not draft_exists:
                    drafts = self.load_drafts_json()
                    if draft_id in drafts:
                        del drafts[draft_id]
                        self.save_drafts_json(drafts)
                    if result and await check_if_message_with_pdf_sent(service, to_emails, company):
                        print(f"Message to {to_emails} for {company} with PDF has already been sent and will not be recreated.")
                    else:
                        pdf_path_pattern = os.path.join('Cover_PDF', f"*{company}*.pdf")
                        existing_files = glob(pdf_path_pattern)
                        for file_path in existing_files:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        print(f"Draft {draft_id} deleted, creating new draft for {company}")
                        await queue.put((company, result))
                    self.draft_ids.remove((draft_id, company, result))
            await asyncio.sleep(5)

class ResultsFileModifiedHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback
        self.processed_companies = set()

    def on_modified(self, event):
        if event.src_path.endswith('results.json'):
            self.callback(self.processed_companies)

async def process_new_companies(processed_companies, queue):
    try:
        async with aiofiles.open(RESULTS_PATH, 'r', encoding='utf-8') as file:
            results = json.loads(await file.read())
    except Exception as e:
        print(f"Error loading results.json: {e}")
        return
    for result in results:
        company_name = result['company_name']
        if company_name not in processed_companies:
            print(f"Processing new company: {company_name}")
            await queue.put((company_name, result))
            processed_companies.add(company_name)

async def check_if_message_with_pdf_sent(service, to_emails, company_name):
    try:
        query = f"to:{to_emails} in:sent"
        results = await asyncio.to_thread(service.users().messages().list(userId='me', q=query).execute)
        messages = results.get('messages', [])
        for message in messages:
            msg = await asyncio.to_thread(service.users().messages().get(userId='me', id=message['id']).execute)
            parts = msg.get('payload', {}).get('parts', [])
            for part in parts:
                filename = part.get('filename')
                if filename and company_name in filename and filename.endswith('.pdf'):
                    return True
        return False
    except Exception as e:
        print(f"An error occurred while checking if message with PDF was sent: {e}")
        return False

async def check_draft_existence(service, draft_id):
    for attempt in range(RETRY_ATTEMPTS):
        try:
            draft = await asyncio.to_thread(service.users().drafts().get(userId="me", id=draft_id).execute)
            if draft:
                return True
        except HttpError as error:
            if error.resp.status == 404:
                return False
            else:
                print(f"An error occurred while checking draft existence: {error}")
                await asyncio.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"Unexpected error: {e}")
            break
    return False

async def main_sender(company_name=None):
    queue = asyncio.Queue()
    processed_companies = set()
    draft_manager = DraftManager()
    observer = Observer()
    event_handler = ResultsFileModifiedHandler(callback=lambda processed_companies: asyncio.run(process_new_companies(processed_companies, queue)))
    observer.schedule(event_handler, path='Json_Files', recursive=False)
    observer.start()
    service = await draft_manager.initialize_gmail_service()
    drafts = await draft_manager.load_drafts_json()
    valid_drafts = await draft_manager.verify_and_cleanup_drafts(service, drafts)
    draft_manager.draft_ids = [(draft_id, company, None) for draft_id, company in valid_drafts.items()]
    try:
        await asyncio.gather(
            draft_manager.check_drafts(queue),
            draft_manager.process_queue(queue, processed_companies, company_name)
        )
    except KeyboardInterrupt:
        observer.stop()
    except Exception as e:
        print(f"Unexpected error in main loop: {e}")
    finally:
        observer.join()

if __name__ == "__main__":
    company_name = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main_sender(company_name))
