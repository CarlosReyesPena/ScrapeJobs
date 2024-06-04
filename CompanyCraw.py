import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
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

# Fonction pour extraire les e-mails d'une page HTML
def extract_emails_with_context(html_content):
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = []
    for match in re.finditer(email_pattern, html_content):
        email = match.group()
        start = max(match.start() - 500, 0)
        end = min(match.end() + 500, len(html_content))
        context = html_content[start:end]
        emails.append((email, context))
    return emails

# Fonction pour récupérer le contenu d'une page web
def fetch_page(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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

# Fonction pour analyser une page et trouver des liens internes
def get_internal_links(base_url, html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    links = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.startswith('/'):
            full_url = urljoin(base_url, href)
            if has_extension(full_url):
                links.add(full_url)
        elif href.startswith(base_url):
            if has_extension(href):
                links.add(href)
    return links

# Fonction pour vérifier si une URL ne contient pas d'extension
def has_extension(url):
    return not re.search(r'\.\w+$', url)

def extract_address(context):
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are an expert in identifying physical addresses from text."
            },
            {
                "role": "user",
                "content": f"Extract only the physical address from the following text: {context}. Do not include any post office boxes (e.g., 'Case postale' or 'P.O. Box'). If no address is found, respond with '@NoAddress'. Provide only the address or '@NoAddress'."
            }
        ],
        model="llama3-70b-8192",
    )
    return chat_completion.choices[0].message.content.strip()

# Fonction principale pour parcourir le site et extraire les e-mails et adresses
def crawl_website(base_urls, max_pages=50):
    visited_urls = set()
    emails = set()
    addresses = set()
    processed_emails = {}
    all_texts = []

    for base_url in base_urls:
        to_visit = {base_url}
        while to_visit and len(visited_urls) < max_pages:
            current_url = to_visit.pop()
            if current_url in visited_urls:
                continue
            visited_urls.add(current_url)
            
            html_content = fetch_page(current_url)
            if html_content:
                print(f"Visiting: {current_url}")
                emails_with_context = extract_emails_with_context(html_content)
                for email, context in emails_with_context:
                    print(f"Email found: {email}")
                    if email not in processed_emails:
                        address = extract_address(context)
                        if address and "@NoAddress" not in address:
                            print(f"Address found: {address}")
                            addresses.add(address)
                            processed_emails[email] = address
                        else:
                            processed_emails[email] = None
                    emails.add(email)
                
                soup = BeautifulSoup(html_content, 'html.parser')
                visible_text = soup.get_text(separator=' ', strip=True)
                all_texts.append(visible_text)
                
                try:
                    internal_links = get_internal_links(base_url, html_content)
                    to_visit.update(internal_links - visited_urls)
                except Exception as e:
                    print(f"Erreur lors de l'analyse des liens internes de {current_url}: {e}")

    return emails, addresses, all_texts

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
                "content": f"You must provide only the description of the company, without any preliminary indication, using the following content: {content}. The response must be in {language}."
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
def main(json_file='Json_Files/base_urls.json', max_pages=50):
    base_urls = load_base_urls(json_file)
    emails, addresses, all_texts = crawl_website(base_urls, max_pages)

    max_length = 5000
    merged_text = " ".join(all_texts)[:max_length]

    print(f"Texte envoyé à l'IA :", merged_text[:1000])

    language = detect_language(merged_text)
    summary = generate_summary(merged_text, language)
    company_name = extract_company_name(summary)

    print(f"Adresses e-mail trouvées :", emails)
    print(f"Adresses trouvées :", addresses)
    print(f"Nom de l'entreprise :", company_name)
    print(f"Résumé de l'entreprise :", summary)

    results = [{
        "name": company_name,
        "summary": summary,
        "mails": list(emails),
        "addresses": list(addresses)
    }]

    # Écriture des résultats dans un fichier JSON
    with open('Json_Files/results.json', mode='w', encoding='utf-8') as file:
        json.dump(results, file, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    main()
