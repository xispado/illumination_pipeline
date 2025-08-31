# src/llm_handler.py
import os
import requests
import re
import pandas as pd
import concurrent.futures
from tqdm import tqdm
from src.config_manager import load_global_config

# NEW helper function to load the prompt template
def _get_prompt_template(global_config):
    """Loads the prompt template from the specified file."""
    template_file = global_config.get("llm_prompt_template_file", "prompt_template.txt")
    if not os.path.exists(template_file):
        raise FileNotFoundError(f"Prompt template file not found: {template_file}")
    with open(template_file, 'r', encoding='utf-8') as f:
        return f.read()

# --- (The following functions are the same as before, but now they will call _get_prompt_template) ---

class Colors:
    CYAN = '\033[96m'; YELLOW = '\033[93m'; GREEN = '\033[92m'; BOLD = '\033[1m'; ENDC = '\033[0m'

def _smart_chunk_text(text, max_chunk_words):
    if not text.strip() or max_chunk_words <= 0: return []
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    chunks, current_chunk_words = [], []
    for paragraph in paragraphs:
        paragraph_words = paragraph.split()
        if not paragraph_words: continue
        if current_chunk_words and (len(current_chunk_words) + len(paragraph_words)) > max_chunk_words:
            chunks.append(" ".join(current_chunk_words)); current_chunk_words = []
        current_chunk_words.extend(paragraph_words)
    if current_chunk_words: chunks.append(" ".join(current_chunk_words))
    return chunks

def _get_llm_response(prompt, global_config):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {global_config.get('llm_api_key', 'not-needed')}"}
    data = {"model": global_config.get("llm_model_name", "local-model"), "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
    try:
        response = requests.post(global_config['llm_api_url'], headers=headers, json=data, timeout=60)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e: return {"error": f"API Request Failed: {e}"}
    except (KeyError, IndexError): return {"error": "Invalid API Response Format"}

def _clean_response(text, parsing_config):
    if not isinstance(text, str): return ""
    text = text.strip()
    if parsing_config.get("strip_code_fences", False):
        text = re.sub(r'^```[\w]*\n', '', text); text = re.sub(r'\n```$', '', text)
    text = text.strip('"')
    for prefix in parsing_config.get("ignore_lines_starting_with", []):
        if text.lower().startswith(prefix.lower()): text = text[len(prefix):].lstrip(' :')
    return text

def _process_chunk(args):
    chunk_data, global_config, prompt_template = args
    final_prompt = prompt_template.replace("<text>", chunk_data['chunk'])
    raw_response = _get_llm_response(final_prompt, global_config)
    if isinstance(raw_response, dict) and 'error' in raw_response:
        print(f"\nERROR for Chapter {chunk_data['chapter_num']}, Scene {chunk_data['scene_num']}: {raw_response['error']}")
        return None
    cleaned_response = _clean_response(raw_response, global_config['llm_parsing_config'])
    return {'chapter': chunk_data['chapter_num'], 'scene': chunk_data['scene_num'], 'prompt': cleaned_response}

def run_chunking_test_suite(project_path, num_chunks_to_test):
    clear_screen(); print("--- Chunking & Prompt Test Suite (Live Data) ---")
    project_name = os.path.basename(project_path)
    clean_txt_path = os.path.join(project_path, f"{project_name}_clean.txt")
    try:
        global_config = load_global_config()
        prompt_template = _get_prompt_template(global_config) # <-- LOAD TEMPLATE
        with open(clean_txt_path, 'r', encoding='utf-8') as f: full_text = f.read()
    except Exception as e:
        print(f"ERROR: Could not load required files. {e}"); return
    cleaned_full_text = full_text.replace("==CHAPTER==", " ").strip()
    chunk_size = global_config.get("llm_chunk_size_words", 350)
    all_chunks = _smart_chunk_text(cleaned_full_text, chunk_size)
    if not all_chunks:
        print("Could not find any text chunks in the selected book."); return
    chunks_to_test = all_chunks[:num_chunks_to_test]
    print(f"Reloaded global_config.json & prompt template. Testing the first {len(chunks_to_test)} of {len(all_chunks)} total chunks.\n")
    for i, chunk in enumerate(chunks_to_test):
        print(f"--- Chunk {i+1}/{len(chunks_to_test)} ---")
        
        print(f"{Colors.BOLD}CHUNK TEXT:{Colors.ENDC}")
        print(f"{Colors.CYAN}\"{chunk[:300]}...\"{Colors.ENDC}\n")
        
        prompt_template = _get_prompt_template(global_config)
        template_parts = prompt_template.split('<text>')
        
        print(f"{Colors.BOLD}FULL PROMPT SENT TO LLM:{Colors.ENDC}")
        if len(template_parts) == 2:
            before_text, after_text = template_parts
            print(f"{Colors.YELLOW}\"{before_text}{Colors.CYAN}{chunk}{Colors.YELLOW}{after_text}\"{Colors.ENDC}\n")
        else:
            final_prompt = prompt_template.replace("<text>", chunk)
            print(f"{Colors.YELLOW}\"{final_prompt}\"{Colors.ENDC}\n")

        print(f"{Colors.BOLD}LLM RESPONSE:{Colors.ENDC}")
        final_prompt = prompt_template.replace("<text>", chunk)
        raw_response = _get_llm_response(final_prompt, global_config)
        
        # THIS IS THE PART THAT WAS MISSING
        if isinstance(raw_response, dict) and 'error' in raw_response:
            print(f"  -> ERROR: {raw_response['error']}")
        else:
            print(f"  -> {Colors.GREEN}\"{raw_response}\"{Colors.ENDC}")
        
        print("\n" + "="*80 + "\n")

def run_single_text_test_suite():
    clear_screen(); print("--- Single Text Test Suite ---")
    try:
        print("1. Loading configurations..."); global_config = load_global_config()
        prompt_template = _get_prompt_template(global_config) # <-- LOAD TEMPLATE
        with open('llm_test_input.txt', 'r', encoding='utf-8') as f: test_text = f.read()
        print("   ...done.")
    except Exception as e:
        print(f"ERROR: Could not find required file: {e}"); return
    print("\n2. Preparing the Prompt:")
    final_prompt = prompt_template.replace("<text>", test_text)
    print(f"  - Prompt Template File: {global_config.get('llm_prompt_template_file')}")
    print(f"  - Model to be used: {global_config.get('llm_model_name', 'default')}")
    print(f"  - Final Prompt Sent to LLM: \n      \"{final_prompt}\"")
    print("\n3. Sending request to LLM API...")
    raw_response = _get_llm_response(final_prompt, global_config)
    if isinstance(raw_response, dict) and 'error' in raw_response:
        print(f"\n--- Test Failed: {raw_response['error']} ---"); return
    print("   ...response received.")
    print("\n4. Analyzing the Response:"); print(f"  - Raw LLM Response: \"{raw_response}\"")
    cleaned_response = _clean_response(raw_response, global_config['llm_parsing_config'])
    print(f"  - Cleaned Response (after parsing rules): \"{cleaned_response}\"")
    print("\n5. Final Result Simulation:"); print(f"  - Example Parsed Output: 01|01|{cleaned_response}")
    print("\n--- Test Complete ---")

def generate_prompts_for_project(project_path):
    clear_screen(); print("--- Starting High-Speed Prompt Generation (with Smart Chunking) ---")
    project_name = os.path.basename(project_path)
    clean_txt_path = os.path.join(project_path, f"{project_name}_clean.txt")
    output_csv_path = os.path.join(project_path, f"{project_name}_prompts.csv")
    try:
        global_config = load_global_config()
        prompt_template = _get_prompt_template(global_config) # <-- LOAD TEMPLATE
        with open(clean_txt_path, 'r', encoding='utf-8') as f: full_text = f.read()
    except Exception as e:
        print(f"ERROR: Could not load required files. {e}"); return
    chapters = [ch for ch in full_text.split("==CHAPTER==") if ch.strip()]
    chunk_size = global_config.get("llm_chunk_size_words", 350)
    tasks = []
    for i, chapter_text in enumerate(chapters):
        chapter_num = i + 1
        chunks = _smart_chunk_text(chapter_text, chunk_size)
        for j, chunk in enumerate(chunks):
            scene_num = j + 1
            tasks.append({'chunk': chunk, 'chapter_num': chapter_num, 'scene_num': scene_num})
    if not tasks: print("No text chunks found to process."); return
    print(f"Found {len(chapters)} chapters. Text was divided into {len(tasks)} chunks of approx. {chunk_size} words each.")
    num_workers = global_config.get("llm_concurrent_requests", 4)
    print(f"Using {num_workers} parallel workers...")
    # We now need to pass the template to each worker
    tasks_with_config = [(task, global_config, prompt_template) for task in tasks]
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        results = list(tqdm(executor.map(_process_chunk, tasks_with_config, chunksize=1), total=len(tasks), desc="Generating Prompts"))
    all_prompts = [res for res in results if res is not None]
    if not all_prompts:
        print("\nNo prompts were successfully generated."); return
    all_prompts.sort(key=lambda x: (x['chapter'], x['scene']))
    df = pd.DataFrame(all_prompts)
    df.to_csv(output_csv_path, sep='|', index=False, header=True)
    print(f"\nSUCCESS: Saved {len(all_prompts)} prompts to '{output_csv_path}'")

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')