# src/project_manager.py
import os
import sys
import subprocess
import json
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from pathlib import Path

from src.config_manager import get_default_project_config

PROJECT_SUFFIX = "_Illumination_Project"
BOOKS_FOLDER = "Books"
ILLUMINATIONS_FOLDER = "Illuminations"

def ensure_project_folders_exist():
    """Creates the core input/output folders if they don't exist."""
    os.makedirs(BOOKS_FOLDER, exist_ok=True)
    os.makedirs(ILLUMINATIONS_FOLDER, exist_ok=True)

def find_projects():
    """Finds all existing project folders."""
    projects = []
    if not os.path.exists(ILLUMINATIONS_FOLDER):
        return []
    for item in os.listdir(ILLUMINATIONS_FOLDER):
        item_path = os.path.join(ILLUMINATIONS_FOLDER, item)
        if os.path.isdir(item_path) and item.endswith(PROJECT_SUFFIX):
            project_name = item.replace(PROJECT_SUFFIX, "")
            projects.append((project_name, item_path))
    return sorted(projects)

def find_importable_epubs():
    """Finds .epub files in the Books folder that don't have a project yet."""
    epubs = []
    existing_project_names = [p[0] for p in find_projects()]
    if not os.path.exists(BOOKS_FOLDER):
        return []
    for item in os.listdir(BOOKS_FOLDER):
        if item.lower().endswith(".epub"):
            book_name = Path(item).stem
            if book_name not in existing_project_names:
                epubs.append(item)
    return sorted(epubs)

def create_project_structure(epub_name):
    """Creates the folder structure and initial files for a new project."""
    epub_path = os.path.join(BOOKS_FOLDER, epub_name)
    book_name = Path(epub_path).stem
    project_folder = os.path.join(ILLUMINATIONS_FOLDER, f"{book_name}{PROJECT_SUFFIX}")
    images_folder = os.path.join(project_folder, "images")
    
    print(f"Creating new project for '{book_name}'...")
    os.makedirs(images_folder, exist_ok=True)
    
    clean_txt_path = os.path.join(project_folder, f"{book_name}_clean.txt")
    try:
        print(f"  - Converting EPUB...")
        book = epub.read_epub(epub_path)
        full_text_parts = ["==CHAPTER=="]
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            paragraphs = [p.get_text(strip=True) for p in soup.find_all('p') if p.get_text(strip=True)]
            if paragraphs:
                full_text_parts.append('\n\n'.join(paragraphs))
                full_text_parts.append("\n\n==CHAPTER==\n\n")

        with open(clean_txt_path, 'w', encoding='utf-8') as f:
            f.write(''.join(full_text_parts))
        print("  - Conversion successful.")
    except Exception as e:
        print(f"  - ERROR converting EPUB: {e}")
        return False

    config_path = os.path.join(project_folder, "config.json")
    default_config = get_default_project_config()
    
    with open(config_path, 'w') as f:
        json.dump(default_config, f, indent=4)
    print(f"  - Created project 'config.json' from global defaults.")

    print("\nProject created successfully!")
    print(f"IMPORTANT: Please manually edit '{clean_txt_path}' to remove unwanted text before generating prompts.")
    
    try:
        os.startfile(clean_txt_path)
    except AttributeError:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.call([opener, clean_txt_path])
    except Exception:
        print("\nCould not automatically open the text file. Please open it manually.")
    return True