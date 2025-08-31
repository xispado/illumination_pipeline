# src/image_generator.py
import os
import json
import base64
import copy
import threading
import time
import pandas as pd
import requests

from src.config_manager import load_project_config

# KeyPressListener can be defined here as it's self-contained
try:
    import msvcrt
    class KeyPressListener:
        def __init__(self, interrupt_key='x'):
            self.interrupt_key = interrupt_key.lower(); self.key_pressed = None
            self._thread = threading.Thread(target=self._listen, daemon=True)
            self._stop_event = threading.Event()
        def _listen(self):
            while not self._stop_event.is_set():
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8').lower()
                    if key == self.interrupt_key: self.key_pressed = key; break
                time.sleep(0.1)
        def start(self): self._thread.start()
        def stop(self): self._stop_event.set()
        def is_interrupt_pressed(self): return self.key_pressed == self.interrupt_key
except ImportError:
    import sys, select, tty, termios
    class KeyPressListener:
        def __init__(self, interrupt_key='x'):
            self.interrupt_key = interrupt_key.lower(); self.key_pressed = None
            self._thread = threading.Thread(target=self._listen, daemon=True)
            self._stop_event = threading.Event()
        def _listen(self):
            old_settings = termios.tcgetattr(sys.stdin)
            try:
                tty.setcbreak(sys.stdin.fileno())
                while not self._stop_event.is_set():
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        key = sys.stdin.read(1).lower()
                        if key == self.interrupt_key: self.key_pressed = key; break
            finally: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        def start(self): self._thread.start()
        def stop(self): self._stop_event.set()
        def is_interrupt_pressed(self): return self.key_pressed == self.interrupt_key

def _create_filename_base_from_prompt(prompt_text):
    first_words = prompt_text.split()[:6]
    base = "_".join(first_words)
    return "".join(c for c in base if c.isalnum() or c == '_').lower()

def run_image_generation(project_path, single_image_details=None):
    """Runs the image generation process."""
    config = load_project_config(project_path)
    project_name = os.path.basename(project_path)
    csv_path = os.path.join(project_path, f"{project_name}_prompts.csv")
    images_folder = os.path.join(project_path, "images")
    os.makedirs(images_folder, exist_ok=True)

    if not single_image_details and not os.path.exists(csv_path):
        print(f"ERROR: Prompts file not found at '{csv_path}'.")
        return

    # The entire "Pre-flight Check" block has been removed.

    rows_to_process = []
    if single_image_details:
        chapter, prompt_text = single_image_details
        scene_num = 1
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
        listener.start()
        print("\n--- Starting Image Generation ---")
        print("Press 'X' at any time to gracefully stop after the current image.")
    
    try:
        for item in rows_to_process:
            if listener.is_interrupt_pressed(): print("\nUser interruption detected."); break
            
            output_path = os.path.join(images_folder, item['filename'])
            if not single_image_details and os.path.exists(output_path):
                print(f"Skipping {item['filename']}, already exists.")
                continue

            print(f"\nGenerating image for Chapter {item['chapter']}, Scene {item['scene']}: {item['filename']}")
            # The payload is now a simple deep copy. The override_settings for model and VAE
            # are included in every call, which is more reliable.
            payload = copy.deepcopy(config["api_payload"])
            payload["prompt"] = config.get("prompt_prefix", "") + item['prompt']
            
            try:
                response = requests.post(url=config['forge_api_url'], json=payload)
                response.raise_for_status()
                r = response.json()
                image_data = base64.b64decode(r['images'][0])
                with open(output_path, 'wb') as f: f.write(image_data)
                print(f"  -> Successfully saved {item['filename']}")
            except requests.RequestException as e:
                print(f"  -> ERROR sending payload to ForgeUI API. Is it running with --api flag?")
                print(f"  -> Details: {e}")
                if e.response: print(f"  -> Response: {e.response.text}")
                break 
    finally:
        listener.stop()

def run_upscaling_process(project_path):
    """Manages the batch upscaling of images."""
    print("\n--- Post-Process Upscaling ---")
    config = load_project_config(project_path)
    
    upscale_settings = config.get("postprocess_upscaling", {})
    if not upscale_settings.get("enabled", False):
        print("Upscaling is disabled in the project's 'config.json'.")
        return

    source_folder = os.path.join(project_path, "images")
    target_folder = os.path.join(project_path, "images_upscaled")
    os.makedirs(target_folder, exist_ok=True)
    
    images_to_process = [f for f in sorted(os.listdir(source_folder)) if f.lower().endswith('.png') and not os.path.exists(os.path.join(target_folder, f))]

    if not images_to_process:
        print("All images have already been upscaled.")
        return
        
    print(f"Found {len(images_to_process)} image(s) to upscale. Press 'X' to stop.")
    listener = KeyPressListener()
    listener.start()
    
    try:
        for i, filename in enumerate(images_to_process):
            if listener.is_interrupt_pressed(): print("\nUser interruption detected."); break
            
            print(f"\n[{i+1}/{len(images_to_process)}] Upscaling {filename}...")
            source_path = os.path.join(source_folder, filename)
            target_path = os.path.join(target_folder, filename)
            
            _upscale_single_image(source_path, target_path, config)
    finally:
        listener.stop()

def _upscale_single_image(source_path, target_path, config):
    """Sends a single image to the 'extras' API."""
    settings = config.get("postprocess_upscaling", {})
    url = config['forge_api_url'].replace('txt2img', 'extra-single-image')
    
    with open(source_path, 'rb') as img_file:
        encoded_image = base64.b64encode(img_file.read()).decode('utf-8')
    
    payload = {"image": encoded_image, "upscaling_resize": settings.get("scale_by", 2.0), "upscaler_1": settings.get("upscaler", "None")}
    
    try:
        response = requests.post(url=url, json=payload)
        response.raise_for_status()
        r = response.json()
        if 'image' in r:
            upscaled_data = base64.b64decode(r['image'])
            with open(target_path, 'wb') as f: f.write(upscaled_data)
            print(f"  -> Successfully saved upscaled image.")
        else:
            print(f"  -> ERROR: Upscale API response did not contain an image.")
    except requests.RequestException as e:
        print(f"  -> ERROR sending payload to Upscale API. Details: {e}")