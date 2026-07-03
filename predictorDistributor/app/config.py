'''
Configuration for PredictorDistributor

- Determines if running inside a container or not.
- Automatically versions the Distributor name using Apptainer's build-date label.
    - Inside container:             "PredictorDistributor_20251128-180629_PST" (sortable, human-readable)
    - Outside container (Dev mode): "PredictorDistributor_dev"
- Reads `distributor_config.yaml` to identify all "worker" Predictors on their host_ip and host_port.
'''

import os
import json
import yaml
from datetime import datetime
from pydantic import BaseModel, model_validator, Field
from typing import List, Optional

CONFIG_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

MODULE_NAME = "PredictorDistributor"
GAME_SCHEMA_VERSION = "1.0"

# DYNAMIC CONFIG PATH
# Determine if running inside a container or not
if os.path.exists('/.singularity.d'):
    print("Running inside the container...")
    try:
        with open('/.singularity.d/labels.json', 'r') as f:
            labels = json.load(f)
        raw_build_date = labels.get('org.label-schema.build-date', '')
        parts = raw_build_date.split('_')
        date_str = f"{parts[1]}_{parts[2]}_{parts[3]}_{parts[4]}"
        dt = datetime.strptime(date_str, "%d_%B_%Y_%H:%M:%S")
        build_timestamp = dt.strftime("%Y%m%d-%H%M%S")
        timezone_label = parts[5] if len(parts) > 5 else "UNK"
        DISTRIBUTOR_NAME = f"{MODULE_NAME}_{build_timestamp}_{timezone_label}"
    except Exception as e:
        print(f"Warning: Could not parse build timestamp from labels.json: {e}")
        DISTRIBUTOR_NAME = f"{MODULE_NAME}_unknown"
    # --- Worker pool configuration from YAML ---
    DIST_CONFIG_FILE_PATH = "/distributor_config.yaml"
else:
    print("Running outside the container (dev mode)...")
    DISTRIBUTOR_NAME = f"{MODULE_NAME}_dev"
    # --- Worker pool configuration from YAML ---
    DIST_CONFIG_FILE_PATH = os.path.join("..", "distributor_config.yaml")

class WorkerConfig(BaseModel):
    id: str
    pred_ip: str
    pred_port: str
    # This field is populated during validation, not read from YAML
    base_url: Optional[str] = Field(default=None, exclude=True)

class ConfigurationSettings(BaseModel):
    base_url_template: str
    predictor_pool: List[WorkerConfig]
    
    # This validator runs after the model is first populated
    @model_validator(mode='after')
    def format_worker_urls(self) -> 'ConfigurationSettings':
        """
        Uses the base_url_template to build the final base_url for each worker.
        """
        try:
            for worker in self.predictor_pool:
            # Create a dictionary of the values to substitute
                substitutions = {
                    "pred_ip": worker.pred_ip,
                    "pred_port": worker.pred_port 
                }
                
                # Use .format() to replace the placeholders
                # We only need the base_url now. Predictor instances run the command through qsub
                worker.base_url = self.base_url_template.format(**substitutions)
        except KeyError as e:
            # This catches typos in the YAML, e.g. if you wrote {port} instead of {pred_port}
            raise ValueError(f"Config error in worker Invalid placeholder {e} in base_url_template")
            
        return self
    
def load_config(path: str = DIST_CONFIG_FILE_PATH) -> ConfigurationSettings:
    """Loads the YAML configuration file"""
    try:
        with open(path, 'r') as f:
            config_data = yaml.safe_load(f)
        return ConfigurationSettings(**config_data)
    except FileNotFoundError:
        print(f"FATAL: Configuration file not found at {path}")
        if os.path.exists('/.singularity.d'):
            print("Ensure that the distributor_config file is mounted with: -B /absolute/path/to/distributor_config.yaml:/distributor_config.yaml")
        raise
    except Exception as e:
        print(f"FATAL: Error parsing configuration: {e}")
        raise

# Load settings once on startup
configuration_settings = load_config()

print("--- Config loaded successfully ---")
print(f"Distributor: {DISTRIBUTOR_NAME}")
print(f"Schema version: {GAME_SCHEMA_VERSION}")
print("Predictor Pool:")
for worker in configuration_settings.predictor_pool:
    print(f"  ID: {worker.id}")
    print(f"  URL: {worker.base_url}")
print("---------------------------------")
