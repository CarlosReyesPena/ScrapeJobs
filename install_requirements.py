import subprocess
import sys

def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def main():
    packages = [
        "requests",
        "beautifulsoup4",
        "groq",
        "langdetect",
        "watchdog"
    ]

    for package in packages:
        print(f"Installation de {package}...")
        install(package)
    print("Toutes les bibliothèques nécessaires ont été installées avec succès.")

if __name__ == "__main__":
    main()
