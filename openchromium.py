import os
from pathlib import Path
from playwright.sync_api import sync_playwright

def get_extension_paths(extensions_dir):
    extension_paths = []
    for path in Path(extensions_dir).iterdir():
        if path.is_dir():
            extension_paths.append(str(path.resolve()))
    return extension_paths

def launch_chromium_with_extensions(url):
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

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(user_data_dir, headless=False, args=extensions_args)
        page = browser.new_page()
        page.goto(url)

        print("Navigating to:", url)
        input("Press Enter to close the browser...")

        browser.close()

# Exemple d'utilisation
url = 'https://example.com'  # Remplacer par l'URL de votre choix
launch_chromium_with_extensions(url)
