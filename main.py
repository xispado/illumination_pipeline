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
from src.llm_handler import run_single_text_test_suite, run_chunking_test_suite, generate_prompts_for_project
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
    print("Enter details in the format: chapter_number: your prompt here")
    user_input = input("Example -> 04: a beautiful spaceship landing on a red planet\n> ")
    
    try:
        # Split on the first colon. This is more flexible than a comma.
        parts = user_input.split(':', 1)
        if len(parts) != 2:
            raise ValueError("Input must contain a colon ':' to separate chapter and prompt.")

        chapter_part, prompt_part = parts
        
        # Simply strip whitespace and convert to int. Much cleaner.
        chapter_num = int(chapter_part.strip())
        
        run_image_generation(project_path, single_image_details=(chapter_num, prompt_part.strip()))

    except (ValueError, IndexError) as e:
        print(f"\nInvalid format. Please try again. ({e})")
    
    press_enter_to_continue()
    
def handle_chunking_test():
    clear_screen()
    print("--- Chunking & Prompt Test Suite ---")
    projects = find_projects()
    if not projects:
        print("No projects found. Please import a book first.")
        press_enter_to_continue()
        return

    print("\nSelect a project to test against:")
    for i, (name, path) in enumerate(projects):
        print(f"[{i+1}] {name}")
    
    try:
        proj_choice = input("\nProject number: ")
        proj_index = int(proj_choice) - 1
        if not (0 <= proj_index < len(projects)):
            print("Invalid project selection."); press_enter_to_continue(); return
        
        project_path = projects[proj_index][1]

        num_chunks_str = input("How many chunks from the beginning of the book would you like to test? ")
        num_chunks = int(num_chunks_str)
        if num_chunks <= 0:
            print("Please enter a positive number."); press_enter_to_continue(); return

        run_chunking_test_suite(project_path, num_chunks)

    except (ValueError, IndexError):
        print("Invalid input.")
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
    os.system("")
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
            print("\nNo projects found.")

        print("\n---------------------------")
        print("(I)mport New Book from 'Books' folder")
        print("\n--- Testing Suites ---")
        print("(C)hunking & Prompt Test (Live Data)")
        print("(S)ingle Text Test (llm_test_input.txt)")
        print("\n(Q)uit")

        choice = input("\nSelect a project or an option: ").lower()

        if choice == 'q': break
        elif choice == 'i': handle_import_new_book()
        elif choice == 'c': handle_chunking_test()
        elif choice == 's': 
            run_single_text_test_suite()
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