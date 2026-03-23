# deploy.ps1 — Validador Tributario NF-e/NFS-e
# Usage: .\deploy.ps1 -ApiKey "sk-ant-..."
# Requires: AWS CLI configured + SAM CLI installed

param(
    [Parameter(Mandatory=$true)]
    [string]$ApiKey,

    [string]$StackName = "tributario",
    [string]$Region    = "us-east-1",
    [string]$S3Bucket  = ""   # SAM deploy staging bucket — created automatically if empty
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "`n=== Validador Tributario — Deploy ===" -ForegroundColor Cyan

# 1. SAM Build
Write-Host "`n[1/4] SAM Build..." -ForegroundColor Yellow
Set-Location $ScriptDir
sam build --template template.yaml

# 2. SAM Deploy
Write-Host "`n[2/4] SAM Deploy..." -ForegroundColor Yellow
$deployArgs = @(
    "deploy",
    "--stack-name", $StackName,
    "--region", $Region,
    "--capabilities", "CAPABILITY_IAM",
    "--parameter-overrides", "AnthropicApiKey=$ApiKey",
    "--resolve-s3"
)
sam @deployArgs

# 3. Get outputs
Write-Host "`n[3/4] Retrieving stack outputs..." -ForegroundColor Yellow
$outputs = aws cloudformation describe-stacks `
    --stack-name $StackName `
    --region $Region `
    --query "Stacks[0].Outputs" `
    --output json | ConvertFrom-Json

$apiEndpoint  = ($outputs | Where-Object { $_.OutputKey -eq "ApiEndpoint"       }).OutputValue
$bucketName   = ($outputs | Where-Object { $_.OutputKey -eq "FrontendBucketName"}).OutputValue
$cloudFrontUrl= ($outputs | Where-Object { $_.OutputKey -eq "CloudFrontUrl"     }).OutputValue

Write-Host "  API Endpoint  : $apiEndpoint"   -ForegroundColor Green
Write-Host "  S3 Bucket     : $bucketName"     -ForegroundColor Green
Write-Host "  CloudFront URL: $cloudFrontUrl"  -ForegroundColor Green

# 4. Inject API endpoint into frontend and upload to S3
Write-Host "`n[4/4] Uploading frontend to S3..." -ForegroundColor Yellow
$htmlPath  = Join-Path $ScriptDir "frontend\index.html"
$htmlContent = Get-Content $htmlPath -Raw
$htmlPatched = $htmlContent -replace "REPLACE_API_ENDPOINT", $apiEndpoint

$tmpFile = [System.IO.Path]::GetTempFileName() + ".html"
Set-Content -Path $tmpFile -Value $htmlPatched -Encoding UTF8
aws s3 cp $tmpFile "s3://$bucketName/index.html" --content-type "text/html" --region $Region
Remove-Item $tmpFile

Write-Host "`n=== Deploy concluido! ===" -ForegroundColor Cyan
Write-Host "Acesse: $cloudFrontUrl" -ForegroundColor Green
Write-Host "(Pode levar alguns minutos para o CloudFront propagar)`n"
