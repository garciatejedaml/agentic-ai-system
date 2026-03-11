# Export Windows trusted root certificates to PEM format
# Run this script on the VDI before starting the Ollama container
#
# Usage (PowerShell as Administrator):
#   cd repo-local-dev
#   .\scripts\export-jp-certs.ps1

$outputDir = Join-Path $PSScriptRoot "..\certs"
$outputFile = Join-Path $outputDir "ca-certificates.crt"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$certs = Get-ChildItem -Path Cert:\LocalMachine\Root
$pem = ""
foreach ($cert in $certs) {
    $pem += "-----BEGIN CERTIFICATE-----`n"
    $pem += [System.Convert]::ToBase64String($cert.RawData, [System.Base64FormattingOptions]::InsertLineBreaks)
    $pem += "`n-----END CERTIFICATE-----`n"
}

$pem | Out-File -FilePath $outputFile -Encoding ASCII
Write-Host "Certificates exported to: $outputFile"
Write-Host "Total certificates: $($certs.Count)"
