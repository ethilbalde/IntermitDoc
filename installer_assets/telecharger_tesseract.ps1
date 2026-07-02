# Télécharge l'installeur officiel Tesseract OCR (UB Mannheim) pour l'embarquer
# dans installer.iss. À exécuter une fois avant de compiler l'installeur si le
# fichier n'est pas déjà présent (le binaire n'est pas versionné dans git — trop lourd).
$ErrorActionPreference = "Stop"
$url = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.4.0.20240606.exe"
$out = Join-Path $PSScriptRoot "tesseract-ocr-w64-setup.exe"

if (Test-Path $out) {
    Write-Host "Déjà présent : $out"
    exit 0
}

Write-Host "Téléchargement de Tesseract OCR depuis $url ..."
Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing `
    -UserAgent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
Write-Host "OK : $out"
