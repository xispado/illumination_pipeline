# src/config_manager.py
import json; import os; from src.utils import Colors
GLOBAL_CONFIG_PATH = 'global_config.json'

def load_global_config():
    if not os.path.exists(GLOBAL_CONFIG_PATH):
        raise FileNotFoundError(f"CRITICAL: Global config file not found at '{GLOBAL_CONFIG_PATH}'")
    with open(GLOBAL_CONFIG_PATH, 'r') as f:
        return json.load(f)

def get_default_project_config():
    global_config = load_global_config()
    return global_config.get("default_project_settings", {})

def load_project_config(project_path):
    config_path = os.path.join(project_path, "config.json")
    if not os.path.exists(config_path):
        print(f"\n{Colors.YELLOW}WARNING: Project 'config.json' not found.{Colors.ENDC}")
        try:
            default_config = get_default_project_config()
            with open(config_path, 'w') as f: json.dump(default_config, f, indent=4)
            print(f"  -> A new 'config.json' has been created with global defaults.")
            return default_config
        except Exception as e:
            print(f"  -> {Colors.RED}ERROR: Could not create default config: {e}{Colors.ENDC}")
            return {}
    with open(config_path, 'r') as f:
        return json.load(f)