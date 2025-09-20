# AnythingLLM API Deployment Script for Windows PowerShell
# This script deploys the AnythingLLM API to Kubernetes

[CmdletBinding()]
param(
    [string]$Namespace = "anythingllm",
    [string]$Environment = "production",
    [string]$ImageTag = "latest",
    [string]$Registry = "",
    [switch]$DryRun = $false,
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
Usage: .\deploy.ps1 [OPTIONS]

Options:
  -Namespace NAMESPACE     Kubernetes namespace (default: anythingllm)
  -Environment ENV         Environment (development|staging|production)
  -ImageTag TAG           Docker image tag (default: latest)
  -Registry REGISTRY      Docker registry URL
  -DryRun                 Perform dry run without applying changes
  -Help                   Show this help message

Examples:
  .\deploy.ps1 -Environment production -Registry gcr.io/my-project -ImageTag v1.0.0
  .\deploy.ps1 -DryRun -Namespace anythingllm-dev
"@
}

# Check prerequisites
function Test-Prerequisites {
    Write-LogInfo "Checking prerequisites..."
    
    # Check if kubectl is installed
    try {
        $null = Get-Command kubectl -ErrorAction Stop
    }
    catch {
        Write-LogError "kubectl is not installed or not in PATH"
        exit 1
    }
    
    # Check if kubectl can connect to cluster
    try {
        $null = kubectl cluster-info 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Cannot connect to cluster"
        }
    }
    catch {
        Write-LogError "Cannot connect to Kubernetes cluster"
        exit 1
    }
    
    # Check if namespace exists
    try {
        $null = kubectl get namespace $Namespace 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-LogWarning "Namespace '$Namespace' does not exist. Creating..."
            kubectl create namespace $Namespace
            kubectl label namespace $Namespace name=$Namespace
        }
    }
    catch {
        Write-LogError "Failed to create namespace '$Namespace'"
        exit 1
    }
    
    Write-LogSuccess "Prerequisites check completed"
}

# Build and push Docker image
function Build-AndPushImage {
    if ($Registry) {
        Write-LogInfo "Building and pushing Docker image..."
        
        $imageName = "$Registry/anythingllm-api:$ImageTag"
        $buildDate = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        
        try {
            # Get git commit hash if available
            $vcsRef = ""
            if (Get-Command git -ErrorAction SilentlyContinue) {
                $vcsRef = git rev-parse HEAD 2>$null
                if ($LASTEXITCODE -ne 0) {
                    $vcsRef = "unknown"
                }
            }
            else {
                $vcsRef = "unknown"
            }
            
            # Build image
            docker build `
                --build-arg BUILD_DATE="$buildDate" `
                --build-arg VERSION="$ImageTag" `
                --build-arg VCS_REF="$vcsRef" `
                -t $imageName `
                -f Dockerfile .
            
            if ($LASTEXITCODE -ne 0) {
                throw "Docker build failed"
            }
            
            # Push image
            docker push $imageName
            
            if ($LASTEXITCODE -ne 0) {
                throw "Docker push failed"
            }
            
            Write-LogSuccess "Image built and pushed: $imageName"
        }
        catch {
            Write-LogError "Failed to build and push image: $_"
            exit 1
        }
    }
    else {
        Write-LogWarning "No registry specified, skipping image build and push"
    }
}

# Deploy configuration
function Deploy-Config {
    Write-LogInfo "Deploying configuration..."
    
    try {
        # Apply RBAC
        $rbacArgs = @("apply", "-f", "k8s/rbac.yaml", "-n", $Namespace)
        if ($DryRun) { $rbacArgs += "--dry-run=client" }
        & kubectl @rbacArgs
        
        # Apply ConfigMap
        $configArgs = @("apply", "-f", "k8s/configmap.yaml", "-n", $Namespace)
        if ($DryRun) { $configArgs += "--dry-run=client" }
        & kubectl @configArgs
        
        # Apply Secret (if exists)
        if (Test-Path "k8s/secret.yaml") {
            $secretArgs = @("apply", "-f", "k8s/secret.yaml", "-n", $Namespace)
            if ($DryRun) { $secretArgs += "--dry-run=client" }
            & kubectl @secretArgs
        }
        else {
            Write-LogWarning "Secret file not found. Please create k8s/secret.yaml with your secrets"
        }
        
        # Apply PVC
        $pvcArgs = @("apply", "-f", "k8s/pvc.yaml", "-n", $Namespace)
        if ($DryRun) { $pvcArgs += "--dry-run=client" }
        & kubectl @pvcArgs
        
        Write-LogSuccess "Configuration deployed"
    }
    catch {
        Write-LogError "Failed to deploy configuration: $_"
        exit 1
    }
}

# Deploy application
function Deploy-App {
    Write-LogInfo "Deploying application..."
    
    try {
        # Update image in deployment if registry is specified
        $deploymentFile = "k8s/deployment.yaml"
        $originalContent = $null
        
        if ($Registry) {
            $imageName = "$Registry/anythingllm-api:$ImageTag"
            $originalContent = Get-Content $deploymentFile -Raw
            $updatedContent = $originalContent -replace "image: anythingllm-api:latest", "image: $imageName"
            Set-Content $deploymentFile -Value $updatedContent -NoNewline
        }
        
        # Apply deployment
        $deployArgs = @("apply", "-f", $deploymentFile, "-n", $Namespace)
        if ($DryRun) { $deployArgs += "--dry-run=client" }
        & kubectl @deployArgs
        
        # Apply service
        $serviceArgs = @("apply", "-f", "k8s/service.yaml", "-n", $Namespace)
        if ($DryRun) { $serviceArgs += "--dry-run=client" }
        & kubectl @serviceArgs
        
        # Apply HPA
        $hpaArgs = @("apply", "-f", "k8s/hpa.yaml", "-n", $Namespace)
        if ($DryRun) { $hpaArgs += "--dry-run=client" }
        & kubectl @hpaArgs
        
        # Apply Network Policy
        $netpolArgs = @("apply", "-f", "k8s/network-policy.yaml", "-n", $Namespace)
        if ($DryRun) { $netpolArgs += "--dry-run=client" }
        & kubectl @netpolArgs
        
        # Apply Ingress (if not dry run)
        if (-not $DryRun) {
            kubectl apply -f k8s/ingress.yaml -n $Namespace
        }
        
        # Restore original deployment file
        if ($Registry -and $originalContent) {
            Set-Content $deploymentFile -Value $originalContent -NoNewline
        }
        
        Write-LogSuccess "Application deployed"
    }
    catch {
        Write-LogError "Failed to deploy application: $_"
        # Restore original deployment file on error
        if ($Registry -and $originalContent) {
            Set-Content $deploymentFile -Value $originalContent -NoNewline
        }
        exit 1
    }
}

# Deploy monitoring
function Deploy-Monitoring {
    Write-LogInfo "Deploying monitoring..."
    
    try {
        # Check if Prometheus operator is installed
        $crdCheck = kubectl get crd servicemonitors.monitoring.coreos.com 2>$null
        if ($LASTEXITCODE -eq 0) {
            $monitorArgs = @("apply", "-f", "k8s/monitoring/servicemonitor.yaml", "-n", $Namespace)
            if ($DryRun) { $monitorArgs += "--dry-run=client" }
            & kubectl @monitorArgs
            Write-LogSuccess "ServiceMonitor deployed"
        }
        else {
            Write-LogWarning "Prometheus operator not found, skipping ServiceMonitor deployment"
        }
    }
    catch {
        Write-LogWarning "Failed to deploy monitoring: $_"
    }
}

# Wait for deployment
function Wait-ForDeployment {
    if ($DryRun) {
        Write-LogInfo "Dry run mode, skipping deployment wait"
        return
    }
    
    Write-LogInfo "Waiting for deployment to be ready..."
    
    try {
        $rolloutResult = kubectl rollout status deployment/anythingllm-api -n $Namespace --timeout=300s
        if ($LASTEXITCODE -eq 0) {
            Write-LogSuccess "Deployment is ready"
        }
        else {
            throw "Deployment failed to become ready"
        }
    }
    catch {
        Write-LogError "Deployment failed to become ready: $_"
        exit 1
    }
}

# Health check
function Test-Health {
    if ($DryRun) {
        Write-LogInfo "Dry run mode, skipping health check"
        return
    }
    
    Write-LogInfo "Performing health check..."
    
    $portForwardJob = $null
    try {
        # Start port forward in background
        $portForwardJob = Start-Job -ScriptBlock {
            kubectl port-forward service/anythingllm-api-service 8080:80 -n $using:Namespace
        }
        
        # Wait a moment for port forward to establish
        Start-Sleep -Seconds 5
        
        # Test health endpoint
        $healthResponse = Invoke-WebRequest -Uri "http://localhost:8080/api/v1/health" -TimeoutSec 10 -UseBasicParsing
        
        if ($healthResponse.StatusCode -eq 200) {
            Write-LogSuccess "Health check passed"
        }
        else {
            throw "Health check returned status code: $($healthResponse.StatusCode)"
        }
    }
    catch {
        Write-LogError "Health check failed: $_"
        exit 1
    }
    finally {
        # Clean up port forward job
        if ($portForwardJob) {
            Stop-Job $portForwardJob -ErrorAction SilentlyContinue
            Remove-Job $portForwardJob -ErrorAction SilentlyContinue
        }
    }
}

# Cleanup function
function Invoke-Cleanup {
    Write-LogInfo "Cleaning up..."
    # Stop any background jobs
    Get-Job | Stop-Job -ErrorAction SilentlyContinue
    Get-Job | Remove-Job -ErrorAction SilentlyContinue
}

# Main deployment function
function Invoke-Main {
    Write-LogInfo "Starting AnythingLLM API deployment..."
    Write-LogInfo "Environment: $Environment"
    Write-LogInfo "Namespace: $Namespace"
    Write-LogInfo "Image Tag: $ImageTag"
    Write-LogInfo "Registry: $(if ($Registry) { $Registry } else { 'Not specified' })"
    Write-LogInfo "Dry Run: $DryRun"
    
    try {
        Test-Prerequisites
        Build-AndPushImage
        Deploy-Config
        Deploy-App
        Deploy-Monitoring
        Wait-ForDeployment
        Test-Health
        
        Write-LogSuccess "Deployment completed successfully!"
        
        if (-not $DryRun) {
            Write-LogInfo "Application is available at:"
            try {
                $ingressHost = kubectl get ingress anythingllm-api-ingress -n $Namespace -o jsonpath='{.spec.rules[0].host}' 2>$null
                if ($LASTEXITCODE -eq 0 -and $ingressHost) {
                    Write-Host "  https://$ingressHost"
                }
                else {
                    Write-Host "  Service: anythingllm-api-service.$Namespace.svc.cluster.local"
                }
            }
            catch {
                Write-Host "  Service: anythingllm-api-service.$Namespace.svc.cluster.local"
            }
        }
    }
    catch {
        Write-LogError "Deployment failed: $_"
        exit 1
    }
    finally {
        Invoke-Cleanup
    }
}

# Script entry point
if ($Help) {
    Show-Usage
    exit 0
}

# Validate parameters
if ($Environment -notin @("development", "staging", "production")) {
    Write-LogError "Invalid environment: $Environment. Must be one of: development, staging, production"
    Show-Usage
    exit 1
}

# Set up error handling
trap {
    Write-LogError "An unexpected error occurred: $_"
    Invoke-Cleanup
    exit 1
}

# Run main function
Invoke-Main