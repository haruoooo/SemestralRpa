# Builds foraDoPicoRpa.zip for BotCity Maestro (Easy Deploy), as in the BotCity Python bot template.
# Only an explicit list of files goes in: never .env, logs, data or the virtual environment.
Set-Location $PSScriptRoot
$staging = Join-Path $env:TEMP "foraDoPicoRpaBuild"
Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $staging | Out-Null
Copy-Item bot.py, foraDoPicoRpa.botproj, requirements.txt -Destination $staging
Copy-Item src -Destination $staging -Recurse
Get-ChildItem -Path $staging -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath "foraDoPicoRpa.zip" -Force
Remove-Item -Recurse -Force $staging
Write-Output "Pacote gerado: foraDoPicoRpa.zip"
