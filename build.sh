#!/bin/bash
# Builds foraDoPicoRpa.zip for BotCity Maestro (Easy Deploy), as in the BotCity Python bot template.
# Only an explicit list of files goes in: never .env, logs, data or the virtual environment.
cd "$(dirname "$0")"
rm -f foraDoPicoRpa.zip
zip -r -q foraDoPicoRpa.zip bot.py foraDoPicoRpa.botproj requirements.txt src -x "*/__pycache__/*" "*.pyc"
echo "Pacote gerado: foraDoPicoRpa.zip"
