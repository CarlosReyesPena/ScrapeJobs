import subprocess
import sys
import os
import platform

def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def install_latex():
    if platform.system() == 'Linux':
        subprocess.check_call(["sudo", "apt-get", "update"])
        subprocess.check_call(["sudo", "apt-get", "install", "-y", "texlive-full"])
    elif platform.system() == 'Darwin':
        subprocess.check_call(["brew", "install", "mactex-no-gui"])
    elif platform.system() == 'Windows':
        # Télécharger l'installeur MiKTeX
        miktex_installer_url = "https://miktex.org/download/win"
        installer_path = "miktexsetup.exe"
        subprocess.check_call(["curl", "-L", miktex_installer_url, "-o", installer_path])
        
        # Exécuter l'installeur MiKTeX en mode silencieux
        subprocess.check_call([installer_path, "--quiet", "--auto-install=yes"])

        # Supprimer l'installeur
        os.remove(installer_path)
    else:
        print("Votre système d'exploitation n'est pas supporté pour une installation automatique de LaTeX.")
        return False
    return True

def main():
    # Installer les bibliothèques Python nécessaires
    packages = [
        "requests",
        "beautifulsoup4",
        "groq",
        "langdetect"
    ]

    for package in packages:
        print(f"Installation de {package}...")
        install(package)
    
    # Installer LaTeX
    if install_latex():
        print("LaTeX a été installé avec succès.")
    else:
        print("L'installation automatique de LaTeX a échoué ou n'est pas supportée sur ce système. Veuillez installer LaTeX manuellement.")
    
    print("Toutes les bibliothèques nécessaires ont été installées avec succès.")

if __name__ == "__main__":
    main()
