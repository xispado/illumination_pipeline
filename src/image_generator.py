# src/image_generator.py
import os
import json
import base64
import copy
import threading
import time
import pandas as pd
import requests
import uuid
import websocket
import random
import shutil

from src.config_manager import load_project_config
from src.utils import Colors

# Helper function to clear the screen
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# ... (KeyPressListener class remains the same) ...
try:
    import msvcrt
    class KeyPressListener:
        def __init__(self, interrupt_key='x'): self.interrupt_key=interrupt_key.lower();self.key_pressed=None;self._thread=threading.Thread(target=self._listen,daemon=True);self._stop_event=threading.Event()
        def _listen(self):
            while not self._stop_event.is_set():
                if msvcrt.kbhit():
                    key=msvcrt.getch().decode('utf-8').lower()
                    if key==self.interrupt_key:self.key_pressed=key;break
                time.sleep(0.1)
        def start(self):self._thread.start()
        def stop(self):self._stop_event.set()
        def is_interrupt_pressed(self):return self.key_pressed==self.interrupt_key
except ImportError:
    import sys,select,tty,termios
    class KeyPressListener:
        def __init__(self,interrupt_key='x'):self.interrupt_key=interrupt_key.lower();self.key_pressed=None;self._thread=threading.Thread(target=self._listen,daemon=True);self._stop_event=threading.Event()
        def _listen(self):
            old_settings=termios.tcgetattr(sys.stdin)
            try:
                tty.setcbreak(sys.stdin.fileno())
                while not self._stop_event.is_set():
                    if select.select([sys.stdin],[],[],0.1)[0]:
                        key=sys.stdin.read(1).lower()
                        if key==self.interrupt_key:self.key_pressed=key;break
            finally:termios.tcsetattr(sys.stdin,termios.TCSADRAIN,old_settings)
        def start(self):self._thread.start()
        def stop(self):self._stop_event.set()
        def is_interrupt_pressed(self):return self.key_pressed==self.interrupt_key

def _create_filename_base_from_prompt(prompt_text):
    first_words = prompt_text.split()[:6]
    base = "_".join(first_words)
    return "".join(c for c in base if c.isalnum() or c == '_').lower()

# =============================================================================
# --- MAIN ROUTER FUNCTIONS ---
# =============================================================================
def run_image_generation(project_path, single_image_details=None):
    """Router for image generation. Calls the correct function based on config."""
    config = load_project_config(project_path)
    generator_type = config.get("image_generator_type", "forge").lower()
    if generator_type == "comfyui":
        print("--- Using ComfyUI Image Generator ---")
        run_comfyui_image_generation(project_path, config, single_image_details)
    else:
        print("--- Using Forge/A1111 Image Generator ---")
        run_forge_image_generation(project_path, config, single_image_details)

def run_upscaling_process(project_path):
    """Router for upscaling. Calls the correct function based on config."""
    clear_screen()
    print("--- Post-Process Upscaling ---")
    config = load_project_config(project_path)
    generator_type = config.get("image_generator_type", "forge").lower()
    
    if generator_type == "comfyui":
        run_comfyui_upscaling(project_path, config)
    else:
        run_forge_upscaling(project_path, config)

# =============================================================================
# --- COMFYUI IMPLEMENTATION ---
# =============================================================================
def _queue_comfy_prompt(prompt_workflow, config, return_filename=False):
    """Sends workflow to ComfyUI and returns image data OR filename."""
    server_address = config.get("comfyui_api_address", "127.0.0.1:8188"); client_id = str(uuid.uuid4())
    try:
        p = {"prompt": prompt_workflow, "client_id": client_id}; data = json.dumps(p).encode('utf-8')
        req = requests.post(f"http://{server_address}/prompt", data=data); req.raise_for_status()
        prompt_id = req.json()['prompt_id']
        ws = websocket.WebSocket(); ws.connect(f"ws://{server_address}/ws?clientId={client_id}")
        
        output = None
        while True:
            out = ws.recv()
            if not isinstance(out, str): continue
            message = json.loads(out)
            if message['type'] == 'executed':
                data = message['data']
                if 'images' in data['output'] and data['prompt_id'] == prompt_id:
                    image_info = data['output']['images'][0]
                    # The filename from the message is now our source of truth
                    output_filename = image_info['filename']
                    
                    if return_filename:
                        output = output_filename # Return the filename for moving
                    else:
                        # Fetch the image data using the reliable filename
                        resp = requests.get(f"http://{server_address}/view?filename={output_filename}&subfolder={image_info['subfolder']}&type={image_info['type']}")
                        resp.raise_for_status(); output = resp.content # Return the image data
                    break
            if message['type'] == 'executing' and message['data']['node'] is None and message['data']['prompt_id'] == prompt_id:
                if output is None: print(f"{Colors.YELLOW}  -> WARNING: Workflow finished but no image output was detected.{Colors.ENDC}")
                break
        ws.close(); return output
    except Exception as e:
        print(f"  -> {Colors.RED}ERROR: An error occurred during ComfyUI communication: {e}{Colors.ENDC}"); return None

def run_comfyui_image_generation(project_path, config, single_image_details=None):
    """Runs the image generation process using ComfyUI with optional overrides."""
    project_name = os.path.basename(project_path)
    csv_path = os.path.join(project_path, f"{project_name}_prompts.csv")
    images_folder = os.path.join(project_path, "images")
    os.makedirs(images_folder, exist_ok=True)

    try:
        with open(config['comfyui_workflow_file'], 'r') as f: base_workflow = json.load(f)
    except Exception as e:
        print(f"ERROR: Could not load ComfyUI workflow. {e}"); return

    overrides = config.get("comfyui_overrides", {})
    if overrides.get("enabled", False):
        print("  -> Applying ComfyUI overrides from config file.")
        for node in base_workflow.values():
            if node["class_type"] in ["CheckpointLoader", "CheckpointLoaderSimple"] and "ckpt_name" in overrides: node["inputs"]["ckpt_name"] = overrides["ckpt_name"]
            elif node["class_type"] == "EmptyLatentImage" and "width" in overrides:
                node["inputs"]["width"] = overrides["width"]
                node["inputs"]["height"] = overrides["height"]
            elif node["class_type"] == "KSampler" and "steps" in overrides:
                node["inputs"]["steps"] = overrides["steps"]
                node["inputs"]["cfg"] = overrides["cfg"]
                node["inputs"]["sampler_name"] = overrides["sampler_name"]
                node["inputs"]["scheduler"] = overrides["scheduler"]

    rows_to_process = []
    if single_image_details:
        chapter, prompt_text = single_image_details; scene_num = 1
        for f in sorted(os.listdir(images_folder)):
            if f.startswith(f"{int(chapter):02d}-"):
                try: scene_num = int(f[3:5]) + 1
                except (ValueError, IndexError): continue
        filename_base = _create_filename_base_from_prompt(prompt_text)
        filename_prefix = f"{str(chapter).zfill(2)}-{str(scene_num).zfill(2)}_{filename_base}"
        rows_to_process.append({'chapter': chapter, 'scene': scene_num, 'prompt': prompt_text, 'filename_prefix': filename_prefix})
    else:
        df = pd.read_csv(csv_path, sep='|')
        for _, row in df.iterrows():
            filename_base = _create_filename_base_from_prompt(row['prompt'])
            filename_prefix = f"{str(row['chapter']).zfill(2)}-{str(row['scene']).zfill(2)}_{filename_base}"
            rows_to_process.append({'chapter': row['chapter'], 'scene': row['scene'], 'prompt': row['prompt'], 'filename_prefix': filename_prefix})

    listener = KeyPressListener()
    if not single_image_details: listener.start(); print(f"{Colors.YELLOW}Press 'X' at any time to gracefully stop.{Colors.ENDC}")
    try:
        for item in rows_to_process:
            if listener.is_interrupt_pressed(): print("\nUser interruption detected. Halting generation."); break
            output_path = os.path.join(images_folder, f"{item['filename_prefix']}.png")
            if not single_image_details and os.path.exists(output_path):
                print(f"Skipping {os.path.basename(output_path)}, already exists."); continue
            
            print(f"\nGenerating image: {os.path.basename(output_path)}")
            prompt_workflow = copy.deepcopy(base_workflow)
            
            # --- MODIFIED LOGIC HERE ---
            for node in prompt_workflow.values():
                # Always set a random seed
                if node["class_type"] == "KSampler": 
                    node["inputs"]["seed"] = random.randint(0, 2**32 - 1)
                
                # Always set the filename prefix
                if node["class_type"] == "SaveImage":
                    node["inputs"]["filename_prefix"] = item['filename_prefix']
                
                # Replace prompt placeholders
                for key, value in node["inputs"].items():
                    if str(value) == "<prompt>": 
                        node["inputs"][key] = config.get("prompt_prefix", "") + item['prompt']
                    if str(value) == "<negprompt>": 
                        node["inputs"][key] = config.get('api_payload', {}).get('negative_prompt', '')
            
            image_data = _queue_comfy_prompt(prompt_workflow, config)
            if image_data:
                with open(output_path, 'wb') as f: f.write(image_data)
                print(f"  -> Successfully saved {os.path.basename(output_path)}")
            else:
                print(f"{Colors.RED}  -> Failed to retrieve image from ComfyUI. Halting generation.{Colors.ENDC}"); break
    finally:
        listener.stop()

def run_comfyui_upscaling(project_path, config):
    """Manages the batch upscaling of images using ComfyUI."""
    server_address = config.get("comfyui_api_address", "127.0.0.1:8188")
    comfyui_path = config.get("comfyui_path")
    if not comfyui_path or not os.path.isdir(comfyui_path):
        print(f"{Colors.RED}ERROR: 'comfyui_path' is not set or is invalid in your config.json.{Colors.ENDC}")
        print("Please set it to the root of your ComfyUI installation folder."); return
    
    source_folder = os.path.join(project_path, "images")
    target_folder = os.path.join(project_path, "images_upscaled")
    os.makedirs(target_folder, exist_ok=True)

    try:
        with open(config['comfyui_upscale_workflow_file'], 'r') as f: base_workflow = json.load(f)
    except Exception as e:
        print(f"ERROR: Could not load ComfyUI upscale workflow file. {e}"); return
    
    images_to_process = [f for f in sorted(os.listdir(source_folder)) if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not os.path.exists(os.path.join(target_folder, f))]
    if not images_to_process:
        print("All images have already been upscaled."); return

    print(f"Found {len(images_to_process)} image(s) to upscale. {Colors.YELLOW}Press 'X' to stop.{Colors.ENDC}")
    listener = KeyPressListener(); listener.start()
    try:
        for i, filename in enumerate(images_to_process):
            if listener.is_interrupt_pressed(): print("\nUser interruption detected."); break
            print(f"\n[{i+1}/{len(images_to_process)}] Upscaling {filename}...")
            
            source_path = os.path.join(source_folder, filename)
            
            with open(source_path, 'rb') as f: image_data = f.read()
            files = {'image': (filename, image_data, 'image/png'), 'overwrite': (None, 'true')}
            resp = requests.post(f"http://{server_address}/upload/image", files=files)
            if resp.status_code != 200:
                print(f"  -> {Colors.RED}ERROR: Failed to upload image to ComfyUI.{Colors.ENDC}"); continue
            
            uploaded_filename = resp.json()['name']

            workflow = copy.deepcopy(base_workflow)
            for node in workflow.values():
                if node['class_type'] == 'LoadImage':
                    node['inputs']['image'] = uploaded_filename
                if node['class_type'] == 'UpscaleModelLoader':
                    node['inputs']['model_name'] = config.get('postprocess_upscaling', {}).get('upscaler', 'R-ESRGAN 4x+.pth')
                if node['class_type'] == 'SaveImage':
                    node['inputs']['filename_prefix'] = f"{os.path.splitext(filename)[0]}_upscaled"
            
            output_filename = _queue_comfy_prompt(workflow, config, return_filename=True)

            if output_filename:
                comfy_output_path = os.path.join(comfyui_path, "output", output_filename)
                target_path = os.path.join(target_folder, filename)
                try:
                    shutil.move(comfy_output_path, target_path)
                    print(f"  -> Successfully upscaled and moved to {os.path.basename(target_folder)}")
                except Exception as move_e:
                    print(f"  -> {Colors.RED}ERROR: Could not move file from ComfyUI output. {move_e}{Colors.ENDC}")
            else:
                print(f"  -> {Colors.RED}ERROR: Upscaling failed in ComfyUI.{Colors.ENDC}")
    finally:
        listener.stop()

# =============================================================================
# --- FORGE/A1111 IMPLEMENTATION ---
# =============================================================================
def run_forge_image_generation(project_path, config, single_image_details=None):
    """Runs the image generation process using Forge/A1111 API."""
    project_name = os.path.basename(project_path)
    csv_path = os.path.join(project_path, f"{project_name}_prompts.csv")
    images_folder = os.path.join(project_path, "images")
    os.makedirs(images_folder, exist_ok=True)
    if not single_image_details and not os.path.exists(csv_path):
        print(f"ERROR: Prompts file not found at '{csv_path}'."); return
    rows_to_process = []
    if single_image_details:
        chapter, prompt_text = single_image_details; scene_num = 1
        for f in sorted(os.listdir(images_folder)):
            if f.startswith(f"{int(chapter):02d}-"):
                try: scene_num = int(f[3:5]) + 1
                except (ValueError, IndexError): continue
        filename_base = _create_filename_base_from_prompt(prompt_text)
        filename = f"{int(chapter):02d}-{scene_num:02d}_{filename_base}.png"
        rows_to_process.append({'chapter': chapter, 'scene': scene_num, 'prompt': prompt_text, 'filename': filename})
    else:
        df = pd.read_csv(csv_path, sep='|')
        for _, row in df.iterrows():
            filename_base = _create_filename_base_from_prompt(row['prompt'])
            filename = f"{str(row['chapter']).zfill(2)}-{str(row['scene']).zfill(2)}_{filename_base}.png"
            rows_to_process.append({'chapter': row['chapter'], 'scene': row['scene'], 'prompt': row['prompt'], 'filename': filename})
    listener = KeyPressListener()
    if not single_image_details:
        listener.start(); print(f"{Colors.YELLOW}Press 'X' at any time to gracefully stop.{Colors.ENDC}")
    try:
        for item in rows_to_process:
            if listener.is_interrupt_pressed(): print("\nUser interruption detected."); break
            output_path = os.path.join(images_folder, item['filename'])
            if not single_image_details and os.path.exists(output_path):
                print(f"Skipping {item['filename']}, already exists."); continue
            print(f"\nGenerating image for Chapter {item['chapter']}, Scene {item['scene']}: {item['filename']}")
            payload = copy.deepcopy(config["api_payload"])
            payload["prompt"] = config.get("prompt_prefix", "") + item['prompt']
            try:
                response = requests.post(url=config['forge_api_url'], json=payload)
                response.raise_for_status()
                r = response.json(); image_data = base64.b64decode(r['images'][0])
                with open(output_path, 'wb') as f: f.write(image_data)
                print(f"  -> Successfully saved {item['filename']}")
            except requests.RequestException as e:
                print(f"  -> ERROR sending payload to API. Is it running with --api flag?")
                if e.response: print(f"  -> Response: {e.response.text}")
                break 
    finally:
        listener.stop()

def run_forge_upscaling(project_path, config):
    """Manages batch upscaling for Forge."""
    source_folder = os.path.join(project_path, "images")
    target_folder = os.path.join(project_path, "images_upscaled")
    os.makedirs(target_folder, exist_ok=True)
    if not os.path.exists(source_folder) or not os.listdir(source_folder):
        print(f"\n{Colors.YELLOW}No images found in 'images' folder to upscale.{Colors.ENDC}"); return
    images_to_process = [f for f in sorted(os.listdir(source_folder)) if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not os.path.exists(os.path.join(target_folder, f))]
    if not images_to_process:
        print("All images have already been upscaled."); return
    print(f"Found {len(images_to_process)} image(s) to upscale. {Colors.YELLOW}Press 'X' to stop.{Colors.ENDC}")
    listener = KeyPressListener(); listener.start()
    try:
        for i, filename in enumerate(images_to_process):
            if listener.is_interrupt_pressed(): print("\nUser interruption detected."); break
            print(f"\n[{i+1}/{len(images_to_process)}] Upscaling {filename}...")
            source_path = os.path.join(source_folder, filename)
            target_path = os.path.join(target_folder, filename)
            _upscale_single_image_forge(source_path, target_path, config)
    finally:
        listener.stop()

def _upscale_single_image_forge(source_path, target_path, config):
    """Sends a single image to the 'extras' API for Forge."""
    settings = config.get("postprocess_upscaling", {})
    url = config['forge_api_url'].replace('txt2img', 'extra-single-image')
    
    # Get the upscaler name from config, which might have an extension
    upscaler_name_with_ext = settings.get("upscaler", "None")
    
    # Strip the file extension for the Forge API call
    upscaler_name_for_api, _ = os.path.splitext(upscaler_name_with_ext)
    
    with open(source_path, 'rb') as f: encoded_image = base64.b64encode(f.read()).decode('utf-8')
    
    # Use the cleaned name in the payload
    payload = {
        "image": encoded_image,
        "upscaling_resize": settings.get("scale_by", 2.0),
        "upscaler_1": upscaler_name_for_api 
    }
    
    try:
        response = requests.post(url=url, json=payload); response.raise_for_status(); r = response.json()
        if 'image' in r:
            with open(target_path, 'wb') as f: f.write(base64.b64decode(r['image']))
            print(f"  -> Successfully saved upscaled image.")
        else:
            print(f"  -> ERROR: Upscale API response did not contain an image.")
    except requests.RequestException as e:
        print(f"  -> ERROR sending payload to Upscale API. Details: {e}")

def cleanup_comfyui_output_for_project(project_path, config):
    """Safely finds and deletes generated images from the ComfyUI output folder that match this project."""
    print("--- ComfyUI Output Cleanup ---")
    
    comfyui_path = config.get("comfyui_path")
    if not comfyui_path or not os.path.isdir(comfyui_path):
        print(f"{Colors.RED}ERROR: 'comfyui_path' is not set or is invalid in your config.json.{Colors.ENDC}")
        return

    comfy_output_dir = os.path.join(comfyui_path, "output")
    if not os.path.isdir(com_fy_output_dir):
        print(f"{Colors.RED}ERROR: Could not find ComfyUI output directory at '{comfy_output_dir}'{Colors.ENDC}")
        return

    # 1. Get a set of all base filenames from our project
    project_basenames = set()
    images_dir = os.path.join(project_path, "images")
    upscaled_dir = os.path.join(project_path, "images_upscaled")

    if os.path.exists(images_dir):
        for f in os.listdir(images_dir):
            project_basenames.add(os.path.splitext(f)[0])
    if os.path.exists(upscaled_dir):
        for f in os.listdir(upscaled_dir):
            # Upscaled files in Comfy have a suffix, so we match the original name
            base_name = os.path.splitext(f)[0]
            if base_name.endswith("_upscaled"):
                 project_basenames.add(base_name.replace("_upscaled", ""))
            else:
                 project_basenames.add(base_name)

    if not project_basenames:
        print("No images found in the project to match against. Cleanup aborted.")
        return

    # 2. Find all matching files in the ComfyUI output directory
    files_to_delete = []
    for comfy_file in os.listdir(comfy_output_dir):
        comfy_basename = os.path.splitext(comfy_file)[0]
        # Check if the Comfy filename STARTS WITH any of our project's base filenames
        for proj_basename in project_basenames:
            if comfy_basename.startswith(proj_basename):
                files_to_delete.append(os.path.join(comfy_output_dir, comfy_file))
                break # Move to the next file once a match is found

    if not files_to_delete:
        print("No matching project files found in the ComfyUI output folder. Nothing to clean up.")
        return

    # 3. CRITICAL: Ask the user for confirmation
    print(f"\nFound {Colors.YELLOW}{len(files_to_delete)}{Colors.ENDC} files in the ComfyUI output folder matching this project:")
    for f in files_to_delete[:5]: # Show a preview of the first 5 files
        print(f"  - {os.path.basename(f)}")
    if len(files_to_delete) > 5:
        print(f"  - ... and {len(files_to_delete) - 5} more.")

    confirm = input("\nAre you sure you want to PERMANENTLY delete these files? (y/n): ").lower()

    # 4. Delete the files if confirmed
    if confirm == 'y':
        deleted_count = 0
        for f_path in files_to_delete:
            try:
                os.remove(f_path)
                deleted_count += 1
            except OSError as e:
                print(f"  -> {Colors.RED}ERROR: Could not delete {os.path.basename(f_path)}. Reason: {e}{Colors.ENDC}")
        print(f"\nSuccessfully deleted {deleted_count} files.")
    else:
        print("\nCleanup cancelled.")