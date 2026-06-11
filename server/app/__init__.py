from pathlib import Path

from dotenv import load_dotenv

# Load server/.env so configuration is available to both the API and the CLI
# scripts without exporting variables in the shell. override=False keeps any
# variables already set in the environment (e.g. by generate_all_manifests.ps1)
# taking precedence over the file.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
