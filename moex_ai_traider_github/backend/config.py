import json
from pathlib import Path
from models import SettingsModel

CONFIG_FILE = Path(__file__).parent / "settings.json"

class ConfigManager:
    def __init__(self):
        self.settings = self.load_settings()

    def load_settings(self) -> SettingsModel:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    return SettingsModel(**data)
            except Exception:
                return SettingsModel()
        return SettingsModel()

    def save_settings(self, settings: SettingsModel):
        self.settings = settings
        with open(CONFIG_FILE, "w") as f:
            f.write(settings.model_dump_json(indent=2))

config_manager = ConfigManager()
