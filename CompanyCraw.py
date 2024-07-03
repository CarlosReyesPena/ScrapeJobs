import os
import re
import requests
from playwright.sync_api import sync_playwright
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
from groq import Groq
from langdetect import detect, LangDetectException
import base64
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

# Fonction pour charger les mots-clés à partir d'un fichier JSON
def load_lists(json_file_path='Json_Files/lists.json'):
    try:
        with open(json_file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data['List_1'], data['List_2']
    except Exception as e:
        print(f"Error loading lists: {e}")
        return [], []

def load_company_info(json_file='Json_Files/company_info.json'):
    try:
        with open(json_file, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Error loading company info: {e}")
        return []

# Fonction pour obtenir les chemins des extensions
def get_extension_paths(extensions_dir):
    extension_paths = []
    for path in Path(extensions_dir).iterdir():
        if path.is_dir():
            extension_paths.append(str(path.resolve()))
    return extension_paths

# Créer un profil persistant avec les préférences et extensions
def create_persistent_profile():
    base_dir = os.path.join(os.getcwd(), 'Chromium')
    user_data_dir = os.path.join(base_dir, 'user_data_dir')
    extensions_dir = os.path.join(base_dir, 'Extensions')

    os.makedirs(user_data_dir, exist_ok=True)
    os.makedirs(extensions_dir, exist_ok=True)

    extension_paths = get_extension_paths(extensions_dir)
    extensions_args = []
    for path in extension_paths:
        extensions_args.append(f'--disable-extensions-except={path}')
        extensions_args.append(f'--load-extension={path}')

    return user_data_dir, extensions_args

# Fonction pour capturer les mailto links avec Playwright avec une limite d'essais
def capture_mailto_links(url):
    mailto_requests_urls = []
    click_attempts = 0  # Initialiser le compteur d'essais de clics
    max_clicks = 10  # Limite des clics

    user_data_dir, extensions_args = create_persistent_profile()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(user_data_dir, headless=False, args=extensions_args)  # Utiliser un profil utilisateur persistant
        page = browser.new_page()

        # Fonction pour capturer les requêtes réseau
        def capture_request(request):
            if 'mailto:' in request.url:
                mailto_requests_urls.append(request.url)

        # Écouter les événements de requêtes réseau
        page.on('request', capture_request)

        for attempt in range(RETRY_ATTEMPTS):
            try:
                # Naviguer vers l'URL
                page.goto(url, timeout=30000)
                page.wait_for_load_state('networkidle')
                break  # Sortir de la boucle si la navigation réussit
            except Exception as e:
                print(f"Error navigating to {url}: {e}")
                if attempt < RETRY_ATTEMPTS - 1:
                    print(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"Failed to navigate to {url} after {RETRY_ATTEMPTS} attempts.")
                    browser.close()
                    return mailto_requests_urls

        # Défilement lent pour s'assurer que tous les éléments sont chargés
        scroll_height = page.evaluate('document.body.scrollHeight')
        for scroll in range(0, scroll_height, 300):
            page.evaluate(f'window.scrollTo(0, {scroll})')
            time.sleep(1)

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
                    href = element.get('href')
                    # Rechercher l'élément avec Playwright et cliquer dessus via JavaScript
                    playwright_element = page.query_selector(f'a[href="{href}"]')
                    if playwright_element:
                        page.evaluate('element => { element.scrollIntoView(); element.click(); }', playwright_element)
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
    visible_text = soup.get_text(separator='\n', strip=True)
    
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = set()
    mail_elements = soup.find_all('a', href=True)
    for element in mail_elements:
        href = element['href'].lower()
        element_text = element.get_text(separator=' ', strip=True).lower()
        if "mail" in href or "mail" in element_text:
            if href not in visited_mailto_links:
                element_context = element.get_text(separator=' ', strip=True)
                start = max(visible_text.find(element_context) - 500, 0)
                end = min(visible_text.find(element_context) + len(element_context) + 500, len(visible_text))
                context = visible_text[start:end]

                mailto_requests_urls = capture_mailto_links(base_url)
                mailto_emails = extract_emails_from_mailto_links(mailto_requests_urls)
                for email in mailto_emails:
                    emails.add((email, context))
                    log_extraction('mailto_link', base_url, (email, context))
                
                visited_mailto_links.add(href)
        
        link_text = element.get_text(separator=' ', strip=True)
        emails.update(extract_emails(link_text, html_content, 'default', email_pattern))

    emails.update(extract_emails(visible_text, html_content, 'default', email_pattern))

    emails.update(extract_emails(visible_text, html_content, 'obfuscated', email_pattern))
    emails.update(extract_emails(visible_text, html_content, 'encoded', email_pattern))
    emails.update(extract_emails(visible_text, html_content, 'base64', email_pattern))
    emails.update(extract_emails(visible_text, html_content, 'spaced', email_pattern))

    return list(emails)

def extract_emails(text, context, method='default', email_pattern=r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'):
    emails = set()

    try:
        if method == 'default':
            matches = re.finditer(email_pattern, text)
        elif method == 'obfuscated':
            obfuscated_pattern = r'\b\w+[.\w+]*\s*\[at\]\s*\w+[.\w+]*\s*\[dot\]\s*\w+\b'
            matches = [
                re.match(email_pattern, match.group().replace('[at]', '@').replace('[dot]', '.').replace(' ', ''))
                for match in re.finditer(obfuscated_pattern, text)
                if re.match(email_pattern, match.group().replace('[at]', '@').replace('[dot]', '.').replace(' ', ''))
            ]
        elif method == 'encoded':
            encoded_emails = re.findall(r'&#\d+;', text)
            decoded_email = ''.join([chr(int(code[2:-1])) for code in encoded_emails])
            matches = [re.match(email_pattern, decoded_email)]
        elif method == 'base64':
            base64_pattern = r'[A-Za-z0-9+/=]{40,}'
            matches = []
            for match in re.finditer(base64_pattern, text):
                try:
                    decoded_email = base64.b64decode(match.group()).decode('utf-8')
                    if re.match(email_pattern, decoded_email):
                        matches.append(re.match(email_pattern, decoded_email))
                except (base64.binascii.Error, UnicodeDecodeError) as e:
                    print(f"Base64 decoding error: {e}")
        elif method == 'spaced':
            #print(text)
            spaced_pattern = r'\b\w+\s*\w*\s*\[?\s*@\s*\]?\s*\w+\s*\.\s*\w+\b'
            matches = [
                re.match(email_pattern, match.group().replace(' ', '').replace('[at]', '@').replace('[dot]', '.'))
                for match in re.finditer(spaced_pattern, text)
                if re.match(email_pattern, match.group().replace(' ', '').replace('[at]', '@').replace('[dot]', '.'))
            ]

        for match in matches:
            if match:
                email = match.group()
                start = max(match.start() - 500, 0)
                end = min(match.end() + 500, len(text))
                email_context = text[start:end]
                emails.add((email, email_context))
                log_extraction('html_content', context, (email, email_context))
                log_extraction('extract_emails_with_context', text, (email, email_context))
    except Exception as e:
        print(f"An error occurred during email extraction: {e}")

    return emails

# Fonction pour récupérer le contenu d'une page web
def fetch_page(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/78.0.3904.70 Chrome/78.0.3904.70 Safari/537.36'
    }
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response.text
            else:
                print(f"HTTP error {response.status_code} while fetching {url}")
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            if attempt < RETRY_ATTEMPTS - 1:
                print(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"Failed to fetch {url} after {RETRY_ATTEMPTS} attempts.")
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

    # Rechercher toutes les balises <a> avec l'attribut href
    for link in soup.find_all('a', href=True):
        href = link['href']
        link_text = link.get_text(separator=' ', strip=True)
        # Construire l'URL complète en utilisant urljoin
        full_url = urljoin(base_url, href)

        parsed_full_url = urlparse(full_url)
        if base_domain in parsed_full_url.netloc:
            if not has_extension(full_url):
                if contains_keyword(full_url, link_text, list_1):
                    cat1_links.add(full_url)
                elif contains_keyword(full_url, link_text, list_2) or full_url in list_2:
                    cat2_links.add(full_url)

    # Charger les liens existants à partir du fichier classified_links.json
    try:
        with open('classified_links.json', 'r', encoding='utf-8') as file:
            existing_links = json.load(file)
    except FileNotFoundError:
        existing_links = {"cat1_links": [], "cat2_links": []}

    # Mettre à jour les liens existants avec les nouveaux liens trouvés
    existing_links["cat1_links"] = list(set(existing_links["cat1_links"]) | cat1_links)
    existing_links["cat2_links"] = list(set(existing_links["cat2_links"]) | cat2_links)

    # Enregistrer les liens mis à jour dans le fichier classified_links.json
    with open('classified_links.json', 'w', encoding='utf-8') as file:
        json.dump(existing_links, file, ensure_ascii=False, indent=4)

    return cat1_links, cat2_links

# Fonction pour vérifier si une URL ne contient pas d'extension non-web
def has_extension(url):
    # Liste des extensions de fichiers web courantes que nous souhaitons exclure
    web_extensions = ['.html', '.htm', '.php', '.asp', '.aspx', '.jsp']
    # Extraire l'extension de l'URL
    extension = re.search(r'\.\w+$', url)
    if extension:
        return extension.group() not in web_extensions
    return False

def clean_json_string(json_str):
    json_str = json_str.replace("'", '"')
    json_str = json_str.replace("(", "{").replace(")", "}")
    return json_str

def extract_text_within_braces(text):
    try:
        start_index = text.index('{')
        end_index = text.rindex('}') + 1
        return text[start_index:end_index]
    except (ValueError, IndexError) as e:
        print(f"Error extracting text within braces: {e}")
        return ""

def extract_address(context):
    result = extract_information(context)
    try:
        clean_result = clean_json_string(result)
        json_str = extract_text_within_braces(clean_result)
        return json.loads(json_str)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Error extracting or decoding JSON: {e}")
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

    list_1, list_2 = load_lists("Json_Files/lists.json")

    to_visit = [[] for _ in range(2)]

    html_content = fetch_page(base_url)
    
    to_visit[0].append(base_url)
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
                
                if current_category == 0 or current_url in cat1_links:
                    emails_with_context = extract_emails_with_context(html_content, current_url, visited_mailto_ref)
                    for email, context in emails_with_context:
                        print(f"Email found: {email}")
                        if email not in processed_emails:
                            information = process_information(context, addresses, names)
                            processed_emails[email] = information
                        if email not in emails:
                            emails.append(email)
                
                if current_category == 0 or current_url in cat2_links:
                    summary_texts.append(visible_text)
                
                cat1_links, cat2_links = get_internal_links(current_url, html_content, list_1, list_2)
                to_visit[0].extend(list(cat1_links - visited_urls))
                to_visit[1].extend(list(cat2_links - visited_urls))
        
        current_category += 1
        if current_category >= len(to_visit):
            break
    
    with open('visited_links.txt', 'w', encoding='utf-8') as file:
        for link in visited_links_order:
            file.write(link + '\n')

    return emails, addresses, names, summary_texts

def process_information(context, addresses, names):
    information = extract_address(context)

    unique_addresses = set(addresses)
    unique_names = set(names)

    if information["addresses"]:
        for address in information["addresses"]:
            print(f"Address found: {address}")
            unique_addresses.add(address)

    if information["names_and_roles"]:
        for name in information["names_and_roles"]:
            print(f"Name found: {name}")
            unique_names.add(name)

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
    for attempt in range(RETRY_ATTEMPTS):
        try:
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
        except Exception as e:
            print(f"Error extracting information: {e}")
            time.sleep(RETRY_DELAY)
    return ""

def generate_summary(content, language, current_summary=""):
    for attempt in range(RETRY_ATTEMPTS):
        try:
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
                            f"### Current summary:\n"
                            f"{current_summary}\n\n"
                            f"### Additionnal data to complete the summary:\n"
                            f"{content}\n\n"
                            f"### Task:\n"
                            f"Using the provided information, generate a detailed and coherent company description. "
                            f"Include the company's history, mission, key products or services, target market, unique selling points, recent achievements, and company culture if available. "
                            f"If specific details are not available, summarize the given information as effectively as possible. "
                            f"Output the description in the format: (description)."
                            f"The final output should be in {language} and enclosed in parentheses ()."
                            f"Erase the @info@ and it's information from the input text"
                            f"If there is a personal name or role mentioned in the Additional data, say @info@ outside the parentheses."
                        )
                    }
                ],
                model="llama3-70b-8192",
            )
            response = chat_completion.choices[0].message.content
            extracted_text = extract_text_within_braces(clean_json_string(response))
            return extracted_text if extracted_text else response
        except Exception as e:
            print(f"Error generating summary: {e}")
            time.sleep(RETRY_DELAY)
    return current_summary

# Fonction pour extraire le nom de l'entreprise à partir du résumé en utilisant le modèle "llama3-70b-8192"
def extract_company_name(summary):
    for attempt in range(RETRY_ATTEMPTS):
        try:
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
        except Exception as e:
            print(f"Error extracting company name: {e}")
            time.sleep(RETRY_DELAY)
    return ""

def load_json_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return []

def save_json_file(data, file_path):
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving JSON file: {e}")

def update_company_data(result, results_file='Json_Files/results.json', company_info_file='Json_Files/company_info.json'):
    existing_results = load_json_file(results_file)
    company_info_list = load_json_file(company_info_file)

    if not result.get("mails"):
        print(f"No emails found for {result.get('company_name')}. Ignored.")
        return

    company_info = None
    for company in company_info_list:
        if company["website"] == result["website"]:
            company_info = company
            break

    if not company_info:
        print(f"No information found for {result.get('company_name')} in company_info.json. Ignored.")
        return

    final_result = {
        "company_name": company_info.get("company_name", result.get("company_name", "")),
        "phone": company_info.get("phone", ""),
        "website": company_info.get("website", result.get("website", "")),
        "addresses": company_info.get("addresses", []) or result.get("addresses", []),
        "summary": company_info.get("summary", result.get("summary", "")),
        "mails": company_info.get("mails", []) or result.get("mails", []),
        "personal_names": company_info.get("personal_names", []) or result.get("personal_names", [])
    }

    updated = False
    for i, existing_result in enumerate(existing_results):
        if existing_result["website"] == final_result["website"]:
            existing_results[i] = final_result
            updated = True
            break

    if not updated:
        existing_results.append(final_result)

    save_json_file(existing_results, results_file)
    print(f"Company information updated for {result.get('company_name')}.")

def main(company_info_file='Json_Files/company_info.json', results_file='Json_Files/results.json', max_pages=20):
    company_info = load_company_info(company_info_file)
    
    # Charger les résultats existants depuis results.json
    existing_results = load_json_file(results_file)
    existing_company_names = {result["company_name"] for result in existing_results}

    for company in company_info:
        base_url = company["website"]
        
        # Vérifier si le nom de la compagnie est déjà présent dans les résultats existants
        if company["company_name"] in existing_company_names:
            print(f"Skipping {company['company_name']} as it already exists in results.")
            continue

        print(f"Crawling website: {base_url}")
        emails, addresses, names, summary_texts = crawl_website(base_url, max_pages)

        max_length = 10000
        merged_text = " ".join(summary_texts)[:max_length]

        current_summary = ""

        language = detect_language(merged_text)

        chunk_size = 2000
        for chunk in chunk_text(merged_text, chunk_size):
            print(f"Text sent to AI (part): {chunk[:chunk_size]}")
            current_summary = generate_summary(chunk, language, current_summary)
            if check_for_info_tag(current_summary):
                process_information(current_summary, addresses, names)
            print(f"Intermediate company summary: {current_summary}")

        company_name = extract_company_name(current_summary)

        print(f"Emails found: {emails}")
        print(f"Addresses found: {addresses}")
        print(f"Names found: {names}")
        print(f"Company name: {company_name}")
        print(f"Company summary: {current_summary}")

        result = {
            "company_name": company_name,
            "summary": current_summary,
            "mails": list(emails),
            "addresses": list(addresses),
            "personal_names": list(names),
            "website": base_url
        }
        update_company_data(result)

if __name__ == "__main__":
    main()
