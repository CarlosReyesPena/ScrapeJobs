import json
import subprocess
import os
import sys
from groq import Groq
from langdetect import detect
import time

RETRY_ATTEMPTS = 20
RETRY_DELAY = 5

# Charger l'API key depuis un fichier
def load_api_key(file_path='groq_api_key.txt'):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read().strip()
    except Exception as e:
        print(f"Error loading API key: {e}")
        return None

# Configuration de l'API Meta3
api_key = load_api_key()
client = Groq(api_key=api_key) if api_key else None

# Fonction pour charger les données du fichier JSON
def load_results(json_file='Json_Files/results.json'):
    try:
        with open(json_file, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data
    except Exception as e:
        print(f"Error loading results.json: {e}")
        return []

# Fonction pour charger les prompts à partir des fichiers
def load_prompts():
    try:
        with open('Text_Files/promptcorp.txt', 'r', encoding='utf-8') as file:
            prompt_corp = file.read()
        with open('Text_Files/promptdestinataire.txt', 'r', encoding='utf-8') as file:
            prompt_destinataire = file.read()
        with open('Text_Files/promptsujet.txt', 'r', encoding='utf-8') as file:
            prompt_sujet = file.read()
        with open('Text_Files/profil.txt', 'r', encoding='utf-8') as file:
            profile_text = file.read()
        return prompt_corp, prompt_destinataire, prompt_sujet, profile_text
    except Exception as e:
        print(f"Error loading prompts: {e}")
        return "", "", "", ""

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
def replace_placeholders(prompt_text, company_info, profile_text=None):
    language_map = {
        "en": "English",
        "fr": "French",
        "es": "Spanish",
        "de": "German",
    }

    all_emails = ", ".join(company_info.get("mails", []))
    all_addresses = "; ".join(company_info.get("addresses", []))
    all_personal_names = ", ".join(company_info.get("personal_names", []))

    prompt_text = prompt_text.replace('{"company_name"}', company_info.get("company_name", ""))
    prompt_text = prompt_text.replace('{"mails"}', all_emails)
    prompt_text = prompt_text.replace('{"summary"}', company_info.get("summary", ""))
    prompt_text = prompt_text.replace('{"addresses"}', all_addresses)
    prompt_text = prompt_text.replace('{"personal_names"}', all_personal_names)

    if profile_text:
        prompt_text = prompt_text.replace("{profile.txt}", profile_text)

    language_code = detect(company_info.get("summary", ""))
    language_full = language_map.get(language_code, "English")
    prompt_text = prompt_text.replace("{language}", language_full)

    return prompt_text

def extract_text_from_response(response_text):
    start = response_text.find('{')
    end = response_text.find('}', start)
    if start != -1 and end != -1:
        return response_text[start+1:end]
    return ""

def generate_corp_content(company_info, prompt_corp, profile_text):
    base_prompt = replace_placeholders(prompt_corp, company_info, profile_text)
    messages = [
        {"role": "system", "content": "You are an expert in professional cover letter writing with over 20 years of experience. You have helped thousands of candidates craft compelling and effective cover letters."},
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
            return extracted_text
        except Exception as e:
            print(f"Error generating corp content: {e}")
            time.sleep(RETRY_DELAY)
    
    return "Erreur de génération du corps de la lettre"

def generate_destinataire_content(company_info, prompt_destinataire):

    def is_valid_format(text):
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if not (2 <= len(lines) <= 5):
            return False
        for line in lines:
            if (len(line) > 32 or ',' in line):
                return False
        return True

    base_prompt = replace_placeholders(prompt_destinataire, company_info)
    messages = [
        {"role": "system", "content": "You are an expert in professional cover letter writing with over 20 years of experience. You have helped thousands of candidates craft compelling and effective cover letters."},
        {"role": "user", "content": base_prompt}
    ]

    max_attempts = 20

    for attempt in range(max_attempts):
        try:
            response = client.chat.completions.create(
                messages=messages,
                model="llama3-70b-8192"
            )
            response_text = response.choices[0].message.content
            print(response_text)
            extracted_text = extract_text_from_response(response_text)
            print(extracted_text)
            if is_valid_format(extracted_text):
                return extracted_text
        except Exception as e:
            print(f"Error generating destinataire content: {e}")
            time.sleep(RETRY_DELAY)
    
    print("Échec de la génération du destinataire après 20 tentatives.")
    return "Échec de la génération du destinataire après 20 tentatives."

def generate_sujet_content(company_info, prompt_sujet):
    base_prompt = replace_placeholders(prompt_sujet, company_info)
    messages = [
        {"role": "system", "content": "You are an expert in professional cover letter writing with over 20 years of experience. You have helped thousands of candidates craft compelling and effective cover letters."},
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
            return extracted_text
        except Exception as e:
            print(f"Error generating sujet content: {e}")
            time.sleep(RETRY_DELAY)

    return "Erreur de génération du sujet de la lettre"

def save_to_file(filename, content):
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(content)
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


def compile_latex(name):
    try:
        output_dir = 'Cover_PDF'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        latex_file = './main.tex'
        pdf_output = f'{output_dir}/{name}.pdf'
        pdf_generated = f'{output_dir}/main.pdf'



        result = subprocess.run(['pdflatex', '-output-directory', output_dir, latex_file], capture_output=True, text=True)

        if result.returncode == 0:

            if os.path.exists(pdf_output):
                new_pdf_output = rename_existing_file(pdf_output)
                os.rename(pdf_output, new_pdf_output)

            os.rename(pdf_generated, pdf_output)

            residual_files = ['Compilation/sujet.txt', 'Compilation/corp.txt', 'Compilation/destinataire.txt']
            latex_residuals = ['aux', 'log', 'out', 'toc', 'synctex.gz']
            for ext in latex_residuals:
                residual_files.append(f'{output_dir}/main.{ext}')
            clean_up_files(residual_files)
        else:
            print(f"Erreur de compilation LaTeX pour {name}")
            print(result.stderr)
    except FileNotFoundError:
        print("Erreur : pdflatex n'a pas été trouvé. Assurez-vous que pdflatex est installé et accessible dans votre PATH.")
        pdflatex_path = 'C:/Users/Carlos/AppData/Local/Programs/MiKTeX/miktex/bin/x64/pdflatex.exe'
        try:
            result = subprocess.run([pdflatex_path, '-output-directory', output_dir, latex_file], capture_output=True, text=True)
            if result.returncode == 0:

                if os.path.exists(pdf_output):
                    new_pdf_output = rename_existing_file(pdf_output)
                    os.rename(pdf_output, new_pdf_output)

                os.rename(pdf_generated, pdf_output)

                residual_files = ['sujet.txt', 'corp.txt', 'destinataire.txt']
                latex_residuals = ['aux', 'log', 'out', 'toc', 'synctex.gz']
                for ext in latex_residuals:
                    residual_files.append(f'{output_dir}/main.{ext}')
                clean_up_files(residual_files)
            else:
                print(f"Erreur de compilation LaTeX pour {name}")
                print(result.stderr)
        except FileNotFoundError:
            print(f"Erreur : Impossible de trouver pdflatex au chemin spécifié : {pdflatex_path}")

def build_covers(json_file='Json_Files/results.json', specific_company_name=None):
    data = load_results(json_file)
    prompt_corp, prompt_destinataire, prompt_sujet, profile_text = load_prompts()

    for company_info in data:
        name = company_info["company_name"]
        
        if specific_company_name and name != specific_company_name:
            continue

        print(f"Traitement de {name}...")

        corp_content = generate_corp_content(company_info, prompt_corp, profile_text)
        destinataire_content = generate_destinataire_content(company_info, prompt_destinataire)
        sujet_content = generate_sujet_content(company_info, prompt_sujet)

        save_to_file('Compilation/corp.txt', corp_content)
        save_to_file('Compilation/destinataire.txt', destinataire_content)
        save_to_file('Compilation/sujet.txt', sujet_content)

        name = get_final_name(detect(company_info.get("summary", "")), name)
        compile_latex(name)
        print(f"Traitement de {name} terminé.\n")

if __name__ == "__main__":
    specific_company_name = None
    if len(sys.argv) > 1:
        specific_company_name = sys.argv[1]
    build_covers(specific_company_name=specific_company_name)
