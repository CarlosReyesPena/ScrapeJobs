import os
import re
import requests
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
from groq import Groq
from langdetect import detect, LangDetectException

# Charger l'API key depuis un fichier
def load_api_key(file_path='groq_api_key.txt'):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read().strip()

# Configuration de l'API Meta3
api_key = load_api_key()
client = Groq(api_key=api_key)

# Fonction pour charger les mots-clés à partir d'un fichier JSON
def load_lists(json_file_path='Json_Files/lists.json'):
    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data['List_1'], data['List_2']

# Fonction pour charger les mots-clés à partir d'un fichier JSON
def load_keywords(json_file_path='Json_Files/keywords.json'):
    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    keywords_cat1 = data['cat_1']
    keywords_cat2 = data['cat_2']
    
    return keywords_cat1, keywords_cat2

def load_company_info(json_file='Json_Files/company_info.json'):
    try:
        with open(json_file, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return []

def save_company_info(company_info, json_file='Json_Files/results.json'):
    with open(json_file, 'w', encoding='utf-8') as file:
        json.dump(company_info, file, ensure_ascii=False, indent=4)

from playwright.sync_api import sync_playwright
import re
from bs4 import BeautifulSoup
import base64
import os

# Fonction pour capturer les mailto links avec Playwright avec une limite d'essais
def capture_mailto_links(url):
    mailto_requests_urls = []
    click_attempts = 0  # Initialiser le compteur d'essais de clics
    max_clicks = 10  # Limite des clics

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # Lancer le navigateur en mode "headless"
        page = browser.new_page()

        # Fonction pour capturer les requêtes réseau
        def capture_request(request):
            if 'mailto:' in request.url:
                mailto_requests_urls.append(request.url)

        # Écouter les événements de requêtes réseau
        page.on('request', capture_request)

        try:
            # Naviguer vers l'URL
            page.goto(url)
            page.wait_for_load_state('networkidle')
        except Exception as e:
            print(f"Erreur lors de la navigation vers {url}: {e}")
            browser.close()
            return mailto_requests_urls

        # Obtenir le contenu HTML de la page
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')

        # Identifier et cliquer sur les éléments contenant "mail" n'importe où dans les attributs ou le texte
        mail_elements = soup.find_all('a')
        for element in mail_elements:
            if click_attempts >= max_clicks:
                print("Nombre maximum d'essais de clics atteint.")
                break
            try:
                element_str = str(element)
                if "mail" in element_str.lower():
                    # Rechercher l'élément avec Playwright et cliquer dessus
                    playwright_element = page.query_selector(f'a[href="{element["href"]}"]')
                    if playwright_element:
                        playwright_element.click()
                        page.wait_for_load_state('networkidle')
                        click_attempts += 1  # Incrémenter le compteur d'essais de clics
            except Exception as e:
                print(f"Error clicking element: {e}")
                click_attempts += 1  # Incrémenter le compteur d'essais de clics en cas d'erreur

        # Fermer le navigateur
        browser.close()

    return mailto_requests_urls

# Fonction pour extraire les e-mails des URLs "mailto:"
def extract_emails_from_mailto_links(mailto_links):
    emails = []
    for link in mailto_links:
        match = re.search(r'mailto:([^?]+)', link)
        if match:
            emails.append(match.group(1))
    return emails

# Fonction pour logger les résultats
def log_extraction(function_name, input_text, result):
    log_dir = f'logs/{function_name}'
    os.makedirs(log_dir, exist_ok=True)
    existing_logs = len(os.listdir(log_dir))
    log_file_path = os.path.join(log_dir, f'log_{existing_logs + 1}.txt')

    with open(log_file_path, 'w', encoding='utf-8') as file:
        file.write("Input Text:\n")
        file.write(input_text + "\n\n")
        file.write("Result:\n")
        file.write(str(result) + "\n")

# Fonction pour extraire les e-mails d'une page HTML et utiliser Playwright si nécessaire
def extract_emails_with_context(html_content, base_url, visited_mailto_links):
    soup = BeautifulSoup(html_content, 'html.parser')
    visible_text = soup.get_text(separator='\n', strip=True)  # Conserver les lignes
    
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = set()  # Utilisation d'un set pour éviter les doublons

    # Identifier les éléments contenant "mail"
    mail_elements = soup.find_all('a', href=True)
    for element in mail_elements:
        if "mail" in element.get_text(separator=' ', strip=True).lower():
            href = element['href']
            if href not in visited_mailto_links:
                # Récupérer le contexte autour de l'élément
                element_context = element.get_text(separator=' ', strip=True)
                start = max(visible_text.find(element_context) - 500, 0)
                end = min(visible_text.find(element_context) + len(element_context) + 500, len(visible_text))
                context = visible_text[start:end]

                # Utiliser Playwright pour capturer les mails obfusqués
                mailto_requests_urls = capture_mailto_links(base_url)
                print(mailto_requests_urls)
                mailto_emails = extract_emails_from_mailto_links(mailto_requests_urls)
                for email in mailto_emails:
                    emails.add((email, context))
                    log_extraction('mailto_link', base_url, (email, context))
                
                visited_mailto_links.add(href)

    # Extraire les e-mails visibles directement
    for match in re.finditer(email_pattern, visible_text):
        email = match.group()
        start = max(match.start() - 500, 0)
        end = min(match.end() + 500, len(visible_text))
        context = visible_text[start:end]
        emails.add((email, context))
        log_extraction('html_content', html_content, (email, context))
        log_extraction('extract_emails_with_context', visible_text, (email, context))

    # Techniques d'obfuscation
    # 1. Remplacement de caractères
    obfuscated_emails = re.findall(r'\b\w+[.\w+]*\s*\[at\]\s*\w+[.\w+]*\s*\[dot\]\s*\w+\b', visible_text)
    for obf_email in obfuscated_emails:
        email = obf_email.replace('[at]', '@').replace('[dot]', '.').replace(' ', '')
        emails.add((email, visible_text))
        log_extraction('obfuscated_email', visible_text, email)

    # 2. Encodage HTML
    encoded_emails = re.findall(r'&#\d+;', visible_text)
    if encoded_emails:
        email = ''.join([chr(int(code[2:-1])) for code in encoded_emails])
        emails.add((email, visible_text))
        log_extraction('encoded_email', visible_text, email)

    # 3. Base64 Encodé
    base64_emails = re.findall(r'[A-Za-z0-9+/=]{40,}', visible_text)
    for b64_email in base64_emails:
        try:
            email = base64.b64decode(b64_email).decode('utf-8')
            if re.match(email_pattern, email):
                emails.add((email, visible_text))
                log_extraction('base64_email', visible_text, email)
        except Exception as e:
            print(f"Erreur lors du décodage Base64: {e}")

    # 4. Suppression des espaces
    spaced_emails = re.findall(r'\b\w+\s*\w*\s*\[?\s*@\s*\]?\s*\w+\s*\.\s*\w+\b', visible_text)
    for spaced_email in spaced_emails:
        email = spaced_email.replace(' ', '').replace('[at]', '@').replace('[dot]', '.')
        if re.match(email_pattern, email):
            emails.add((email, visible_text))
            log_extraction('spaced_email', visible_text, email)
    
    print(list(emails))

    return list(emails)  # Convertir le set en liste


# Fonction pour récupérer le contenu d'une page web
def fetch_page(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/78.0.3904.70 Chrome/78.0.3904.70 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        else:
            print(f"Erreur HTTP {response.status_code} lors de la récupération de {url}")
            return ""
    except requests.RequestException as e:
        print(f"Erreur lors de la récupération de {url}: {e}")
        return ""

# Fonction pour normaliser les textes en minuscules et remplacer les caractères non alphabétiques par des espaces
def normalize_text(text):
    return re.sub(r'[^a-zA-Z]', ' ', text).lower()

# Fonction pour vérifier si un lien ou son texte contient un mot-clé d'une catégorie donnée
def contains_keyword(url, text, keywords):
    normalized_url = normalize_text(url)
    normalized_text = normalize_text(text)
    return any(normalize_text(keyword) in normalized_url or normalize_text(keyword) in normalized_text for keyword in keywords)

# Fonction pour analyser une page et trouver des liens internes classés par catégories
def get_internal_links(base_url, html_content, list_1, list_2):
    parsed_base_url = urlparse(base_url)
    base_domain = parsed_base_url.netloc
    soup = BeautifulSoup(html_content, 'html.parser')
    cat1_links = set()
    cat2_links = set()

    for link in soup.find_all('a', href=True):
        href = link['href']
        link_text = link.get_text(separator=' ', strip=True)
        if href.startswith('/'):
            full_url = urljoin(base_url, href)
        else:
            full_url = href

        parsed_full_url = urlparse(full_url)
        if base_domain in parsed_full_url.netloc:
            if not has_extension(full_url):
                if contains_keyword(full_url, link_text, list_1):
                    cat1_links.add(full_url)
                elif contains_keyword(full_url, link_text, list_2) or full_url in list_2:
                    cat2_links.add(full_url)

    # Lecture du fichier JSON existant pour ajouter les nouveaux liens
    try:
        with open('classified_links.json', 'r', encoding='utf-8') as file:
            existing_links = json.load(file)
    except FileNotFoundError:
        existing_links = {
            "cat1_links": [],
            "cat2_links": []
        }
    
    # Fusion des nouveaux liens avec ceux existants en évitant les doublons
    existing_links["cat1_links"] = list(set(existing_links["cat1_links"]) | cat1_links)
    existing_links["cat2_links"] = list(set(existing_links["cat2_links"]) | cat2_links)
    
    # Écriture des liens mis à jour dans le fichier JSON
    with open('classified_links.json', 'w', encoding='utf-8') as file:
        json.dump(existing_links, file, ensure_ascii=False, indent=4)
    
    return cat1_links, cat2_links

# Fonction pour vérifier si une URL ne contient pas d'extension
def has_extension(url):
    return re.search(r'\.\w+$', url)

def clean_json_string(json_str):
    # Remplacer les guillemets simples par des guillemets doubles
    json_str = json_str.replace("'", '"')
    
    # Remplacer les parenthèses par des accolades
    json_str = json_str.replace("(", "{").replace(")", "}")
    
    return json_str

def extract_text_within_braces(text):
    try:
        # Recherche le début et la fin des accolades
        start_index = text.index('{')
        end_index = text.rindex('}') + 1
        return text[start_index:end_index]
    except (ValueError, IndexError) as e:
        print(f"Error extracting text within braces: {e}")
        return ""

def extract_address(context):
    result = extract_information(context)
    try:
        # Recherche le début et la fin du JSON
        clean_result = clean_json_string(result)
        
        json_str = extract_text_within_braces(clean_result)
        
        return json.loads(json_str)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Error extracting or decoding JSON: {e}")
        
        # Handling incorrect format by informing the user and retrying extraction
        try:
            corrected_result = extract_information(
                context + " The previous output was not in the correct JSON format. Please ensure the JSON is properly formatted."
            )
            clean_result = clean_json_string(corrected_result)
            json_str = extract_text_within_braces(clean_result)
            return json.loads(json_str)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"Error extracting or decoding JSON after retry: {e}")
            return {"addresses": [], "names_and_roles": []}
    
def chunk_text(text, chunk_size):
    words = text.split()
    for i in range(0, len(words), chunk_size):
        yield ' '.join(words[i:i + chunk_size])

# Fonction principale pour parcourir le site et extraire les e-mails et adresses
def crawl_website(base_url, max_pages):
    visited_urls = set()
    emails = []
    addresses = []
    names = []
    processed_emails = {}
    summary_texts = []
    visited_links_order = []
    visited_mailto_ref = set()

    # Chargement des listes List_1 et List_2
    list_1, list_2 = load_lists("Json_Files/lists.json")

    to_visit = [[] for _ in range(2)]  # Une liste de listes pour les catégories : [list_1_links, list_2_links]

    html_content = fetch_page(base_url)
    
    to_visit[0].append(base_url)  # Ajouter l'URL de départ dans la catégorie "list_1_links"
    if html_content:
        cat1_links, cat2_links = get_internal_links(base_url, html_content, list_1, list_2)
        to_visit[0].extend(list(cat1_links))
        to_visit[1].extend(list(cat2_links))

    current_category = 0

    while any(to_visit) and len(visited_urls) < max_pages:
        while to_visit[current_category] and len(visited_urls) < max_pages:
            current_url = to_visit[current_category].pop(0)

            if current_url in visited_urls:
                continue

            visited_urls.add(current_url)
            visited_links_order.append(current_url)
            
            html_content = fetch_page(current_url)
            if html_content:
                print(f"Visiting: {current_url}")
                
                soup = BeautifulSoup(html_content, 'html.parser')
                visible_text = soup.get_text(separator=' ', strip=True)
                
                # Extraction des e-mails seulement sur la première page et les pages de list_1
                if current_category == 0 or current_url in cat1_links:
                    emails_with_context = extract_emails_with_context(html_content,current_url,visited_mailto_ref)
                    for email, context in emails_with_context:
                        print(f"Email found: {email}")
                        if email not in processed_emails:
                            information = process_information(context, addresses, names)
                            processed_emails[email] = information
                        if email not in emails:
                            emails.append(email)
                
                # Ajouter le texte visible pour le résumé seulement sur la première page et les pages de List_2
                if current_category == 0 or current_url in cat2_links:
                    summary_texts.append(visible_text)
                
                # Obtenir les liens internes de la page courante et les ajouter dans l'ordre de priorité
                cat1_links, cat2_links = get_internal_links(current_url, html_content, list_1, list_2)
                to_visit[0].extend(list(cat1_links - visited_urls))
                to_visit[1].extend(list(cat2_links - visited_urls))
        
        current_category += 1
        if current_category >= len(to_visit):
            break
    
    # Écriture des liens visités dans un fichier texte
    with open('visited_links.txt', 'w', encoding='utf-8') as file:
        for link in visited_links_order:
            file.write(link + '\n')

    return emails, addresses, names, summary_texts

def process_information(context, addresses, names):
    information = extract_address(context)

    # Utilisation de sets pour éviter les doublons
    unique_addresses = set(addresses)
    unique_names = set(names)

    if information["addresses"]:
        for address in information["addresses"]:
            print(f"Address found: {address}")
            unique_addresses.add(address)  # Ajout des adresses uniques

    if information["names_and_roles"]:
        for name in information["names_and_roles"]:
            print(f"Name found: {name}")
            unique_names.add(name)  # Ajout des noms uniques

    # Convertir les sets en listes
    addresses[:] = list(unique_addresses)
    names[:] = list(unique_names)

    return information


# Fonction pour détecter la langue du contenu
def detect_language(text):
    try:
        return detect(text)
    except LangDetectException:
        return "en"

def check_for_info_tag(summary_response):
    return "@info@" in summary_response
    
def extract_information(context):
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert in extracting specific information from text and providing structured outputs in JSON format. "
                    "Your task is to identify and extract physical addresses and the names of key figures along with their roles from the provided text. "
                    "Ensure the output is accurate and formatted correctly, avoiding redundancy."
                )
            },
            {
                "role": "user",
                "content": (
                    f"From the following text: {context}, extract the physical addresses and person names with their roles. "
                    f"Do not include any post office boxes. Provide the results in the following JSON format: "
                    f"{{\"addresses\": [\"address1\", \"address2\", ...], \"names_and_roles\": [\"Person Name, Person Role\", ...]}}. "
                    f"Do not include addresses that are not related to the company. Exclude any person that is not a key figure in the company. "
                    f"Ensure each name is correctly paired with their role and formatted as \"Person Name, Person Role\" without any extra structure or redundancy."
                )
            }
        ],
        model="llama3-70b-8192",
    )
    return chat_completion.choices[0].message.content.strip()
    
def generate_summary(content, language, current_summary=""):
    combined_content = current_summary + " " + content if current_summary else content
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert in summarizing company information. "
                    "Your task is to create a comprehensive and coherent company description suitable for a cover letter. "
                    "The description should be detailed and include, if available, the following elements: "
                    "company history, mission, key products or services, target market, unique selling points, recent achievements, and company culture. "
                    "If certain details are missing, focus on summarizing the provided information effectively. "
                )
            },
            {
                "role": "user",
                "content": (
                    f"### Provided Information:\n"
                    f"{combined_content}\n\n"
                    f"### Task:\n"
                    f"Using the provided information, generate a detailed and coherent company description. "
                    f"Include the company's history, mission, key products or services, target market, unique selling points, recent achievements, and company culture if available. "
                    f"If specific details are not available, summarize the given information as effectively as possible. "
                    f"Output the description in the format: (description)."
                    f"The final output should be in {language} and enclosed in parentheses ()."
                    f"If there is a personal name or role mentioned, say @info@ outside the parentheses."
                )
            }
        ],
        model="llama3-70b-8192",
    )
    response = chat_completion.choices[0].message.content
    extracted_text = extract_text_within_braces(clean_json_string(response))
    return extracted_text if extracted_text else response

# Fonction pour extraire le nom de l'entreprise à partir du résumé en utilisant le modèle "llama3-70b-8192"
def extract_company_name(summary):
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are an expert in identifying company names from text."
            },
            {
                "role": "user",
                "content": f"You must provide only the name of the company, without any preliminary indication, using the following summary: {summary}. "
            }
        ],
        model="llama3-70b-8192",
    )
    return chat_completion.choices[0].message.content.strip()

def add_intermediate_result(result, results_file='Json_Files/results.json'):
    # Charger les résultats existants du fichier results.json
    try:
        with open(results_file, 'r', encoding='utf-8') as file:
            existing_results = json.load(file)
    except FileNotFoundError:
        existing_results = []

    # Ajouter le nouveau résultat
    existing_results.append(result)

    # Sauvegarder les résultats mis à jour dans le fichier results.json
    save_company_info(existing_results, results_file)


def update_company_info(input, company_info_file='Json_Files/company_info.json', result_file='Json_Files/results.json'):
    company_info = load_company_info(company_info_file)
    updated = False

    for company in company_info:
        if company["website"] == input["website"]:
            # Mise à jour des informations existantes uniquement si elles sont absentes
            if not company.get("summary"):
                company["summary"] = input.get("summary", "")
            if not company.get("mails"):
                company["mails"] = input.get("mails", [])
            if not company.get("addresses"):
                company["addresses"] = input.get("addresses", [])
            if not company.get("personal_names"):
                company["personal_names"] = input.get("personal_names", [])
            updated = True
            break

    if not updated:
        # Ajout de nouvelles informations si l'URL n'est pas trouvée
        company_info.append({
            "company_name": input.get("company_name", ""),
            "phone": "",
            "website": input.get("website", ""),
            "addresses": input.get("addresses", []),
            "summary": input.get("summary", ""),
            "mails": input.get("mails", []),
            "personal_names": input.get("personal_names", [])
        })

    # Filtrer les entreprises sans mails
    company_info = [company for company in company_info if company.get("mails")]

    save_company_info(company_info, result_file)
    print("Company info updated successfully.")

# Fonction pour exécuter le processus complet de crawl et de génération de résultats
def main(company_info_file='Json_Files/company_info.json', results_file='Json_Files/results.json', max_pages=20):
    # Charger les informations des entreprises depuis company_info.json
    company_info = load_company_info(company_info_file)

    results = []

    for company in company_info:
        base_url = company["website"]
        print(f"Crawling website: {base_url}")
        emails, addresses, names, summary_texts = crawl_website(base_url, max_pages)

        max_length = 15000
        merged_text = " ".join(summary_texts)[:max_length]

        current_summary = ""

        language = detect_language(merged_text)

        # Diviser le texte en morceaux et itérer pour améliorer la description
        chunk_size = 2000  # Définir la taille des chunks en nombre de caractères
        for chunk in chunk_text(merged_text, chunk_size):
            print(f"Texte envoyé à l'IA (partie) :", chunk[:2000])
            current_summary = generate_summary(chunk, language, current_summary)
            if check_for_info_tag(current_summary) :
                process_information(current_summary, addresses, names)
            print(f"Résumé intermédiaire de l'entreprise :", current_summary)

        company_name = extract_company_name(current_summary)

        print(f"Adresses e-mail trouvées :", emails)
        print(f"Adresses trouvées :", addresses)
        print(f"Noms trouvés :", names)
        print(f"Nom de l'entreprise :", company_name)
        print(f"Résumé de l'entreprise :", current_summary)

        result = {
            "company_name": company_name,
            "summary": current_summary,
            "mails": list(emails),
            "addresses": list(addresses),
            "personal_names": list(names),
            "website": base_url  # Ajouter l'URL de base au résultat
        }

        # Ajouter le résultat intermédiaire au fichier results.json
        add_intermediate_result(result, results_file)

        results.append(result)
        
    # Mettre à jour les informations des entreprises dans company_info.json
    update_company_info(result, company_info_file, results_file)
    print("Mise à jour de company_info.json terminée.")

if __name__ == "__main__":
    main()

