import os
import shutil
import threading
import time
import json
import subprocess

def clear_pycache():
    pycache_dir = '__pycache__'
    if os.path.exists(pycache_dir):
        shutil.rmtree(pycache_dir)

def run_company_craw():
    # Exécuter CompanyCraw pour générer les résultats à partir des URLs
    subprocess.run(['python', 'CompanyCraw.py', 'Json_Files/company_info.json', '20'])

def run_mailsender():
    # Exécuter Mailsender pour gérer les brouillons et envoyer les e-mails
    subprocess.run(['python', 'Mailsender.py'])

def create_empty_results_file():
    results_file = 'Json_Files/results.json'
    if not os.path.exists(results_file):
        with open(results_file, 'w', encoding='utf-8') as file:
            json.dump([], file)
        print(f"Created empty {results_file}")

def main():
    create_empty_results_file()

    # Démarrer CompanyCraw dans un thread séparé
    thread_company_craw = threading.Thread(target=run_company_craw)
    thread_company_craw.start()

    # Démarrer Mailsender dans un thread séparé
    thread_mailsender = threading.Thread(target=run_mailsender)
    thread_mailsender.start()

    try:
        # Garder le script en cours d'exécution pour surveiller les threads
        while thread_company_craw.is_alive() or thread_mailsender.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    thread_company_craw.join()
    thread_mailsender.join()

    # Supprimer le dossier __pycache__ après l'exécution
    clear_pycache()

if __name__ == "__main__":
    main()
