import os
import re
from playwright.async_api import async_playwright
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
from groq import Groq
from langdetect import detect, LangDetectException
import base64
import time
import asyncio
import aiohttp
from email_validator import validate_email, EmailNotValidError

RETRY_ATTEMPTS = 5
RETRY_DELAY = 3

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
    # Construire les arguments pour charger toutes les extensions
    extensions_arg = ",".join(extension_paths)

    args = [
        f'--disable-extensions-except={extensions_arg}',
        f'--load-extension={extensions_arg}'
    ]

    return user_data_dir, args
# Fonction pour extraire les e-mails des URLs "mailto:"
def extract_emails_from_mailto_links(mailto_links):
    emails = []
    for link in mailto_links:
        match = re.search(r'mailto:([^?]+)', link)
        if match:
            emails.append(match.group(1))
    return emails

# Fonction pour capturer les mailto links avec Playwright avec une limite d'essais
async def capture_mailto_links(url):
    mailto_requests_urls = []
    click_attempts = 0  # Initialiser le compteur d'essais de clics
    max_clicks = 10  # Limite des clics

    user_data_dir, extensions_args = create_persistent_profile()

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(user_data_dir, headless=True, args=extensions_args)  # Utiliser un profil utilisateur persistant
        page = await browser.new_page()

        # Fonction pour capturer les requêtes réseau
        async def capture_request(request):
            if 'mailto:' in request.url:
                mailto_requests_urls.append(request.url)

        # Écouter les événements de requêtes réseau
        page.on('request', capture_request)

        for attempt in range(RETRY_ATTEMPTS):
            try:
                # Naviguer vers l'URL
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state('networkidle')
                break  # Sortir de la boucle si la navigation réussit
            except Exception as e:
                print(f"Error navigating to {url}: {e}")
                if attempt < RETRY_ATTEMPTS - 1:
                    print(f"Retrying in {RETRY_DELAY} seconds...")
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    print(f"Failed to navigate to {url} after {RETRY_ATTEMPTS} attempts.")
                    await browser.close()
                    return mailto_requests_urls

        # Identifier les éléments contenant le mot "mail" dans le texte visible, dans les attributs ou dans le contenu de l'élément
        mail_elements = await page.query_selector_all('a, button')
        matching_elements = []

        for element in mail_elements:
            element_html = await element.evaluate('(element) => element.outerHTML.toLowerCase()')
            element_text = await element.evaluate('(element) => element.innerText.toLowerCase()')
            if "mail" in element_html or "mail" in element_text:
                matching_elements.append(element)


        for element in matching_elements:
            if click_attempts >= max_clicks:
                print("Nombre maximum d'essais de clics atteint.")
                break
            try:
                # Obtenir la bounding box de l'élément
                bounding_box = await element.bounding_box()
                if bounding_box:
                   
                    # Utiliser des assertions pour vérifier que l'élément est visible et cliquable
                    await element.scroll_into_view_if_needed()
                    # Cliquer sur la position centrale de l'élément
                    bounding_box = await element.bounding_box()
                    x = bounding_box['x'] + bounding_box['width'] / 2
                    y = bounding_box['y'] + bounding_box['height'] / 2
                    await page.mouse.click(x, y)
                click_attempts += 1  # Incrémenter le compteur d'essais de clics
            except Exception as e:
                print(f"Error clicking element: {e}")
                click_attempts += 1  # Incrémenter le compteur d'essais de clics en cas d'erreur
        # Fermer le navigateur
        await browser.close()

        emails = extract_emails_from_mailto_links(list(mailto_requests_urls))

    return emails

async def filter_and_rank_emails(emails, url):
    if not emails:
        return emails  # Retourner immédiatement si la liste des e-mails est vide

    valid_emails = []
    for email in emails:
        try:
            # Valider et normaliser l'email
            email_info = validate_email(email, check_deliverability=True)
            normalized_email = email_info.normalized
            valid_emails.append(normalized_email)
        except EmailNotValidError as e:
            print(f"Invalid email '{email}': {str(e)}")

    if not valid_emails:
        return valid_emails  # Retourner immédiatement si aucune adresse email valide n'est trouvée

    # Extraction du domaine principal du site web
    parsed_url = urlparse(url)
    base_domain = parsed_url.netloc
    base_domain_name = base_domain.split('.')[-2]  # Nom de domaine sans TLD

    # Liste des mots-clés spécifiques
    keywords = [
        'job', 'work', 'career', 'recruitment', 'hr', 'human resources', 'employment', 'vacancy', 'position', 'opening',
        'arbeit', 'karriere', 'rekrutierung', 'personal', 'menschliche ressourcen', 'beschäftigung', 'stelle', 'position', 'öffnung',
        'lavoro', 'carriera', 'reclutamento', 'risorse umane', 'occupazione', 'vacanza', 'posizione', 'apertura',
        'emploi', 'travail', 'carrière', 'recrutement', 'rh', 'ressources humaines', 'poste', 'position', 'ouverture',
        'trabajo', 'carrera', 'reclutamiento', 'recursos humanos', 'empleo', 'vacante', 'posición', 'apertura'
    ]

    # Calculer la longueur moyenne des emails
    avg_length = sum(len(email) for email in valid_emails) / len(valid_emails)

    # Compter les occurrences de chaque domaine complet après le @
    domain_counts = {}
    for email in valid_emails:
        full_domain = email.split('@')[-1]
        if full_domain not in domain_counts:
            domain_counts[full_domain] = 0
        domain_counts[full_domain] += 1

    # Définir une fonction pour calculer les points pour chaque email
    def calculate_points(email):
        points = 0
        domain_full = email.split('@')[-1]
        domain_base = domain_full.split('.')[0]
        # Ajouter des points si le domaine complet a plusieurs occurrences
        if domain_counts[domain_full] > 1:
            points += 1
        # Ajouter des points si le domaine du site web est inclus dans l'email (comparaison entre @ et .)
        if base_domain_name in domain_base:
            points += 1
        # Pénaliser les emails qui sont de 10 caractères plus longs que la longueur moyenne
        if len(email) > avg_length + 10:
            points -= 1
        return points

    # Calculer les points pour chaque email
    email_points = [(email, calculate_points(email)) for email in valid_emails]

    # Vérifier si email_points est vide
    if not email_points:
        return valid_emails

    # Trouver le score maximum
    max_points = max(email_points, key=lambda x: x[1])[1]

    # Filtrer les emails pour ne conserver que ceux avec le score maximum
    filtered_emails = [email for email, points in email_points if points == max_points]

    # Trier les emails par des mots-clés spécifiques pour les placer en premier
    filtered_emails.sort(key=lambda email: any(keyword in email for keyword in keywords), reverse=True)

    return filtered_emails



async def extract_emails_with_context(html_content, url,currents_emails, visited_mailto_links):
    emails_with_context = set()
    soup = BeautifulSoup(html_content, 'html.parser')
    visible_text = soup.get_text(separator='\n', strip=True)
    clickable_elements = soup.find_all(['a', 'button'])

    emails_with_context.update(extract_emails(visible_text,currents_emails))

    if clickable_elements:
        element_str = str(clickable_elements).lower()
        if "mailto" in element_str:
            if url not in visited_mailto_links:
                mailto_emails = await capture_mailto_links(url)
                for mailto_email in mailto_emails:
                    if mailto_email not in emails_with_context and mailto_email not in currents_emails:
                        emails_with_context.add((mailto_email, None))
                visited_mailto_links.add(url)
    return emails_with_context

def is_base64(s):
    try:
        return base64.b64encode(base64.b64decode(s)).decode('utf-8') == s
    except Exception:
        return False
    
# Listes des variantes pour @ et .
at_variants = ['[at]', '(at)', '{at}', '[AT]', '(AT)', '{AT}', ' at ']
dot_variants = ['[dot]', '(dot)', '{dot}', '[DOT]', '(DOT)', '{DOT}', ' dot ']

def clean_text_for_emails(text):
     # Replace obfuscated [at] and [dot]
    # Remplacer les variantes de @ par @
    for variant in at_variants:
        text = text.replace(variant, '@')
    
    # Remplacer les variantes de . par .
    for variant in dot_variants:
        text = text.replace(variant, '.')
    
    text = text.replace(' ', '')

    # Decode base64 encoded strings
    words = text.split()
    for i, word in enumerate(words):
        if is_base64(word):
            try:
                decoded_email = base64.b64decode(word).decode('utf-8')
                words[i] = decoded_email
            except (base64.binascii.Error, UnicodeDecodeError):
                continue
    text = ' '.join(words)

    return ''.join(text)

def extract_emails(text,currents_emails):
    email_pattern=r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = set()
    cleaned_text = clean_text_for_emails(text)
    matches = re.finditer(email_pattern, cleaned_text)

    for match in matches:
        if match.group() not in emails and match.group() not in currents_emails:
            email = match.group()
            start = max(match.start() - 500, 0)
            end = min(match.end() + 500, len(cleaned_text))
            email_context = cleaned_text[start:end]
            emails.add((email, email_context))

    return emails

async def fetch_page_with_aiohttp(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/78.0.3904.70 Chrome/78.0.3904.70 Safari/537.36'
    }
    async with aiohttp.ClientSession() as session:
        for attempt in range(RETRY_ATTEMPTS):
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        print(f"HTTP error {response.status} while fetching {url}")
            except aiohttp.ClientError as e:
                print(f"Error fetching {url}: {e}")
            if attempt < RETRY_ATTEMPTS - 1:
                print(f"Retrying in {RETRY_DELAY} seconds...")
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"Failed to fetch {url} after {RETRY_ATTEMPTS} attempts.")
    return None

async def fetch_page_with_playwright(url):
    user_data_dir, extensions_args = create_persistent_profile()

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(user_data_dir, headless=True, args=extensions_args)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state('networkidle')
            content = await page.content()
            await browser.close()
            return content
    except Exception as e:
        print(f"Error fetching {url} with Playwright: {e}")
        return None

async def fetch_page_with_fallback(url, use_playwright=False):
    if use_playwright:
        return await fetch_page_with_playwright(url)
    try:
        content = await fetch_page_with_aiohttp(url)
        if content:
            return content
        print(f"Failed to fetch {url} with aiohttp, falling back to Playwright...")
        content = await fetch_page_with_playwright(url)
        if content:
            print(f"Fetched {url} with Playwright successfully.")
            use_playwright = True
            return content
    except Exception as e:
        print(f"Error in fetch_page_with_fallback: {e}")
    return None

# Fonction pour normaliser les textes en minuscules et remplacer les caractères non alphabétiques par des espaces
def normalize_text(text):
    return re.sub(r'[^a-zA-Z]', ' ', text).lower()

# Fonction pour vérifier si un lien ou son texte contient un mot-clé d'une catégorie donnée
def contains_keyword(url, text, keywords):
    normalized_url = normalize_text(url)
    normalized_text = normalize_text(text)
    return any(normalize_text(keyword) in normalized_url or normalize_text(keyword) in normalized_text for keyword in keywords)

# Fonction pour analyser une page et trouver des liens internes classés par catégories
async def get_internal_links(base_url, html_content, list_1, list_2, initial_attempt=True):
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

    # Si aucun lien trouvé lors de la tentative initiale, utiliser Playwright pour récupérer le contenu
    if initial_attempt and not cat1_links and not cat2_links:
        return cat1_links, cat2_links

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

def extract_address(context, company_name):
    result = extract_information(context, company_name)
    try:
        clean_result = clean_json_string(result)
        json_str = extract_text_within_braces(clean_result)
        return json.loads(json_str)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Error extracting or decoding JSON: {e}")
        try:
            corrected_result = extract_information(
                context + " The previous output was not in the correct JSON format. Please ensure the JSON is properly formatted.", company_name
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
async def crawl_website(base_url, max_pages):
    visited_urls = set()
    emails = []
    addresses = []
    names = []
    processed_emails = {}
    summary_texts = []
    visited_mailto_ref = set()
    use_playwright = False

    list_1, list_2 = load_lists("Json_Files/lists.json")

    html_content = await fetch_page_with_fallback(base_url, use_playwright)
    
    to_visit = [[] for _ in range(2)]
    to_visit[0].append(base_url)
    if html_content:
        cat1_links, cat2_links = await get_internal_links(base_url, html_content, list_1, list_2, initial_attempt=True)
        if not cat1_links and not cat2_links:
            print("No internal links found on the main page. Using Playwright to fetch more links.")
            html_content = await fetch_page_with_playwright(base_url)
            cat1_links, cat2_links = await get_internal_links(base_url, html_content, list_1, list_2, initial_attempt=False)
            if cat1_links or cat2_links:
                print("Internal links found using Playwright.")
                use_playwright = True
        to_visit[0].extend(list(cat1_links))
        to_visit[1].extend(list(cat2_links))

    current_category = 0

    count = 0
    while any(to_visit) and len(visited_urls) < max_pages:
        while current_category < len(to_visit) and to_visit[current_category] and len(visited_urls) < max_pages:
            count += 1
            current_url = to_visit[current_category].pop(0)

            if current_url in visited_urls:
                continue

            visited_urls.add(current_url)
            
            html_content = await fetch_page_with_fallback(current_url, use_playwright)
            if html_content:
                print(f"Visiting: {current_url}")          
                soup = BeautifulSoup(html_content, 'html.parser')
                visible_text = soup.get_text(separator=' ', strip=True)
                
                if current_category == 0 or current_url in cat1_links:
                    emails_with_context = await extract_emails_with_context(html_content, current_url,emails , visited_mailto_ref)
                    for email, context in emails_with_context:
                        print(f"Email found: {email}")
                        if email not in processed_emails and context:
                            #extract the name of the site web in the base_url : exemple : www.google.com => google
                            company_name = base_url.split('.')[1]
                            information = process_information(context, addresses, names, company_name)
                            processed_emails[email] = information
                        if email not in emails:
                            emails.append(email)
                
                if current_category == 0 or current_url in cat2_links:
                    summary_texts.append(visible_text)
                
                cat1_links, cat2_links = await get_internal_links(current_url, html_content, list_1, list_2, initial_attempt=True)
                to_visit[0].extend(list(cat1_links - visited_urls))
                to_visit[1].extend(list(cat2_links - visited_urls))
            
            current_category += 1
            if current_category >= len(to_visit):
                break

        # Reset current_category to start again
        if to_visit[0]:
            current_category = 0
        else:
            current_category = 1

    emails = await filter_and_rank_emails(emails, base_url)

    print(f"final emails found: {emails}")

    return emails, addresses, names, summary_texts



def process_information(context, addresses, names, company_name):
    information = extract_address(context, company_name)

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
    
def extract_information(context, company_name):
    for attempt in range(RETRY_ATTEMPTS):
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert in extracting specific information from text and providing structured outputs in JSON format. "
                            f"Your task is to identify and extract physical addresses and the names of key figures of the company {company_name}, along with their roles from the provided text."
                            "Ensure the output is accurate and formatted correctly, avoiding redundancy."
                            f"Do not include any names or addresses that are not related to the company {company_name}."
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"From the following text: {context}, extract the physical addresses and person names with their roles. "
                            "Do not include any post office boxes. Provide the results in the following JSON format: "
                            "{\"addresses\": [\"address1\", \"address2\", ...], \"names_and_roles\": [\"Person Name, Person Role\", ...]}."
                            "Do not include addresses that are not related to the company. Exclude any person that is not a key figure in the company. "
                            "Ensure each name is correctly paired with their role and formatted as \"Person Name, Person Role\" without any extra structure or redundancy."
                        )
                    }
                ],
                model="llama3-70b-8192",
            )
            return chat_completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error: {e}")
            wait_time = extract_wait_time(str(e))
            if wait_time:
                print(f"Rate limit exceeded. Waiting for {wait_time} seconds before retrying...")
                time.sleep(wait_time)
            else:
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
                            f"If there is a personal name in the Additional data, write @info@ at the right of the description. Outside the parentheses."
                        )
                    }
                ],
                model="llama3-70b-8192",
            )
            response = chat_completion.choices[0].message.content
            extracted_text = extract_text_within_braces(clean_json_string(response))
            return extracted_text if extracted_text else response
        except Exception as e:
            print(f"Error: {e}")
            wait_time = extract_wait_time(str(e))
            if wait_time:
                print(f"Rate limit exceeded. Waiting for {wait_time} seconds before retrying...")
                time.sleep(wait_time)
            else:
                time.sleep(RETRY_DELAY)
    return current_summary

# Fonction pour extraire le nom de l'entreprise à partir du résumé.
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
            print(f"Error: {e}")
            wait_time = extract_wait_time(str(e))
            if wait_time:
                print(f"Rate limit exceeded. Waiting for {wait_time} seconds before retrying...")
                time.sleep(wait_time)
            else:
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

def update_company_data(result, results_file='Json_Files/results.json', company_info_file='Json_Files/company_info.json', failed_companies_file='Json_Files/failed_companies.json'):
    existing_results = load_json_file(results_file)
    company_info_list = load_json_file(company_info_file)
    failed_companies = load_json_file(failed_companies_file)

    if not result.get("mails"):
        print(f"No emails found for {result.get('company_name')}. Ignored.")
        # Mise à jour des compagnies ayant échoué
        failed_companies.append({
            "company_name": result.get('company_name', ''),
            "website": result.get('website', '')
        })
        save_json_file(failed_companies, failed_companies_file)
        return

    company_info = None
    for company in company_info_list:
        if company["website"] == result["website"]:
            company_info = company
            break

    if not company_info:
        print(f"No information found for {result.get('company_name')} in company_info.json. Ignored.")
        failed_companies.append({
            "company_name": result.get('company_name', ''),
            "website": result.get('website', '')
        })
        save_json_file(failed_companies, failed_companies_file)
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


async def main(company_info_file='Json_Files/company_info.json', results_file='Json_Files/results.json', max_pages=20):
    company_info = load_company_info(company_info_file)
    
    existing_results = load_json_file(results_file)
    existing_company_names = {result["company_name"] for result in existing_results}

    for company in company_info:
        base_url = company["website"]
        
        if company["company_name"] in existing_company_names:
            print(f"Skipping {company['company_name']} as it already exists in results.")
            continue

        print(f"Crawling website: {base_url}")
        emails, addresses, names, summary_texts = await crawl_website(base_url, max_pages)

        max_length = 10000
        merged_text = " ".join(summary_texts)[:max_length]

        current_summary = ""

        language = detect_language(merged_text)

        first_summary = True

        chunk_size = 2000
        for chunk in chunk_text(merged_text, chunk_size):
            print(f"Text sent to AI (part): {chunk[:chunk_size]}")
            current_summary = generate_summary(chunk, language, current_summary)
            if check_for_info_tag(current_summary):
                current_summary = current_summary.replace("@info@", "")
                if first_summary:
                    company_name = extract_company_name(current_summary)
                    first_summary = False    
                process_information(chunk, addresses, names, company_name)
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
    asyncio.run(main())