# jwd

A self-contained static site for sharing cycling, hiking, and running routes.

## How

1. Drop GPX files into `trails/`
2. The build script extracts all metadata from GPX files: distance, elevation gain/loss, estimated time, coordinates, and elevation profiles
3. GitHub Actions builds the site and deploys to pages

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 build.py
```
