#!/usr/bin/env bash
# Build step for deploy (Render runs this). Installs deps, collects static
# assets, applies migrations, and seeds the synthetic demo data + analytics.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py seed_demo
