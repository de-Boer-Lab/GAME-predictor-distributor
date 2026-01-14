'''
Configuration script to read `distributor_config.yaml` file and identify all "worker" Predictors on their host_ip and host_port
'''
import os
import yaml
from pydantic import BaseModel, model_validator, Field
from typing import List, Optional

CONFIG_SCRIPT_DIR = os.path.dirname(__file__)

# DYNAMIC CONFIG PATH
# Determine if running inside a container or not
if os.path.exists('/.singularity.d'):
    DIST_CONFIG_FILE_PATH = "/distributor_config.yaml"
else:
    DIST_CONFIG_FILE_PATH = os.path.join("..", "distributor_config.yaml")

class WorkerConfig(BaseModel):
    id: str
    pred_ip: str
    pred_port: str
    # This field is populated during validation, not read from YAML
    base_url: Optional[str] = Field(default=None, exclude=True)

class ConfigurationSettings(BaseModel):
    distributor_name: str
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
for worker in configuration_settings.predictor_pool:
    print(f"ID: {worker.id}")
    print(f"URL: {worker.base_url}")
    print("---------------------------------")