import os
import json
import base64
import mimetypes
import ssl
import sys
import urllib3
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
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging
from concurrent.futures import ThreadPoolExecutor
import requests
import CoverBuilder

# SSL Configuration
ssl._create_default_https_context = ssl._create_unverified_context

# Constants
RETRY_ATTEMPTS = 5
RETRY_DELAY = 3
EMAIL_INFO_PATH = 'Json_Files\\email_info.json'
CREDENTIALS_PATH = 'Json_Files\\credentials.json'
TOKEN_PATH = 'token.json'
RESULTS_PATH = 'Json_Files\\results.json'
ATTACHMENTS_DIRS = ['attachments\\CV', 'attachments\\Others']
DRAFTS_JSON_PATH = 'Json_Files\\drafts.json'
MAX_CONCURRENT_DRAFTS = 20
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.readonly'
]

LOGGIN = 'INFO'

def LOGGIN_LEVEL(level):
    if level == 'DEBUG':
        return logging.DEBUG
    elif level == 'INFO':
        return logging.INFO
    elif level == 'WARNING':
        return logging.WARNING
    elif level == 'ERROR':
        return logging.ERROR
    elif level == 'CRITICAL':
        return logging.CRITICAL
    else:
        return logging.NOTSET

# Logging Configuration
logging.basicConfig(level=LOGGIN_LEVEL(LOGGIN), format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# SSL Diagnostic Function
def print_ssl_info():
    print(f"Python version: {sys.version}")
    print(f"OpenSSL version: {ssl.OPENSSL_VERSION}")
    print(f"SSL default version: {ssl.PROTOCOL_TLS}")
    context = ssl.create_default_context()
    print(f"SSL context - Minimum version: {context.minimum_version}")
    print(f"SSL context - Maximum version: {context.maximum_version}")
    print(f"SSL context - Verify mode: {context.verify_mode}")
    print(f"urllib3 version: {urllib3.__version__}")

print_ssl_info()

@dataclass
class EmailInfo:
    subject: str
    body: str

@dataclass
class CompanyResult:
    company_name: str
    mails: List[str]

class GmailService:
    def __init__(self):
        self.service = None
        self.credentials = None
        self.logger = logging.getLogger(__name__)

    async def initialize(self):
        self.credentials = await self.load_credentials()
        self.service = build("gmail", "v1", credentials=self.credentials, cache_discovery=False)

    async def create_draft(self, to_emails: str, subject: str, body: str, attachments: List[str], cc_emails: Optional[str] = None, bcc_emails: Optional[str] = None) -> Optional[str]:
        try:
            mime_message = self.create_mime_message(to_emails, subject, body, attachments, cc_emails, bcc_emails)
            encoded_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
            create_draft_request_body = {"message": {"raw": encoded_message}}

            headers = {
                "Authorization": f"Bearer {self.credentials.token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                headers=headers,
                json=create_draft_request_body
            )
            
            if response.status_code == 200:
                draft = response.json()
                self.logger.info(f"Draft created with ID: {draft['id']}")
                return draft['id']
            else:
                self.logger.error(f"Failed to create draft. Status code: {response.status_code}, Response: {response.text}")
                return None

        except Exception as e:
            self.logger.exception(f"Unexpected error in create_draft: {e}")
            raise

    async def refresh_token(self):
        try:
            self.credentials = await self.load_credentials(force_refresh=True)
            self.service = build("gmail", "v1", credentials=self.credentials, cache_discovery=False)
        except Exception as e:
            self.logger.error(f"Failed to refresh token: {e}")
            raise

    async def load_credentials(self, force_refresh=False):
        creds = None
        if os.path.exists(TOKEN_PATH) and not force_refresh:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

        if not creds or not creds.valid or force_refresh:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    self.logger.warning("Failed to refresh token. Initiating new authentication flow.")
                    creds = None

            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
                creds = await asyncio.to_thread(flow.run_local_server, port=0)
            
            async with aiofiles.open(TOKEN_PATH, 'w') as token:
                await token.write(creds.to_json())
        
        return creds

    def create_mime_message(self, to_emails: str, subject: str, body: str, attachments: List[str], cc_emails: Optional[str], bcc_emails: Optional[str]) -> MIMEMultipart:
        mime_message = MIMEMultipart()
        mime_message["To"] = to_emails
        if cc_emails:
            mime_message["Cc"] = cc_emails
        if bcc_emails:
            mime_message["Bcc"] = bcc_emails
        mime_message["Subject"] = subject
        mime_message.attach(MIMEText(body, 'plain'))

        for file in attachments:
            mime_message.attach(self.build_file_part(file))

        return mime_message

    def build_file_part(self, file: str) -> MIMEBase:
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

    async def check_draft_existence(self, draft_id: str) -> bool:
        try:
            draft = await asyncio.to_thread(self.service.users().drafts().get(userId="me", id=draft_id).execute)
            return bool(draft)
        except HttpError as error:
            if error.resp.status == 404:
                return False
            else:
                self.logger.error(f"HTTP error checking draft existence: {error}")
                raise
        except Exception as e:
            self.logger.exception(f"Unexpected error in check_draft_existence: {e}")
            return False

class DraftsManager:
    def __init__(self):
        self.drafts: Dict[str, str] = {}
        

    def load(self):
        if not os.path.exists(DRAFTS_JSON_PATH):
            return

        with open(DRAFTS_JSON_PATH, 'r', encoding='utf-8') as f:
            self.drafts = json.load(f)

    def save(self):
        with open(DRAFTS_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.drafts, f, indent=4)

    def add(self, draft_id: str, company: str):
        self.drafts[draft_id] = company
        self.save()

    def remove(self, draft_id: str):
        if draft_id in self.drafts:
            del self.drafts[draft_id]
            self.save()

    async def verify_and_cleanup(self, gmail_service: GmailService):
        valid_drafts = {}
        for draft_id, company in self.drafts.items():
            if await gmail_service.check_draft_existence(draft_id):
                valid_drafts[draft_id] = company
            else:
                logger.info(f"Draft {draft_id} for {company} does not exist anymore. Removing from JSON and erasing PDF file.")
                await EmailSender.remove_pdf_file(company)

        
        self.drafts = valid_drafts
        self.save()

class EmailSender:
    def __init__(self):
        self.gmail_service = GmailService()
        self.drafts_manager = DraftsManager()
        self.recipient_manager = RecipientManager()
        self.queue = asyncio.Queue()
        self.processed_companies = set()
        self.draft_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DRAFTS)
        self.executor = ThreadPoolExecutor()
        self.logger = logging.getLogger(__name__)
        self.rebuild_lock = asyncio.Lock()

    async def run(self):
        await self.initialize()

        observer = Observer()
        event_handler = ResultsFileModifiedHandler(self.process_new_companies, asyncio.get_running_loop())
        observer.schedule(event_handler, path='Json_Files', recursive=False)
        observer.start()

        try:
            await self.process_new_companies()
            tasks = [
                self.check_drafts(),
                self.process_queue()
            ]
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            observer.stop()
        except Exception as e:
            self.logger.exception(f"Unexpected error in main loop: {e}")
        finally:
            observer.join()

    async def initialize(self):
        await self.gmail_service.initialize()
        self.drafts_manager.load()
        await self.drafts_manager.verify_and_cleanup(self.gmail_service)

    async def process_new_companies(self):
        try:
            async with aiofiles.open(RESULTS_PATH, 'r', encoding='utf-8') as file:
                results = json.loads(await file.read())
        except Exception as e:
            logger.exception(f"Error loading results.json: {e}")
            return

        for result in results:
            company_name = result['company_name']
            if company_name not in self.processed_companies:
                logger.info(f"Processing new company: {company_name}")
                await self.queue.put(CompanyResult(company_name, result['mails']))
                self.processed_companies.add(company_name)

    async def check_drafts(self):
        while True:
            for draft_id, company in list(self.drafts_manager.drafts.items()):
                draft_exists = await self.gmail_service.check_draft_existence(draft_id)
                if not draft_exists:
                    self.drafts_manager.remove(draft_id)
                    logger.info(f"Draft {draft_id} deleted for {company}")
                    
                    # Supprimer le fichier PDF associé
                    await self.remove_pdf_file(company)
                    
                    # Vérifier si des adresses e-mail sont disponibles pour cette entreprise
                    company_info = await self.get_company_info(company)
                    if company_info and company_info.mails:
                        logger.info(f"Creating new draft for {company}")
                        await self.queue.put(CompanyResult(company, company_info.mails))
                    else:
                        logger.warning(f"No email addresses available for {company}. Skipping draft recreation.")
            
            await asyncio.sleep(5)

    async def remove_pdf_file(self, company_name: str):
        try:
            pdf_pattern = os.path.join('Cover_PDF', f"*{company_name}*.pdf")
            pdf_files = glob(pdf_pattern)
            for pdf_file in pdf_files:
                if os.path.exists(pdf_file):
                    os.remove(pdf_file)
                    logger.info(f"Removed PDF file: {pdf_file}")
        except Exception as e:
            logger.exception(f"Error removing PDF file for {company_name}: {e}")

    async def get_company_info(self, company_name: str) -> Optional[CompanyResult]:
        try:
            async with aiofiles.open(RESULTS_PATH, 'r', encoding='utf-8') as file:
                results = json.loads(await file.read())
            
            for result in results:
                if result['company_name'] == company_name:
                    return CompanyResult(company_name, result.get('mails', []))
            
            return None
        except Exception as e:
            logger.exception(f"Error loading company info for {company_name}: {e}")
            return None

    async def create_and_send_draft(self, company: str, mails: List[str]):
        async with self.draft_semaphore:
            attachments = await self.load_attachments(company)
            to_emails = mails[0]
            bcc_emails = ', '.join(mails[1:])
            recipient = self.recipient_manager.get(company)
            email_info = await self.load_email_info(attachments, recipient)
            subject = f"{email_info.subject} {company}"
            
            draft_id = await self.gmail_service.create_draft(to_emails, subject, email_info.body, attachments, None, bcc_emails)
            if draft_id:
                self.drafts_manager.add(draft_id, company)
                return draft_id
            return None

    async def load_attachments(self, company_name: str) -> List[str]:
        attachments = []

        generated_files = glob(os.path.join('Cover_PDF', f"*{company_name}*.pdf"))
        pdf_path = next((file for file in generated_files if os.path.exists(file) and "OLD" not in file), None)

        if not pdf_path:
            pdf_path = await self.build_cover_letter(company_name)
            await self.recipient_manager.load()
        else:
            logger.info(f"Using existing PDF for {company_name}")

        attachments.append(pdf_path)

        for attachment_dir in ATTACHMENTS_DIRS:
            if os.path.exists(attachment_dir) and os.listdir(attachment_dir):
                attachments.extend([os.path.join(attachment_dir, f) for f in os.listdir(attachment_dir)])
        return attachments

    async def build_cover_letter(self, company_name: str) -> str:
            for attempt in range(RETRY_ATTEMPTS):
                try:
                    async with self.rebuild_lock:
                        await CoverBuilder.build_covers('Json_Files/results.json', specific_company_name=company_name)

                    generated_files = glob(os.path.join('Cover_PDF', f"*{company_name}.pdf"))
                    for generated_file in generated_files:
                        if os.path.exists(generated_file) and "OLD" not in generated_file:
                            return generated_file

                    raise FileNotFoundError(f"PDF generation for {company_name} failed to produce a valid file.")

                except FileNotFoundError as fnf_error:
                    logger.error(f"Attempt {attempt + 1}/{RETRY_ATTEMPTS} - {fnf_error}")
                    if attempt + 1 < RETRY_ATTEMPTS:
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        raise
                except Exception as e:
                    logger.exception(f"An error occurred while rebuilding cover letter for {company_name}: {e}")
                    if attempt + 1 < RETRY_ATTEMPTS:
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        raise
            raise FileNotFoundError(f"Failed to generate PDF for {company_name} after {RETRY_ATTEMPTS} attempts.")

    async def load_email_info(self, attachments: List[str], recipient: Optional[str]) -> EmailInfo:
        try:
            language = self.detect_language(attachments)

            async with aiofiles.open(EMAIL_INFO_PATH, 'r', encoding='utf-8') as file:
                email_info_data = json.loads(await file.read())

                for email_info in email_info_data['emails']:
                    if email_info['language'] == language:
                        subject = email_info.get('subject', '')
                        if recipient:
                            body = email_info.get('body_with_recipient', '')
                            body = body.replace("{recipient}", recipient)
                        else:
                            body = email_info.get('body_without_recipient', '')
                        return EmailInfo(subject, body)

            return EmailInfo("Default Subject", "Default Body")
        except Exception as e:
            logger.exception(f"Error loading email info: {e}")
            return EmailInfo("", "")

    def detect_language(self, attachments: List[str]) -> str:
        language_phrases = {
            "English": "Cover letter",
            "French": "Lettre de motivation",
            "Spanish": "Carta de presentación",
            "German": "Anschreiben",
            "Italian": "Lettera di presentazione",
            "Portuguese": "Carta de apresentação"
        }
        for attachment in attachments:
            for lang, phrase in language_phrases.items():
                if phrase in attachment:
                    return lang
        return "English"  # Default to English

    async def process_queue(self):
        while True:
            tasks = []
            for _ in range(MAX_CONCURRENT_DRAFTS):
                if not self.queue.empty():
                    company_result = await self.queue.get()
                    task = asyncio.create_task(self.process_draft(company_result))
                    tasks.append(task)
            if tasks:
                await asyncio.gather(*tasks)
            else:
                await asyncio.sleep(0)

    async def process_draft(self, company_result):
        if company_result.company_name in self.drafts_manager.drafts.values():
            logger.info(f"Draft for {company_result.company_name} already exists. Skipping.")
        else:
            draft_id = await self.create_and_send_draft(company_result.company_name, company_result.mails)
            if draft_id:
                logger.info(f"Successfully created draft for {company_result.company_name}")
            else:
                logger.error(f"Draft creation failed for {company_result.company_name}")
                await self.queue.put(company_result)

class ResultsFileModifiedHandler(FileSystemEventHandler):
    def __init__(self, callback, loop):
        self.callback = callback
        self.loop = loop

    def on_modified(self, event):
        if event.src_path.endswith('results.json'):
            asyncio.run_coroutine_threadsafe(self.callback(), self.loop)

class RecipientManager:
    def __init__(self):
        self.recipients = {}
        self.file_path = 'Json_Files/recipients.json'

    async def load(self,company_name: str = None):
        try:
            async with aiofiles.open(self.file_path, 'r', encoding='utf-8') as file:
                self.recipients = json.loads(await file.read())
            if company_name:
                return self.recipients.get(company_name)
        except FileNotFoundError:
            self.recipients = {}
        except json.JSONDecodeError:
            print(f"Error decoding {self.file_path}. Starting with an empty dictionary.")
            self.recipients = {}
        return None

    async def save(self):
        async with aiofiles.open(self.file_path, 'w', encoding='utf-8') as file:
            await file.write(json.dumps(self.recipients, ensure_ascii=False, indent=4))

    def get(self, company_name: str) -> Optional[str]:
        return self.recipients.get(company_name)

async def main():
    email_sender = EmailSender()
    await email_sender.run()

if __name__ == "__main__":
    asyncio.run(main())