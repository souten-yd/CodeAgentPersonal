Write-Output "[Docker] Attempting Docker Desktop installation helper..."
Write-Output "[Docker][WARN] Admin rights/WSL2/reboot/license acceptance may be required."
if (Get-Command winget -ErrorAction SilentlyContinue) {
  winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
  exit $LASTEXITCODE
}
Write-Output "[Docker][WARN] winget not available. Install Docker Desktop manually: https://www.docker.com/products/docker-desktop/"
exit 1
