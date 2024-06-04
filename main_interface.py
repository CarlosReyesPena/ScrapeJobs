import tkinter as tk
from tkinter import filedialog, messagebox, Listbox, Scrollbar
import os
import json
import shutil
import CompanyCraw
import CoverBuilder

class Application(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
        self.pack()
        self.create_widgets()

    def create_widgets(self):
        self.url_label = tk.Label(self, text="Collez vos liens internet ci-dessous (un par ligne) :")
        self.url_label.pack(pady=5)

        self.url_text = tk.Text(self, height=10, width=80)
        self.url_text.pack(pady=5)

        self.run_button = tk.Button(self, text="Run", command=self.run_program)
        self.run_button.pack(pady=5)

        self.pdf_label = tk.Label(self, text="Fichiers PDF générés :")
        self.pdf_label.pack(pady=5)

        self.pdf_listbox = Listbox(self, height=10, width=80)
        self.pdf_listbox.pack(pady=5)

        self.scrollbar = Scrollbar(self)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.pdf_listbox.config(yscrollcommand=self.scrollbar.set)
        self.scrollbar.config(command=self.pdf_listbox.yview)

        self.pdf_listbox.bind('<Double-1>', self.open_pdf)

    def run_program(self):
        urls = self.url_text.get("1.0", tk.END).strip().split('\n')
        urls = [url.strip() for url in urls if url.strip()]

        if not urls:
            messagebox.showerror("Erreur", "Veuillez entrer au moins un lien internet.")
            return

        # Sauvegarder les URLs dans un fichier JSON pour les passer à CompanyCraw.py
        with open('base_urls.json', 'w', encoding='utf-8') as file:
            json.dump(urls, file)

        try:
            # Exécuter CompanyCraw pour générer les résultats
            CompanyCraw.main('base_urls.json', 50)
            # Exécuter CoverBuilder pour utiliser les résultats générés et créer les fichiers PDF
            CoverBuilder.build_covers('results.json')

            self.update_pdf_list()
            messagebox.showinfo("Succès", "Le programme a été exécuté avec succès.")
        except Exception as e:
            messagebox.showerror("Erreur", f"Une erreur est survenue : {e}")

    def update_pdf_list(self):
        self.pdf_listbox.delete(0, tk.END)
        pdf_dir = 'Cover_PDF'
        if os.path.exists(pdf_dir):
            pdf_files = [f for f in os.listdir(pdf_dir) if f.endswith('.pdf')]
            for pdf in pdf_files:
                self.pdf_listbox.insert(tk.END, pdf)

    def open_pdf(self, event):
        selection = event.widget.curselection()
        if selection:
            index = selection[0]
            pdf_file = event.widget.get(index)
            os.startfile(os.path.join('Cover_PDF', pdf_file))

def clear_pycache():
    pycache_dir = '__pycache__'
    if os.path.exists(pycache_dir):
        shutil.rmtree(pycache_dir)
        print(f"Dossier {pycache_dir} supprimé.")

def main():
    clear_pycache()
    root = tk.Tk()
    root.title("Interface Utilisateur")
    app = Application(master=root)
    app.mainloop()
    clear_pycache()

if __name__ == "__main__":
    main()
