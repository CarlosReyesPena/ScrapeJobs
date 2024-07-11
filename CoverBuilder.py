import json
import aiofiles
import os
import sys
from groq import Groq
from langdetect import detect
import asyncio
import shutil
import re

RETRY_ATTEMPTS = 20
RETRY_DELAY = 3
MAX_COMPILATION_ATTEMPTS = 3

# Charger l'API key depuis un fichier
async def load_api_key(file_path='groq_api_key.txt'):
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
            return await file.read()
    except Exception as e:
        print(f"Error loading API key: {e}")
        return None

# Configuration de l'API Meta3
api_key = asyncio.run(load_api_key())
client = Groq(api_key=api_key.strip()) if api_key else None

# Fonction pour charger les données du fichier JSON
async def load_results(json_file='Json_Files/results.json'):
    try:
        async with aiofiles.open(json_file, 'r', encoding='utf-8') as file:
            data = await file.read()
        return json.loads(data)
    except Exception as e:
        print(f"Error loading results.json: {e}")
        return []

# Fonction pour charger les prompts à partir des fichiers
async def load_prompts():
    try:
        async with aiofiles.open('Text_Files/promptbody.txt', 'r', encoding='utf-8') as file:
            prompt_body = await file.read()
        async with aiofiles.open('Text_Files/promptbody-norecipient.txt', 'r', encoding='utf-8') as file:
            prompt_body_norecipient = await file.read()
        async with aiofiles.open('Text_Files/promptrecipient.txt', 'r', encoding='utf-8') as file:
            prompt_recipient = await file.read()
        async with aiofiles.open('Text_Files/profil.txt', 'r', encoding='utf-8') as file:
            profile_text = await file.read()
        return prompt_body, prompt_body_norecipient, prompt_recipient , profile_text
    except Exception as e:
        print(f"Error loading prompts: {e}")
        return "", "", "", ""

# Fonction pour extraire le temps d'attente depuis le message d'erreur
def extract_wait_time(error_message):
    match = re.search(r'Please try again in (\d+\.?\d*)s', error_message)
    if match:
        return float(match.group(1))
    match = re.search(r'Please try again in (\d+\.?\d*)m', error_message)
    if match:
        return float(match.group(1)) * 60
    match = re.search(r'Please try again in (\d+\.?\d*)h', error_message)
    if match:
        return float(match.group(1)) * 3600
    return None

def get_final_name(language_code, name):
    language_map = {
        "en": "Cover letter",
        "fr": "Lettre de motivation",
        "es": "Carta de presentación",
        "de": "Anschreiben",
        "it": "Lettera di presentazione",
        "pt": "Carta de apresentação"
    }

    prefix = language_map.get(language_code, "Cover letter")
    final_name = f"{prefix} {name}"
    
    return final_name

# Fonction pour remplacer les balises dans le texte du prompt
def replace_placeholders(prompt_text, company_info, profile_text=None,SelectedDest=None):
    language_map = {
        "en": "English",
        "fr": "French",
        "es": "Spanish",
        "de": "German",
    }

    # Join emails correctly
    all_emails = ", ".join(company_info.get("mails", []))

    # Use the address directly from company_info
    all_addresses = company_info.get("addresses", "")

    # Join personal names correctly
    all_personal_names = ", ".join(company_info.get("personal_names", []))

    # Replace placeholders
    prompt_text = prompt_text.replace('{"company_name"}', company_info.get("company_name", ""))
    prompt_text = prompt_text.replace('{"mails"}', all_emails)
    prompt_text = prompt_text.replace('{"summary"}', company_info.get("summary", ""))
    prompt_text = prompt_text.replace('{"addresses"}', all_addresses)
    prompt_text = prompt_text.replace('{"personal_names"}', all_personal_names)
    if SelectedDest != None:
        prompt_text = prompt_text.replace('{"SelectPerson"}', SelectedDest)

    if profile_text != None:
        prompt_text = prompt_text.replace("{profile.txt}", profile_text)

    # Detect language from the summary or default to English
    summary = company_info.get("summary", "")
    language_code = detect(summary) if summary else 'en'
    language_full = language_map.get(language_code, "English")
    prompt_text = prompt_text.replace("{language}", language_full)
    return prompt_text


def extract_text_from_response(response_text):
    start = response_text.find('{')
    end = response_text.find('}', start)
    if start != -1 and end != -1:
        return response_text[start+1:end]
    return ""

async def generate_content(company_info, prompt,system_promp="", profile_text=None, is_valid_format=None,SelectedDest=None):
    base_prompt = replace_placeholders(prompt, company_info, profile_text,SelectedDest)
    messages = [
        {"role": "system", "content": system_promp},
        {"role": "user", "content": base_prompt}
    ]

    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = client.chat.completions.create(
                messages=messages,
                model="llama3-70b-8192"
            )
            response_text = response.choices[0].message.content
            extracted_text = extract_text_from_response(response_text)
            if extracted_text:
                if is_valid_format is None or is_valid_format(extracted_text):
                    return extracted_text
            raise ValueError(f"Invalid format generated: {extracted_text}")
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(RETRY_DELAY)
    
    return ""

async def save_to_file(filename, content):
    try:
        async with aiofiles.open(filename, 'w', encoding='utf-8') as file:
            await file.write(content)
    except Exception as e:
        print(f"Error saving to file {filename}: {e}")

def rename_existing_file(file_path):
    base, extension = os.path.splitext(file_path)
    suffix = "_OLD_"
    index = 1

    while os.path.exists(file_path):
        new_file_path = f"{base}{suffix}{index}{extension}"
        index += 1
        file_path = new_file_path
    
    return file_path

def clean_up_files(files_to_remove):
    for file_path in files_to_remove:
        if os.path.exists(file_path):
            os.remove(file_path)

async def compile_latex(name: str, timeout: int = 120):
    output_dir = 'Cover_PDF'
    latex_file = './main.tex'
    pdf_output = f'{output_dir}/{name}.pdf'
    pdf_generated = f'{output_dir}/main.pdf'

    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    async def run_pdflatex():
        process = await asyncio.create_subprocess_exec(
            'pdflatex', '-output-directory', output_dir, latex_file,
            stdout=asyncio.subprocess.PIPE,  # Removed since it's not used
            stderr=asyncio.subprocess.PIPE
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except asyncio.TimeoutError:
            process.kill()
            _, stderr = await process.communicate()
            raise TimeoutError(f"Le processus pdflatex a dépassé le temps limite de {timeout} secondes.")
        
        return process.returncode, stderr

    # Check if pdflatex is available
    if not shutil.which('pdflatex'):
        raise FileNotFoundError("Erreur : pdflatex n'a pas été trouvé dans le PATH du système. Assurez-vous que pdflatex est installé et accessible.")

    try:
        returncode, stderr = await run_pdflatex()
        if returncode != 0:
            print(f"Erreur de compilation LaTeX pour {name}")
            print(stderr.decode())
            raise Exception(f"Compilation LaTeX échouée pour {name}")
    except TimeoutError as e:
        print(e)
        raise Exception(f"Compilation LaTeX échouée pour {name} en raison du timeout")

    # Check the compilation result
    if os.path.exists(pdf_output):
        new_pdf_output = rename_existing_file(pdf_output)
        os.rename(pdf_output, new_pdf_output)
    
    os.rename(pdf_generated, pdf_output)

    residual_files = ['Compilation/sujet.txt', 'Compilation/corp.txt', 'Compilation/destinataire.txt']
    latex_residuals = ['aux', 'log', 'out', 'toc', 'synctex.gz']
    for ext in latex_residuals:
        residual_files.append(f'{output_dir}/main.{ext}')
    
    clean_up_files(residual_files)

def set_subject(company_info, language_code):

    subject_map = {
        "en": "Application for a position at {company_name}",
        "fr": "Candidature pour un poste chez {company_name}",
        "es": "Solicitud para un puesto en {company_name}",
        "de": "Bewerbung für eine Position bei {company_name}",
        "it": "Candidatura per una posizione presso {company_name}",
        "pt": "Candidatura para uma posição na {company_name}"
    }
    subject_template = subject_map.get(language_code, "Application for a position at {company_name}")
    subject = subject_template.format(company_name=company_info.get("company_name", ""))
    return subject

async def generate_files(company_info, recipient_manager):
    print(f"generating files for {company_info['company_name']}...")

    recipient_system = "You are an expert building recipient addresses."
    body_system = "Act like a professional career advisor. You have been helping individuals craft compelling and effective job applications for over 20 years. Your expertise spans various industries, allowing you to tailor advice to specific career paths and organizational cultures."

    prompt_body, prompt_body_norecipient, promptrecipient, profile_text = await load_prompts()

    destinataire_content = await generate_content(company_info, promptrecipient, recipient_system, profile_text, is_valid_format)
    
    # Extrait la deuxième ligne du message
    lines = destinataire_content.split('\n')
    NomDest = lines[2] if len(lines) > 2 else ""

    # List of phrases to check against (expand this list as needed)
    generic_phrases = ["droit", "Concern", "corresponda", "betrifft","competenza"]
    
    # Check if NomDest contains any of the generic phrases (case-insensitive)
    if any(phrase.lower() in NomDest.lower() for phrase in generic_phrases):
        corp_content = await generate_content(company_info, prompt_body_norecipient, body_system, profile_text, None, "")
        NomDest = None  # Set to None if it's a generic recipient
    else:
        corp_content = await generate_content(company_info, prompt_body, body_system, profile_text, None, NomDest)
        # Extraire le destinataire de la première ligne non vide du contenu du corps
        lines = corp_content.split('\n')
        first_non_empty_line = next((line.strip() for line in lines if line.strip()), "")
        if first_non_empty_line.endswith(','):
            NomDest = first_non_empty_line[:-1]  # Enlever la virgule à la fin
        else:
            NomDest = first_non_empty_line

    # Update recipient info
    recipient_manager.update(company_info['company_name'], NomDest)
    await recipient_manager.save()
    
    language_code = detect(corp_content)
    sujet_content = set_subject(company_info, language_code)
    
    await save_to_file('Compilation/corp.txt', corp_content)
    await save_to_file('Compilation/destinataire.txt', destinataire_content)
    await save_to_file('Compilation/sujet.txt', sujet_content)

def is_valid_format(text):
    # Définir une expression régulière pour les caractères non valides
    invalid_characters = re.compile(r'[!@#$%^&*+=[\]{}|\\:;"<>?\/`~]')
    
    # Supprimer les lignes vides et espaces en début/fin des lignes restantes
    lines = text.strip().split('\n')
    
    # Vérifier que le nombre de lignes est entre 2 et 5
    if not (2 <= len(lines) <= 5):
        return False
    
    for line in lines:
        # Vérifier la longueur de chaque ligne
        if len(line) > 40:
            return False
        
        if line != lines[0]:
            # Vérifier la présence de caractères non valides
            if invalid_characters.search(line):
                return False
    
    return True

class RecipientManager:
    def __init__(self):
        self.recipients = {}
        self.file_path = 'Json_Files/recipients.json'

    async def load(self):
        try:
            async with aiofiles.open(self.file_path, 'r', encoding='utf-8') as file:
                self.recipients = json.loads(await file.read())
        except FileNotFoundError:
            self.recipients = {}
        except json.JSONDecodeError:
            print(f"Error decoding {self.file_path}. Starting with an empty dictionary.")
            self.recipients = {}

    async def save(self):
        async with aiofiles.open(self.file_path, 'w', encoding='utf-8') as file:
            await file.write(json.dumps(self.recipients, ensure_ascii=False, indent=4))

    def update(self, company_name: str, recipient: str):
        if recipient:
            self.recipients[company_name] = recipient
        elif company_name in self.recipients:
            del self.recipients[company_name]

    def get(self, company_name: str) -> str:
        return self.recipients.get(company_name)

async def build_covers(json_file='Json_Files/results.json', specific_company_name=None):
    data = await load_results(json_file)
    recipient_manager = RecipientManager()
    await recipient_manager.load()

    for company_info in data:
        name = company_info["company_name"]
        if specific_company_name and name != specific_company_name:
            continue
        print(f"Traitement de {name}...")
        
        name = get_final_name(detect(company_info.get("summary", "")), name)
        
        for attempt in range(MAX_COMPILATION_ATTEMPTS):
            await generate_files(company_info, recipient_manager)
            print(f"Fichiers générés pour {name}.")   
            try:
                await compile_latex(name)
                print(f"Traitement de {name} terminé avec succès.\n")
                break  # Sortir de la boucle si la compilation a réussi
            except Exception as e:
                print(f"Tentative {attempt + 1}/{MAX_COMPILATION_ATTEMPTS} échouée pour {name}. Erreur: {e}")
                await asyncio.sleep(RETRY_DELAY)
        else:
            print(f"Échec de la génération et de la compilation pour {name} après {MAX_COMPILATION_ATTEMPTS} tentatives.")

if __name__ == "__main__":
    specific_company_name = None
    if len(sys.argv) > 1:
        specific_company_name = sys.argv[1]
    asyncio.run(build_covers(specific_company_name=specific_company_name))