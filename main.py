# main.py
import os
import sys

# Import functions from our new modules
from src.project_manager import (
    ensure_project_folders_exist,
    find_projects,
    find_importable_epubs,
    create_project_structure,
)
from src.llm_handler import run_llm_test_suite, generate_prompts_for_project
from src.image_generator import run_image_generation, run_upscaling_process

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def press_enter_to_continue():
    input("\nPress Enter to return to the menu...")

def handle_import_new_book():
    clear_screen()
    epubs = find_importable_epubs()
    if not epubs:
        print("No new .epub files found in the 'Books' directory.")
        press_enter_to_continue()
        return

    print("=== Import New Book ===")
    for i, epub in enumerate(epubs):
        print(f"[{i+1}] {epub}")
    print("\n(B)ack to Main Menu")
    
    choice = input("Select an EPUB to import: ").lower()
    if choice == 'b': return

    try:
        index = int(choice) - 1
        if 0 <= index < len(epubs):
            create_project_structure(epubs[index])
        else:
            print("Invalid selection.")
    except (ValueError, IndexError):
        print("Invalid input.")
    press_enter_to_continue()

def handle_single_image(project_path):
    print("\n--- Generate Single Fill-in Image ---")
    user_input = input("Enter details (e.g., ch:04, a beautiful spaceship): ")
    try:
        chapter_part, prompt_part = user_input.split(',', 1)
        chapter_num = int(chapter_part.lower().replace("ch:", "").strip())
        run_image_generation(project_path, single_image_details=(chapter_num, prompt_part.strip()))
    except (ValueError, IndexError):
        print("\nInvalid format. Please try again.")
    press_enter_to_continue()

def handle_project_menu(project_name, project_path):
    while True:
        clear_screen()
        print(f"=== Project: {project_name} ===")
        
        prompts_exist = os.path.exists(os.path.join(project_path, f"{project_name}_prompts.csv"))
        
        if not prompts_exist:
            print("Status: Ready for Prompt Generation.")
            print("\n[1] Generate prompts from book text")
            print("(B)ack to Main Menu")
            choice = input("\nSelect an option: ").lower()
            if choice == '1':
                generate_prompts_for_project(project_path)
                press_enter_to_continue()
            elif choice == 'b': return
        else:
            print("Status: Ready for Image Generation.")
            print("\n[1] Generate/Continue image generation")
            print("[2] Generate a single fill-in image")
            print("[3] Upscale generated images")
            print("---------------------------")
            print("(R)e-run prompt generation (deletes existing prompts)")
            print("(B)ack to Main Menu")
            choice = input("\nSelect an option: ").lower()

            if choice == '1':
                run_image_generation(project_path)
                press_enter_to_continue()
            elif choice == '2':
                handle_single_image(project_path)
            elif choice == '3':
                run_upscaling_process(project_path)
                press_enter_to_continue()
            elif choice == 'r':
                if input("Are you sure? (y/n): ").lower() == 'y':
                    os.remove(os.path.join(project_path, f"{project_name}_prompts.csv"))
            elif choice == 'b': return

def main():
    ensure_project_folders_exist()
    while True:
        clear_screen()
        print("=== Illumination Pipeline V2 ===")
        projects = find_projects()
        
        if projects:
            print("\nExisting Illuminations:")
            for i, (name, path) in enumerate(projects):
                print(f"[{i+1}] {name}")
        else:
            print("\nNo existing projects found.")

        print("\n---------------------------")
        print("(I)mport New Book from 'Books' folder")
        print("(T)est LLM Prompt Generation")
        print("(Q)uit")

        choice = input("\nSelect a project or an option: ").lower()

        if choice == 'q': break
        elif choice == 'i': handle_import_new_book()
        elif choice == 't': 
            run_llm_test_suite()
            press_enter_to_continue()
        else:
            try:
                index = int(choice) - 1
                if 0 <= index < len(projects):
                    handle_project_menu(*projects[index])
            except (ValueError, IndexError):
                print("Invalid input.")

if __name__ == "__main__":
    main()