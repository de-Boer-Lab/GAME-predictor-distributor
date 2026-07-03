# GAME Predictor Distributor

The creation of massive genomics datasets will continue to increase rapidly and thus to further future proof GAME's utility we designed Predictor Distributor (PD). PD is an optional module that acts as a transparent orchestration layer implementing a scatter-gather design.

> **Important Note: Supported MIME Types**
> The current version of PD only supports handling of **JSON** (`application/json`) and **MsgPack** (`application/msgpack`) MIME-types.

## 📦 Installation

To install PD:

```bash
wget -O predictorDistributor.sif "https://huggingface.co/datasets/deBoerLab/PredictorDistributor_GAME/resolve/main/predictorDistributor.sif?download=true"
```

👉 **[View Latest Release & Usage Instructions](../../releases/latest)**

## ⚙️ Configuration

PD reads a `distributor_config.yaml` file at startup to discover its pool of worker Predictors. This file **must be mounted into the container at runtime** -- PD will fail to start without it.

Create a `distributor_config.yaml` listing each worker Predictor's IP and port:

```yaml
base_url_template: "http://{pred_ip}:{pred_port}"
predictor_pool:
  - id: "worker_1"
    pred_ip: "host_ip1"    # Replace with your worker/Predictor IP
    pred_port: "8000"
  - id: "worker_2"
    pred_ip: "host_ip2"    # Replace with your worker/Predictor IP
    pred_port: "8001"
# Add more workers as necessary
```

Each entry corresponds to one running Predictor instance. Add as many workers as you have Predictor nodes available.

## 🚀 Quick Start

Mount your config file into the container at `/distributor_config.yaml` using the `-B` (bind) flag, and pass the IP and port the Distributor itself should listen on:

```bash
apptainer run --containall \
  -B /absolute/path/to/distributor_config.yaml:/distributor_config.yaml \
  predictorDistributor.sif HOST_IP HOST_PORT
```

- `HOST_IP` / `HOST_PORT`: the address the Distributor API listens on (this is what your Evaluator points at)
- The `-B` mount is **required** -- PD reads the config at startup and will exit immediately if it isn't present at `/distributor_config.yaml`
- `--containall` ensures a clean, isolated environment
- PD is **CPU-only** -- no `--nv` / GPU needed (the workers do the GPU inference)

Once running, PD impersonates a single Predictor to your Evaluator while transparently scattering requests across all configured workers.

## 🖥️ Automated HPC Deployment (Recommended)

Manually writing `distributor_config.yaml` and launching each worker, the Distributor, and the Evaluator by hand is tedious and error-prone -- especially getting every worker's IP and port right. For HPC users, the main GAME repository provides **Slurm job submission scripts** that automate this end to end. They:

- launch the full pipeline (Matcher &rarr; workers &rarr; Distributor &rarr; Evaluator) in the correct order using job dependencies,
- health-check each worker before adding it to the pool, then build the `distributor_config.yaml` automatically from the allocated nodes, and
- coordinate readiness signaling so the Evaluator only starts once the Predictors are actually serving.

They also support alternate topologies, including a direct single-Predictor mode (no PD, no Matcher) and a pool-without-Matcher mode for Predictors that may not need it.

📜 **[GAME Job Submission Scripts](https://github.com/de-Boer-Lab/Genomic-API-for-Model-Evaluation/tree/main/src/job-submission-scripts)** and more details about **[submitting jobs using GAME](https://genomic-api-for-model-evaluation-documentation.readthedocs.io/en/latest/Submitting_jobs.html)** 

This is the recommended path for running PD at scale on a cluster. The manual steps above are useful for local testing, debugging, or understanding what the scripts automate under the hood.

> **Note:** The job scripts are templates. Before submitting, edit the `<PATH_TO_...>` placeholders and add your cluster's scheduler directives (e.g. `#SBATCH` keys for partitions, GPU allocation, and output files) to suit your environment.

## 🔗 Links

- [PD Container Image](https://huggingface.co/datasets/deBoerLab/PredictorDistributor_GAME): Hosted on Hugging Face
- [Predictor Distributor Documentation](https://genomic-api-for-model-evaluation-documentation.readthedocs.io/en/latest/Predictor_distributor.html): Architecture and design details
- [Main GAME Repo](https://github.com/de-Boer-Lab/Genomic-API-for-Model-Evaluation?tab=readme-ov-file): For more details about the GAME framework
- [GAME Modules Repo](https://github.com/de-Boer-Lab/GAME_modules): Community-contributed list of GAME modules
- [GAME Documentation](https://genomic-api-for-model-evaluation-documentation.readthedocs.io): Consolidated ReadTheDocs documentation