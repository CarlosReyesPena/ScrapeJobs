import os
import shutil
import threading
import time
import json
import subprocess

# Fonction pour supprimer le dossier __pycache__
def clear_pycache():
    pycache_dir = '__pycache__'
    if os.path.exists(pycache_dir):
        shutil.rmtree(pycache_dir)

# Fonction pour exécuter CompanyCraw
def run_company_craw():
    try:
        subprocess.run(['python', 'CompanyCraw.py', 'Json_Files/company_info.json', '20'], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running CompanyCraw: {e}")
    except Exception as e:
        print(f"Unexpected error running CompanyCraw: {e}")

# Fonction pour exécuter Mailsender
def run_mailsender():
    try:
        subprocess.run(['python', 'Mailsender.py'], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running Mailsender: {e}")
    except Exception as e:
        print(f"Unexpected error running Mailsender: {e}")

# Fonction pour créer un fichier results.json vide
def create_empty_results_file():
    results_file = 'Json_Files/results.json'
    if not os.path.exists(results_file):
        try:
            with open(results_file, 'w', encoding='utf-8') as file:
                json.dump([], file)
            print(f"Created empty {results_file}")
        except IOError as e:
            print(f"Error creating empty results file: {e}")

# Fonction principale
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
        print("Script interrupted by user")
    finally:
        thread_company_craw.join()
        thread_mailsender.join()

    # Supprimer le dossier __pycache__ après l'exécution
    clear_pycache()

if __name__ == "__main__":
    main()
