# AnythingLLM API Health Check Script for Windows PowerShell
# This script performs health checks for the AnythingLLM API container

[CmdletBinding()]
param(
    [string]$Host = "localhost",
    [int]$Port = 8000,
    [int]$Timeout = 10,
    [ValidateSet("liveness", "readiness", "basic", "detailed")]
    [string]$CheckType = "basic",
    [int]$Retries = 1,
    [int]$RetryDelay = 1,
    [switch]$Verbose = $false
)

# Set strict mode and error action
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Configure logging
if ($Verbose) {
    $VerbosePreference = "Continue"
}

class HealthChecker {
    [string]$Host
    [int]$Port
    [int]$Timeout
    [string]$BaseUrl
    
    HealthChecker([string]$host, [int]$port, [int]$timeout) {
        $this.Host = $host
        $this.Port = $port
        $this.Timeout = $timeout
        $this.BaseUrl = "http://$host`:$port"
    }
    
    [hashtable] CheckBasicHealth() {
        try {
            $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
            $response = Invoke-WebRequest -Uri "$($this.BaseUrl)/api/v1/health" -TimeoutSec $this.Timeout -UseBasicParsing
            $stopwatch.Stop()
            
            $data = $response.Content | ConvertFrom-Json
            
            return @{
                status = "healthy"
                response_time = $stopwatch.Elapsed.TotalSeconds
                status_code = $response.StatusCode
                data = $data
            }
        }
        catch {
            return @{
                status = "unhealthy"
                error = $_.Exception.Message
                error_type = $_.Exception.GetType().Name
            }
        }
    }
    
    [hashtable] CheckDetailedHealth() {
        try {
            $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
            $response = Invoke-WebRequest -Uri "$($this.BaseUrl)/api/v1/health/detailed" -TimeoutSec $this.Timeout -UseBasicParsing
            $stopwatch.Stop()
            
            $data = $response.Content | ConvertFrom-Json
            
            return @{
                status = "healthy"
                response_time = $stopwatch.Elapsed.TotalSeconds
                status_code = $response.StatusCode
                data = $data
            }
        }
        catch {
            return @{
                status = "unhealthy"
                error = $_.Exception.Message
                error_type = $_.Exception.GetType().Name
            }
        }
    }
    
    [hashtable] CheckReadiness() {
        try {
            # Check basic health first
            $basicHealth = $this.CheckBasicHealth()
            if ($basicHealth.status -ne "healthy") {
                return $basicHealth
            }
            
            # Check detailed health for dependencies
            $detailedHealth = $this.CheckDetailedHealth()
            if ($detailedHealth.status -ne "healthy") {
                return $detailedHealth
            }
            
            # Check if all critical dependencies are healthy
            $healthData = $detailedHealth.data
            if ($healthData.dependencies) {
                foreach ($depName in $healthData.dependencies.PSObject.Properties.Name) {
                    $depStatus = $healthData.dependencies.$depName
                    if ($depStatus.status -ne "healthy") {
                        return @{
                            status = "not_ready"
                            error = "Dependency $depName is not healthy"
                            dependency_status = $depStatus
                        }
                    }
                }
            }
            
            return @{
                status = "ready"
                response_time = $detailedHealth.response_time
                dependencies = if ($healthData.dependencies) { $healthData.dependencies } else { @{} }
            }
        }
        catch {
            return @{
                status = "not_ready"
                error = $_.Exception.Message
                error_type = $_.Exception.GetType().Name
            }
        }
    }
    
    [hashtable] CheckLiveness() {
        return $this.CheckBasicHealth()
    }
}

function Write-LogInfo {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-LogError {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Show-Usage {
    Write-Host @"
Usage: .\Test-Health.ps1 [OPTIONS]

Options:
  -Host HOST              Host to check (default: localhost)
  -Port PORT              Port to check (default: 8000)
  -Timeout TIMEOUT        Request timeout in seconds (default: 10)
  -CheckType TYPE         Type of health check (liveness|readiness|basic|detailed, default: basic)
  -Retries COUNT          Number of retries (default: 1)
  -RetryDelay SECONDS     Delay between retries in seconds (default: 1)
  -Verbose                Verbose output

Examples:
  .\Test-Health.ps1 -CheckType readiness -Verbose
  .\Test-Health.ps1 -Host api.example.com -Port 443 -CheckType detailed
  .\Test-Health.ps1 -Retries 3 -RetryDelay 2
"@
}

# Main function
function Invoke-Main {
    Write-Verbose "Starting health check..."
    Write-Verbose "Host: $Host"
    Write-Verbose "Port: $Port"
    Write-Verbose "Check Type: $CheckType"
    Write-Verbose "Timeout: $Timeout seconds"
    Write-Verbose "Retries: $Retries"
    
    $checker = [HealthChecker]::new($Host, $Port, $Timeout)
    
    # Perform health check with retries
    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        if ($attempt -gt 1) {
            Write-LogInfo "Retry attempt $attempt/$Retries"
            Start-Sleep -Seconds $RetryDelay
        }
        
        try {
            $result = switch ($CheckType) {
                "liveness" { $checker.CheckLiveness() }
                "readiness" { $checker.CheckReadiness() }
                "detailed" { $checker.CheckDetailedHealth() }
                default { $checker.CheckBasicHealth() }
            }
            
            # Output result
            if ($Verbose) {
                $result | ConvertTo-Json -Depth 10 | Write-Host
            }
            else {
                Write-Host "Status: $($result.status)"
                if ($result.status -in @("unhealthy", "not_ready") -and $result.error) {
                    Write-Host "Error: $($result.error)"
                }
            }
            
            # Exit with appropriate code
            if ($result.status -in @("healthy", "ready")) {
                Write-LogInfo "Health check passed"
                exit 0
            }
            else {
                Write-LogError "Health check failed: $($result.error)"
                if ($attempt -eq $Retries) {
                    exit 1
                }
            }
        }
        catch {
            Write-LogError "Health check error: $_"
            if ($attempt -eq $Retries) {
                exit 1
            }
        }
    }
}

# Script entry point
try {
    Invoke-Main
}
catch {
    Write-LogError "Unexpected error: $_"
    exit 1
}