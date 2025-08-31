# src/config_manager.py
import json
import os

GLOBAL_CONFIG_PATH = 'global_config.json'

def load_global_config():
    """Loads the global configuration file."""
    if not os.path.exists(GLOBAL_CONFIG_PATH):
        raise FileNotFoundError(f"CRITICAL: Global config file not found at '{GLOBAL_CONFIG_PATH}'")
    with open(GLOBAL_CONFIG_PATH, 'r') as f:
        return json.load(f)

def get_default_project_config():
    """Returns the default settings block from the global config."""
    global_config = load_global_config()
    return global_config.get("default_settings", {})

def load_project_config(project_path):
    """Loads a project-specific config file."""
    config_path = os.path.join(project_path, "config.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Project config not found in '{project_path}'")
    with open(config_path, 'r') as f:
        return json.load(f)