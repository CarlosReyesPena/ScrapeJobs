import json
import subprocess
import os
from groq import Groq
from langdetect import detect

# Charger l'API key depuis un fichier
def load_api_key(file_path='groq_api_key.txt'):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read().strip()

# Configuration de l'API Meta3
api_key = load_api_key()
client = Groq(api_key=api_key)

# Fonction pour charger les données du fichier JSON
def load_results(json_file='Json_Files/results.json'):
    print("Chargement des données depuis results.json...")
    with open(json_file, 'r', encoding='utf-8') as file:
        data = json.load(file)
    print("Données chargées.")
    return data

# Fonction pour charger les prompts à partir des fichiers
def load_prompts():
    print("Chargement des fichiers de prompt...")
    with open('Text_Files/promptcorp.txt', 'r', encoding='utf-8') as file:
        prompt_corp = file.read()

    with open('Text_Files/promptdestinataire.txt', 'r', encoding='utf-8') as file:
        prompt_destinataire = file.read()

    with open('Text_Files/promptsujet.txt', 'r', encoding='utf-8') as file:
        prompt_sujet = file.read()

    with open('Text_Files/profil.txt', 'r', encoding='utf-8') as file:
        profile_text = file.read()
    print("Fichiers de prompt chargés.")
    return prompt_corp, prompt_destinataire, prompt_sujet, profile_text

# Fonction pour remplacer les balises dans le texte du prompt
def replace_placeholders(prompt_text, company_info, profile_text=None):
    language_map = {
        "en": "English",
        "fr": "French",
        "es": "Spanish",
        "de": "German",
        # Ajoutez d'autres langues si nécessaire
    }

    # Créer une chaîne de tous les e-mails et adresses
    all_emails = ", ".join(company_info.get("mails", []))
    all_addresses = "; ".join(company_info.get("addresses", []))
    all_personal_names = ", ".join(company_info.get("personal_names", []))


    # Remplacement des placeholders
    prompt_text = prompt_text.replace('{"company_name"}', company_info.get("company_name", ""))
    prompt_text = prompt_text.replace('{"mails"}', all_emails)
    prompt_text = prompt_text.replace('{"summary"}', company_info.get("summary", ""))
    prompt_text = prompt_text.replace('{"addresses"}', all_addresses)
    prompt_text = prompt_text.replace('{"personal_names"}', all_personal_names)

    if profile_text:
        prompt_text = prompt_text.replace("{profile.txt}", profile_text)

    # Détecter la langue et remplacer la balise {language}
    language_code = detect(company_info.get("summary", ""))
    language_full = language_map.get(language_code, "English")  # Par défaut à l'anglais si la langue n'est pas dans le dictionnaire
    prompt_text = prompt_text.replace("{language}", language_full)

    return prompt_text

# Fonction pour extraire le texte entre les accolades d'une réponse.
def extract_text_from_response(response_text):
    start = response_text.find('{')
    end = response_text.find('}', start)
    if start != -1 and end != -1:
        return response_text[start+1:end]
    return ""


# Fonction pour générer le corps de la lettre en utilisant LLaMA3-70b
def generate_corp_content(company_info, prompt_corp, profile_text):
    print(f'Génération du corps de la lettre pour {company_info["company_name"]}...')
    base_prompt = replace_placeholders(prompt_corp, company_info, profile_text)
    messages = [
        {"role": "system", "content": "You are an expert in professional cover letter writing with over 20 years of experience. You have helped thousands of candidates craft compelling and effective cover letters."},
        {"role": "user", "content": base_prompt}
    ]
    response = client.chat.completions.create(
        messages=messages,
        model="llama3-70b-8192"
    )
    print("Corps de la lettre généré.")
    response_text = response.choices[0].message.content
    extracted_text = extract_text_from_response(response_text)
    return extracted_text

# Fonction pour générer le destinataire en utilisant LLaMA3-70b
def generate_destinataire_content(company_info, prompt_destinataire):
    print(f'Génération du destinataire pour {company_info["company_name"]}...')
    base_prompt = replace_placeholders(prompt_destinataire, company_info)
    messages = [
        {"role": "system", "content": "You are an expert in professional cover letter writing with over 20 years of experience. You have helped thousands of candidates craft compelling and effective cover letters."},
        {"role": "user", "content": base_prompt}
    ]
    response = client.chat.completions.create(
        messages=messages,
        model="llama3-70b-8192"
    )
    print("Destinataire généré.")
    response_text = response.choices[0].message.content
    extracted_text = extract_text_from_response(response_text)
    return extracted_text

# Fonction pour générer le sujet de la lettre en utilisant LLaMA3-70b
def generate_sujet_content(company_info, prompt_sujet):
    print(f'Génération du sujet de la lettre pour {company_info["company_name"]}...')
    base_prompt = replace_placeholders(prompt_sujet, company_info)
    messages = [
        {"role": "system", "content": "You are an expert in professional cover letter writing with over 20 years of experience. You have helped thousands of candidates craft compelling and effective cover letters."},
        {"role": "user", "content": base_prompt}
    ]
    response = client.chat.completions.create(
        messages=messages,
        model="llama3-70b-8192"
    )
    print("Sujet de la lettre généré.")
    response_text = response.choices[0].message.content
    extracted_text = extract_text_from_response(response_text)
    return extracted_text

# Fonction pour sauvegarder le contenu dans un fichier
def save_to_file(filename, content):
    print(f"Sauvegarde du contenu dans {filename}...")
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(content)
    print(f"Contenu sauvegardé dans {filename}.")

# Fonction pour renommer les fichiers existants en ajoutant un suffixe
def rename_existing_file(file_path):
    base, extension = os.path.splitext(file_path)
    suffix = "_OLD_"
    index = 1

    while os.path.exists(file_path):
        new_file_path = f"{base}{suffix}{index}{extension}"
        index += 1
        file_path = new_file_path
    
    return file_path

# Fonction pour supprimer les fichiers résiduels
def clean_up_files(files_to_remove):
    for file_path in files_to_remove:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Fichier supprimé : {file_path}")

# Fonction pour compiler le fichier LaTeX
def compile_latex(name):
    try:
        # Créer le dossier Cover_PDF s'il n'existe pas
        output_dir = 'Cover_PDF'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Chemin complet du fichier LaTeX et du fichier PDF de sortie
        latex_file = './main.tex'
        pdf_output = f'{output_dir}/{name}.pdf'
        pdf_generated = f'{output_dir}/main.pdf'

        print(f"Compilation du fichier LaTeX pour {name}...")

        # Commande pour compiler le fichier LaTeX et spécifier le dossier de sortie
        result = subprocess.run(['pdflatex', '-output-directory', output_dir, latex_file], capture_output=True, text=True)

        if result.returncode == 0:
            print(f"Compilation LaTeX réussie pour {name}")

            # Vérifier si le fichier généré existe déjà et le renommer si nécessaire
            if os.path.exists(pdf_output):
                new_pdf_output = rename_existing_file(pdf_output)
                os.rename(pdf_output, new_pdf_output)
                print(f"Fichier existant renommé en {new_pdf_output}")

            # Renommer le fichier généré de main.pdf à nom_de_lentreprise.pdf
            os.rename(pdf_generated, pdf_output)
            print(f"Fichier PDF généré : {pdf_output}")

            # Supprimer les fichiers résiduels
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
        print("Essai avec le chemin complet vers pdflatex...")
        # Essayez avec un chemin complet, mettez à jour avec votre chemin exact si nécessaire
        pdflatex_path = 'C:/Users/Carlos/AppData/Local/Programs/MiKTeX/miktex/bin/x64/pdflatex.exe'
        try:
            result = subprocess.run([pdflatex_path, '-output-directory', output_dir, latex_file], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"Compilation LaTeX réussie pour {name}")

                # Vérifier si le fichier généré existe déjà et le renommer si nécessaire
                if os.path.exists(pdf_output):
                    new_pdf_output = rename_existing_file(pdf_output)
                    os.rename(pdf_output, new_pdf_output)
                    print(f"Fichier existant renommé en {new_pdf_output}")

                # Renommer le fichier généré de main.pdf à nom_de_lentreprise.pdf
                os.rename(pdf_generated, pdf_output)
                print(f"Fichier PDF généré : {pdf_output}")

                # Supprimer les fichiers résiduels
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

# Fonction principale pour générer et sauvegarder le contenu pour chaque entreprise
def build_covers(json_file='Json_Files/results.json'):
    data = load_results(json_file)
    prompt_corp, prompt_destinataire, prompt_sujet, profile_text = load_prompts()

    for company_info in data:
        name = company_info["company_name"]
        print(f"Traitement de {name}...")

        # Générer le contenu de la lettre
        corp_content = generate_corp_content(company_info, prompt_corp, profile_text)
        destinataire_content = generate_destinataire_content(company_info, prompt_destinataire)
        sujet_content = generate_sujet_content(company_info, prompt_sujet)

        # Sauvegarder les parties dans des fichiers séparés
        save_to_file('Compilation/corp.txt', corp_content)
        save_to_file('Compilation/destinataire.txt', destinataire_content)
        save_to_file('Compilation/sujet.txt', sujet_content)

        # Compiler le fichier LaTeX avec le nom de l'entreprise
        compile_latex(name)
        print(f"Traitement de {name} terminé.\n")

if __name__ == "__main__":
    build_covers()
