# AnythingLLM API Docker Compose Management Script for Windows PowerShell
# This script manages Docker Compose deployments for the AnythingLLM API

[CmdletBinding()]
param(
    [ValidateSet("up", "down", "restart", "logs", "status", "build", "pull")]
    [string]$Action = "up",
    [ValidateSet("development", "staging", "production")]
    [string]$Environment = "production",
    [string]$ComposeFile = "",
    [switch]$Detached = $true,
    [switch]$Build = $false,
    [switch]$Pull = $false,
    [switch]$RemoveOrphans = $false,
    [string]$Service = "",
    [int]$Follow = 100,
    [switch]$Help = $false
)

# Set strict mode and error action
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Colors for output
$Colors = @{
    Red = "Red"
    Green = "Green"
    Yellow = "Yellow"
    Blue = "Blue"
    White = "White"
}

# Logging functions
function Write-LogInfo {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor $Colors.Blue
}

function Write-LogSuccess {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor $Colors.Green
}

function Write-LogWarning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor $Colors.Yellow
}

function Write-LogError {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor $Colors.Red
}

# Show usage information
function Show-Usage {
    Write-Host @"
Usage: .\Start-DockerCompose.ps1 [OPTIONS]

Actions:
  up          Start services (default)
  down        Stop and remove services
  restart     Restart services
  logs        Show service logs
  status      Show service status
  build       Build services
  pull        Pull service images

Options:
  -Environment ENV        Environment (development|staging|production, default: production)
  -ComposeFile FILE       Custom compose file path
  -Detached              Run in detached mode (default: true)
  -Build                 Build images before starting
  -Pull                  Pull images before starting
  -RemoveOrphans         Remove orphaned containers
  -Service SERVICE       Target specific service
  -Follow COUNT          Number of log lines to follow (default: 100)
  -Help                  Show this help message

Examples:
  .\Start-DockerCompose.ps1 -Action up -Environment production
  .\Start-DockerCompose.ps1 -Action logs -Service anythingllm-api -Follow 50
  .\Start-DockerCompose.ps1 -Action down -RemoveOrphans
  .\Start-DockerCompose.ps1 -Action build -Service anythingllm-api
"@
}

# Get compose file based on environment
function Get-ComposeFile {
    param([string]$env)
    
    if ($ComposeFile) {
        return $ComposeFile
    }
    
    switch ($env) {
        "development" { return "docker-compose.yml" }
        "staging" { return "docker-compose.staging.yml" }
        "production" { return "docker-compose.production.yml" }
        default { return "docker-compose.production.yml" }
    }
}

# Check prerequisites
function Test-Prerequisites {
    Write-LogInfo "Checking prerequisites..."
    
    # Check if Docker is installed and running
    try {
        $null = Get-Command docker -ErrorAction Stop
        $dockerInfo = docker info 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Docker daemon is not running"
        }
    }
    catch {
        Write-LogError "Docker is not installed or not running: $_"
        exit 1
    }
    
    # Check if Docker Compose is available
    try {
        $null = docker compose version 2>$null
        if ($LASTEXITCODE -ne 0) {
            # Try legacy docker-compose
            $null = Get-Command docker-compose -ErrorAction Stop
        }
    }
    catch {
        Write-LogError "Docker Compose is not installed"
        exit 1
    }
    
    Write-LogSuccess "Prerequisites check completed"
}

# Get Docker Compose command
function Get-DockerComposeCommand {
    try {
        $null = docker compose version 2>$null
        if ($LASTEXITCODE -eq 0) {
            return "docker", "compose"
        }
    }
    catch {}
    
    try {
        $null = Get-Command docker-compose -ErrorAction Stop
        return "docker-compose"
    }
    catch {
        Write-LogError "Neither 'docker compose' nor 'docker-compose' is available"
        exit 1
    }
}

# Start services
function Start-Services {
    param([string]$composeFile)
    
    Write-LogInfo "Starting services..."
    
    $composeCmd = Get-DockerComposeCommand
    $args = @()
    
    if ($composeCmd.Count -gt 1) {
        $args += $composeCmd[1]
    }
    
    $args += "-f", $composeFile, "up"
    
    if ($Detached) {
        $args += "-d"
    }
    
    if ($Build) {
        $args += "--build"
    }
    
    if ($Pull) {
        $args += "--pull", "always"
    }
    
    if ($RemoveOrphans) {
        $args += "--remove-orphans"
    }
    
    if ($Service) {
        $args += $Service
    }
    
    try {
        if ($composeCmd.Count -gt 1) {
            & $composeCmd[0] @args
        }
        else {
            & $composeCmd @args
        }
        
        if ($LASTEXITCODE -eq 0) {
            Write-LogSuccess "Services started successfully"
            
            if ($Detached) {
                Write-LogInfo "Services are running in detached mode"
                Write-LogInfo "Use '.\Start-DockerCompose.ps1 -Action logs' to view logs"
                Write-LogInfo "Use '.\Start-DockerCompose.ps1 -Action status' to check status"
            }
        }
        else {
            throw "Docker Compose up failed with exit code $LASTEXITCODE"
        }
    }
    catch {
        Write-LogError "Failed to start services: $_"
        exit 1
    }
}

# Stop services
function Stop-Services {
    param([string]$composeFile)
    
    Write-LogInfo "Stopping services..."
    
    $composeCmd = Get-DockerComposeCommand
    $args = @()
    
    if ($composeCmd.Count -gt 1) {
        $args += $composeCmd[1]
    }
    
    $args += "-f", $composeFile, "down"
    
    if ($RemoveOrphans) {
        $args += "--remove-orphans"
    }
    
    try {
        if ($composeCmd.Count -gt 1) {
            & $composeCmd[0] @args
        }
        else {
            & $composeCmd @args
        }
        
        if ($LASTEXITCODE -eq 0) {
            Write-LogSuccess "Services stopped successfully"
        }
        else {
            throw "Docker Compose down failed with exit code $LASTEXITCODE"
        }
    }
    catch {
        Write-LogError "Failed to stop services: $_"
        exit 1
    }
}

# Restart services
function Restart-Services {
    param([string]$composeFile)
    
    Write-LogInfo "Restarting services..."
    
    $composeCmd = Get-DockerComposeCommand
    $args = @()
    
    if ($composeCmd.Count -gt 1) {
        $args += $composeCmd[1]
    }
    
    $args += "-f", $composeFile, "restart"
    
    if ($Service) {
        $args += $Service
    }
    
    try {
        if ($composeCmd.Count -gt 1) {
            & $composeCmd[0] @args
        }
        else {
            & $composeCmd @args
        }
        
        if ($LASTEXITCODE -eq 0) {
            Write-LogSuccess "Services restarted successfully"
        }
        else {
            throw "Docker Compose restart failed with exit code $LASTEXITCODE"
        }
    }
    catch {
        Write-LogError "Failed to restart services: $_"
        exit 1
    }
}

# Show logs
function Show-Logs {
    param([string]$composeFile)
    
    Write-LogInfo "Showing service logs..."
    
    $composeCmd = Get-DockerComposeCommand
    $args = @()
    
    if ($composeCmd.Count -gt 1) {
        $args += $composeCmd[1]
    }
    
    $args += "-f", $composeFile, "logs"
    
    if ($Follow -gt 0) {
        $args += "--tail", $Follow.ToString()
    }
    
    $args += "-f"
    
    if ($Service) {
        $args += $Service
    }
    
    try {
        if ($composeCmd.Count -gt 1) {
            & $composeCmd[0] @args
        }
        else {
            & $composeCmd @args
        }
    }
    catch {
        Write-LogError "Failed to show logs: $_"
        exit 1
    }
}

# Show status
function Show-Status {
    param([string]$composeFile)
    
    Write-LogInfo "Showing service status..."
    
    $composeCmd = Get-DockerComposeCommand
    $args = @()
    
    if ($composeCmd.Count -gt 1) {
        $args += $composeCmd[1]
    }
    
    $args += "-f", $composeFile, "ps"
    
    try {
        if ($composeCmd.Count -gt 1) {
            & $composeCmd[0] @args
        }
        else {
            & $composeCmd @args
        }
    }
    catch {
        Write-LogError "Failed to show status: $_"
        exit 1
    }
}

# Build services
function Build-Services {
    param([string]$composeFile)
    
    Write-LogInfo "Building services..."
    
    $composeCmd = Get-DockerComposeCommand
    $args = @()
    
    if ($composeCmd.Count -gt 1) {
        $args += $composeCmd[1]
    }
    
    $args += "-f", $composeFile, "build"
    
    if ($Service) {
        $args += $Service
    }
    
    try {
        if ($composeCmd.Count -gt 1) {
            & $composeCmd[0] @args
        }
        else {
            & $composeCmd @args
        }
        
        if ($LASTEXITCODE -eq 0) {
            Write-LogSuccess "Services built successfully"
        }
        else {
            throw "Docker Compose build failed with exit code $LASTEXITCODE"
        }
    }
    catch {
        Write-LogError "Failed to build services: $_"
        exit 1
    }
}

# Pull images
function Pull-Images {
    param([string]$composeFile)
    
    Write-LogInfo "Pulling service images..."
    
    $composeCmd = Get-DockerComposeCommand
    $args = @()
    
    if ($composeCmd.Count -gt 1) {
        $args += $composeCmd[1]
    }
    
    $args += "-f", $composeFile, "pull"
    
    if ($Service) {
        $args += $Service
    }
    
    try {
        if ($composeCmd.Count -gt 1) {
            & $composeCmd[0] @args
        }
        else {
            & $composeCmd @args
        }
        
        if ($LASTEXITCODE -eq 0) {
            Write-LogSuccess "Images pulled successfully"
        }
        else {
            throw "Docker Compose pull failed with exit code $LASTEXITCODE"
        }
    }
    catch {
        Write-LogError "Failed to pull images: $_"
        exit 1
    }
}

# Main function
function Invoke-Main {
    Write-LogInfo "Starting Docker Compose management..."
    Write-LogInfo "Action: $Action"
    Write-LogInfo "Environment: $Environment"
    
    $composeFile = Get-ComposeFile -env $Environment
    Write-LogInfo "Compose File: $composeFile"
    
    # Check if compose file exists
    if (-not (Test-Path $composeFile)) {
        Write-LogError "Compose file not found: $composeFile"
        exit 1
    }
    
    Test-Prerequisites
    
    switch ($Action) {
        "up" { Start-Services -composeFile $composeFile }
        "down" { Stop-Services -composeFile $composeFile }
        "restart" { Restart-Services -composeFile $composeFile }
        "logs" { Show-Logs -composeFile $composeFile }
        "status" { Show-Status -composeFile $composeFile }
        "build" { Build-Services -composeFile $composeFile }
        "pull" { Pull-Images -composeFile $composeFile }
        default {
            Write-LogError "Unknown action: $Action"
            Show-Usage
            exit 1
        }
    }
}

# Script entry point
if ($Help) {
    Show-Usage
    exit 0
}

# Set up error handling
trap {
    Write-LogError "An unexpected error occurred: $_"
    exit 1
}

# Run main function
Invoke-Main