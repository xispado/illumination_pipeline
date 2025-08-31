# src/llm_handler.py
import os
import requests
import re
import pandas as pd
from src.config_manager import load_global_config, load_project_config

def _get_llm_response(prompt, global_config):
    """Sends a prompt to the configured LLM API and returns the response."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {global_config.get('llm_api_key', 'not-needed')}"
    }
    data = {
        "model": "local-model",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    
    try:
        response = requests.post(global_config['llm_api_url'], headers=headers, json=data)
        response.raise_for_status()
        
        # Standard OpenAI-compatible response format
        return response.json()['choices'][0]['message']['content']
    except requests.RequestException as e:
        print(f"  -> ERROR: Could not connect to LLM API at {global_config['llm_api_url']}")
        print(f"  -> Details: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"  -> ERROR: Received an unexpected response format from the LLM API.")
        print(f"  -> Response JSON: {response.text}")
        return None

def _clean_response(text, parsing_config):
    """Cleans the raw LLM response based on parsing rules."""
    text = text.strip()
    
    if parsing_config.get("strip_code_fences", False):
        text = re.sub(r'^```[\w]*\n', '', text)
        text = re.sub(r'\n```$', '', text)
    
    # Remove quotes from start and end
    text = text.strip('"')

    for prefix in parsing_config.get("ignore_lines_starting_with", []):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].lstrip()
    
    return text

def run_llm_test_suite():
    """Runs a single test of the LLM prompt generation process."""
    print("--- LLM Prompt Generation Test ---")
    
    try:
        global_config = load_global_config()
        with open('llm_test_input.txt', 'r', encoding='utf-8') as f:
            test_text = f.read()
    except FileNotFoundError as e:
        print(f"ERROR: Could not find required file: {e}")
        return

    print("\n1. Preparing the Prompt:")
    template = global_config['llm_prompt_template']
    final_prompt = template.replace("<text>", test_text)
    print(f"  - Prompt Template: {template[:80]}...")
    print(f"  - Input Text: {test_text[:80]}...")
    print(f"  - Final Prompt Sent to LLM: {final_prompt[:120]}...")

    print("\n2. Awaiting LLM Response...")
    raw_response = _get_llm_response(final_prompt, global_config)
    
    if not raw_response:
        print("Test failed. Could not get a response from the LLM.")
        return

    print("\n3. Analyzing the Response:")
    print(f"  - Raw LLM Response: {raw_response}")
    cleaned_response = _clean_response(raw_response, global_config['llm_parsing_config'])
    print(f"  - Cleaned Response: {cleaned_response}")

    print("\n4. Final Result Simulation:")
    print(f"  - Example Parsed Output: 01|01|{cleaned_response}")
    print("\n--- Test Complete ---")


def generate_prompts_for_project(project_path):
    """Generates a prompts CSV file from a book's clean text file."""
    print("\n--- Starting Prompt Generation ---")
    
    project_name = os.path.basename(project_path).replace("_Illumination_Project", "")
    clean_txt_path = os.path.join(project_path, f"{project_name}_clean.txt")
    output_csv_path = os.path.join(project_path, f"{project_name}_prompts.csv")

    if not os.path.exists(clean_txt_path):
        print(f"ERROR: Clean text file not found at '{clean_txt_path}'")
        return

    try:
        global_config = load_global_config()
        with open(clean_txt_path, 'r', encoding='utf-8') as f:
            full_text = f.read()
    except Exception as e:
        print(f"ERROR: Could not load required files. {e}")
        return

    chapters = full_text.split("==CHAPTER==")
    all_prompts = []
    
    print(f"Found {len(chapters)} chapters to process.")
    
    # Simple chunking by paragraph. A more advanced "smart chunking" could be implemented here.
    for i, chapter_text in enumerate(chapters):
        chapter_num = i + 1
        if not chapter_text.strip():
            continue

        print(f"\nProcessing Chapter {chapter_num}...")
        paragraphs = [p.strip() for p in chapter_text.split('\n\n') if p.strip()]
        
        for j, paragraph in enumerate(paragraphs):
            scene_num = j + 1
            print(f"  - Generating prompt for Chapter {chapter_num}, Scene {scene_num}...")

            prompt_template = global_config['llm_prompt_template']
            final_prompt = prompt_template.replace("<text>", paragraph)
            
            raw_response = _get_llm_response(final_prompt, global_config)
            if raw_response:
                cleaned_response = _clean_response(raw_response, global_config['llm_parsing_config'])
                all_prompts.append({
                    'chapter': chapter_num, 
                    'scene': scene_num, 
                    'prompt': cleaned_response
                })
    
    if not all_prompts:
        print("\nNo prompts were generated. The process may have failed or the book text was empty.")
        return

    df = pd.DataFrame(all_prompts)
    df.to_csv(output_csv_path, sep='|', index=False)
    print(f"\nSUCCESS: Saved {len(all_prompts)} prompts to '{output_csv_path}'")