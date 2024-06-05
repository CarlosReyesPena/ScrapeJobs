import os
import re
import requests
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

# Charger les URLs à partir du fichier JSON
def load_base_urls(json_file='Json_Files/base_urls.json'):
    with open(json_file, 'r', encoding='utf-8') as file:
        return json.load(file)
    
# Fonction pour charger les mots-clés à partir d'un fichier JSON
def load_keywords(json_file_path='Json_Files/keywords.json'):
    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    keywords_cat1 = data['cat_1']
    keywords_cat2 = data['cat_2']
    
    return keywords_cat1, keywords_cat2


# Fonction pour extraire les e-mails d'une page HTML
def extract_emails_with_context(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    visible_text = soup.get_text(separator=' ', strip=True)
    
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = []
    
    for match in re.finditer(email_pattern, visible_text):
        email = match.group()
        start = max(match.start() - 200, 0)
        end = min(match.end() + 200, len(visible_text))
        context = visible_text[start:end]
        emails.append((email, context))
    
    return emails

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
def get_internal_links(base_url, html_content, keywords_cat1, keywords_cat2):
    parsed_base_url = urlparse(base_url)
    base_domain = parsed_base_url.netloc
    soup = BeautifulSoup(html_content, 'html.parser')
    cat1_links = set()
    cat2_links = set()
    other_links = set()
    
    for link in soup.find_all('a', href=True):
        href = link['href']
        link_text = link.get_text(separator=' ', strip=True)
        if href.startswith('/'):
            full_url = urljoin(base_url, href)
        else:
            full_url = href

        parsed_full_url = urlparse(full_url)
        if base_domain in parsed_full_url.netloc:
            if has_extension(full_url):
                if contains_keyword(full_url, link_text, keywords_cat1):
                    cat1_links.add(full_url)
                elif contains_keyword(full_url, link_text, keywords_cat2):
                    cat2_links.add(full_url)
                else:
                    other_links.add(full_url)
    
    # Lecture du fichier JSON existant pour ajouter les nouveaux liens
    try:
        with open('classified_links.json', 'r', encoding='utf-8') as file:
            existing_links = json.load(file)
    except FileNotFoundError:
        existing_links = {
            "cat1_links": [],
            "cat2_links": [],
            "other_links": []
        }
    
    # Fusion des nouveaux liens avec ceux existants en évitant les doublons
    existing_links["cat1_links"] = list(set(existing_links["cat1_links"]) | cat1_links)
    existing_links["cat2_links"] = list(set(existing_links["cat2_links"]) | cat2_links)
    existing_links["other_links"] = list(set(existing_links["other_links"]) | other_links)
    
    # Écriture des liens mis à jour dans le fichier JSON
    with open('classified_links.json', 'w', encoding='utf-8') as file:
        json.dump(existing_links, file, ensure_ascii=False, indent=4)
    
    return cat1_links, cat2_links, other_links

# Fonction pour vérifier si une URL ne contient pas d'extension
def has_extension(url):
    return not re.search(r'\.\w+$', url)

def extract_information(context):
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are an expert in extracting specific information from text and providing structured outputs in JSON format."
            },
            {
                "role": "user",
                "content": f"From the following text: {context}, extract the physical addresses and person names. Do not include any post office boxes (e.g., 'Case postale' or 'P.O. Box'). Provide the results in the following JSON format: {{\"addresses\": [], \"names\": []}} You MUST respond only the json and only in this format."
            }
        ],
        model="llama3-70b-8192",
    )
    return chat_completion.choices[0].message.content.strip()

def clean_json_string(json_str):
    json_str = json_str.replace("'", '"')  # Remplace les guillemets simples par des guillemets doubles
    return json_str

def extract_address(context):
    result = extract_information(context) 
    try:
        # Recherche le début et la fin du JSON
        start_index = result.index('{')
        end_index = result.rindex('}') + 1
        json_str = result[start_index:end_index]
        cleaned_json_str = clean_json_string(json_str)
        
        return json.loads(cleaned_json_str)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Error extracting or decoding JSON: {e}")
        return {"addresses": [], "names": []}

# Fonction principale pour parcourir le site et extraire les e-mails et adresses
def crawl_website(base_url, max_pages):
    visited_urls = set()
    emails = []
    addresses = []
    names = []
    processed_emails = {}
    all_texts = []
    visited_links_order = []

    # Chargement des mots-clés à partir du fichier JSON
    keywords_cat1, keywords_cat2 = load_keywords("Json_Files/keywords.json")

    to_visit = [[] for _ in range(3)]  # Une liste de listes pour les catégories : [cat1_links, cat2_links, other_links]

    html_content = fetch_page(base_url)
    
    to_visit[0].append(base_url)  # Ajouter l'URL de départ dans la catégorie "cat1_links"
    if html_content:
        cat1_links, cat2_links, other_links = get_internal_links(base_url, html_content, keywords_cat1, keywords_cat2)
        to_visit[0].extend(list(cat1_links))
        to_visit[1].extend(list(cat2_links))
        to_visit[2].extend(list(other_links))

    current_category = 0

    while any(to_visit) and len(visited_urls) < max_pages:
        while to_visit[current_category]:
            current_url = to_visit[current_category].pop(0)

            if current_url in visited_urls:
                continue

            visited_urls.add(current_url)
            visited_links_order.append(current_url)
            
            html_content = fetch_page(current_url)
            if html_content:
                print(f"Visiting: {current_url}")
                emails_with_context = extract_emails_with_context(html_content)
                for email, context in emails_with_context:
                    print(f"Email found: {email}")
                    if email not in processed_emails:
                        information = extract_address(context)
                        if information["addresses"]:
                            for address in information["addresses"]:
                                print(f"Address found: {address}")
                                addresses.append(address)
                        if information["names"]:
                            for name in information["names"]:
                                print(f"Name found: {name}")
                                names.append(name)
                        processed_emails[email] = information
                    if email not in emails:
                        emails.append(email)
                
                soup = BeautifulSoup(html_content, 'html.parser')
                visible_text = soup.get_text(separator=' ', strip=True)
                all_texts.append(visible_text)
                
                # Obtenir les liens internes de la page courante et les ajouter dans l'ordre de priorité
                cat1_links, cat2_links, other_links = get_internal_links(current_url, html_content, keywords_cat1, keywords_cat2)
                to_visit[0].extend(list(cat1_links - visited_urls))
                to_visit[1].extend(list(cat2_links - visited_urls))
                to_visit[2].extend(list(other_links - visited_urls))
        
        current_category += 1
        if current_category >= len(to_visit):
            break
    
    # Écriture des liens visités dans un fichier texte
    with open('visited_links.txt', 'w', encoding='utf-8') as file:
        for link in visited_links_order:
            file.write(link + '\n')

    return emails, addresses, names, all_texts

# Fonction pour détecter la langue du contenu
def detect_language(text):
    try:
        return detect(text)
    except LangDetectException:
        return "en"

# Fonction pour générer un résumé en utilisant le modèle "llama3-70b-8192"
def generate_summary(content, language):
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are an expert in summarizing company information."
            },
            {
                "role": "user",
                "content": f"You must provide only the description of the company, without any preliminary indication, using the following content: {content}. Ensure the description is detailed, covering aspects such as the company's history, mission, key products or services, target market, and unique selling points. Do not invent any information. The response must be in {language}."
            }
        ],
        model="llama3-70b-8192",
    )
    return chat_completion.choices[0].message.content

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


# Fonction pour exécuter le processus complet de crawl et de génération de résultats
def main(json_file='Json_Files/base_urls.json', max_pages=10):
    base_urls = load_base_urls(json_file)
    results = []

    for base_url in base_urls:
        emails, addresses, names, all_texts = crawl_website(base_url, max_pages)

        max_length = 5000
        merged_text = " ".join(all_texts)[:max_length]

        print(f"Texte envoyé à l'IA :", merged_text[:1000])

        language = detect_language(merged_text)
        summary = generate_summary(merged_text, language)
        company_name = extract_company_name(summary)

        print(f"Adresses e-mail trouvées :", emails)
        print(f"Adresses trouvées :", addresses)
        print(f"Noms trouvés :", names)
        print(f"Nom de l'entreprise :", company_name)
        print(f"Résumé de l'entreprise :", summary)

        result = {
            "company_name": company_name,
            "summary": summary,
            "mails": list(emails),
            "addresses": list(addresses),
            "personal_names": list(names)
        }

        results.append(result)

        # Écriture des résultats mis à jour dans un fichier JSON
        with open('Json_Files/results.json', mode='w', encoding='utf-8') as file:
            json.dump(results, file, ensure_ascii=False, indent=4)
    

if __name__ == "__main__":
    main()
