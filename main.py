import os
import shutil
import CompanyCraw
import CoverBuilder

def clear_pycache():
    pycache_dir = '__pycache__'
    if os.path.exists(pycache_dir):
        shutil.rmtree(pycache_dir)

def main():

    # Exécuter CompanyCraw pour générer les résultats à partir des URLs
    CompanyCraw.main('base_urls.json', 100)
    
    # Exécuter CoverBuilder pour utiliser les résultats générés et créer les fichiers PDF
    CoverBuilder.build_covers('results.json')
    
    # Supprimer le dossier __pycache__ après l'exécution
    clear_pycache()

if __name__ == "__main__":
    main()
