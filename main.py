import os
import shutil
import threading
import time
import json
import tempfile
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import CompanyCraw
import CoverBuilder

def clear_pycache():
    pycache_dir = '__pycache__'
    if os.path.exists(pycache_dir):
        shutil.rmtree(pycache_dir)

class ResultsFileModifiedHandler(FileSystemEventHandler):
    def __init__(self, file_to_watch, callback):
        self.file_to_watch = file_to_watch
        self.callback = callback
        self.last_modified = None
        self.previous_data = self.load_json_file(file_to_watch)

    def load_json_file(self, file_path):
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as file:
                try:
                    return json.load(file)
                except json.JSONDecodeError:
                    return []
        return []

    def on_modified(self, event):
        if event.src_path == self.file_to_watch:
            current_modified = os.path.getmtime(self.file_to_watch)
            if self.last_modified is None or current_modified > self.last_modified:
                self.last_modified = current_modified
                new_data = self.load_json_file(self.file_to_watch)
                diff = self.get_new_entries(self.previous_data, new_data)
                self.previous_data = new_data
                if diff:
                    self.callback(diff)

    def get_new_entries(self, old_data, new_data):
        old_set = {json.dumps(entry, sort_keys=True) for entry in old_data}
        new_entries = [json.loads(entry) for entry in {json.dumps(entry, sort_keys=True) for entry in new_data} - old_set]
        return new_entries

def run_company_craw():
    # Exécuter CompanyCraw pour générer les résultats à partir des URLs
    CompanyCraw.main('Json_Files/base_urls.json', 10)

def run_cover_builder(new_data):
    # Créer un fichier JSON temporaire
    with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.json') as tmp_file:
        json.dump(new_data, tmp_file, ensure_ascii=False, indent=4)
        tmp_file_path = tmp_file.name
    
    try:
        # Utiliser le fichier JSON temporaire pour créer les fichiers PDF
        CoverBuilder.build_covers(tmp_file_path)
    finally:
        # Supprimer le fichier JSON temporaire
        os.remove(tmp_file_path)

def main():
    # Démarrer CompanyCraw dans un thread séparé
    thread_company_craw = threading.Thread(target=run_company_craw)
    thread_company_craw.start()

    # Démarrer la surveillance du fichier results.json
    results_file = os.path.abspath('Json_Files/results.json')
    event_handler = ResultsFileModifiedHandler(file_to_watch=results_file, callback=run_cover_builder)
    observer = Observer()
    observer.schedule(event_handler, path=os.path.dirname(results_file), recursive=False)
    observer.start()

    try:
        # Garder le script en cours d'exécution pour surveiller les modifications du fichier
        while thread_company_craw.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()

    # Supprimer le dossier __pycache__ après l'exécution
    clear_pycache()

if __name__ == "__main__":
    main()
