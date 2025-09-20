#!/bin/bash

# AnythingLLM API Deployment Script
# This script deploys the AnythingLLM API to Kubernetes

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-anythingllm}"
ENVIRONMENT="${ENVIRONMENT:-production}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${REGISTRY:-}"
DRY_RUN="${DRY_RUN:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check if kubectl can connect to cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_warning "Namespace '$NAMESPACE' does not exist. Creating..."
        kubectl create namespace "$NAMESPACE"
        kubectl label namespace "$NAMESPACE" name="$NAMESPACE"
    fi
    
    log_success "Prerequisites check completed"
}

# Build and push Docker image
build_and_push_image() {
    if [[ -n "$REGISTRY" ]]; then
        log_info "Building and pushing Docker image..."
        
        local image_name="${REGISTRY}/anythingllm-api:${IMAGE_TAG}"
        
        # Build image
        docker build \
            --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
            --build-arg VERSION="$IMAGE_TAG" \
            --build-arg VCS_REF="$(git rev-parse HEAD)" \
            -t "$image_name" \
            -f Dockerfile .
        
        # Push image
        docker push "$image_name"
        
        log_success "Image built and pushed: $image_name"
    else
        log_warning "No registry specified, skipping image build and push"
    fi
}

# Deploy configuration
deploy_config() {
    log_info "Deploying configuration..."
    
    # Apply RBAC
    kubectl apply -f k8s/rbac.yaml -n "$NAMESPACE" ${DRY_RUN:+--dry-run=client}
    
    # Apply ConfigMap
    kubectl apply -f k8s/configmap.yaml -n "$NAMESPACE" ${DRY_RUN:+--dry-run=client}
    
    # Apply Secret (if exists)
    if [[ -f "k8s/secret.yaml" ]]; then
        kubectl apply -f k8s/secret.yaml -n "$NAMESPACE" ${DRY_RUN:+--dry-run=client}
    else
        log_warning "Secret file not found. Please create k8s/secret.yaml with your secrets"
    fi
    
    # Apply PVC
    kubectl apply -f k8s/pvc.yaml -n "$NAMESPACE" ${DRY_RUN:+--dry-run=client}
    
    log_success "Configuration deployed"
}

# Deploy application
deploy_app() {
    log_info "Deploying application..."
    
    # Update image in deployment if registry is specified
    if [[ -n "$REGISTRY" ]]; then
        local image_name="${REGISTRY}/anythingllm-api:${IMAGE_TAG}"
        sed -i.bak "s|image: anythingllm-api:latest|image: $image_name|g" k8s/deployment.yaml
    fi
    
    # Apply deployment
    kubectl apply -f k8s/deployment.yaml -n "$NAMESPACE" ${DRY_RUN:+--dry-run=client}
    
    # Apply service
    kubectl apply -f k8s/service.yaml -n "$NAMESPACE" ${DRY_RUN:+--dry-run=client}
    
    # Apply HPA
    kubectl apply -f k8s/hpa.yaml -n "$NAMESPACE" ${DRY_RUN:+--dry-run=client}
    
    # Apply Network Policy
    kubectl apply -f k8s/network-policy.yaml -n "$NAMESPACE" ${DRY_RUN:+--dry-run=client}
    
    # Apply Ingress (if not dry run)
    if [[ "$DRY_RUN" != "true" ]]; then
        kubectl apply -f k8s/ingress.yaml -n "$NAMESPACE"
    fi
    
    # Restore original deployment file
    if [[ -n "$REGISTRY" && -f "k8s/deployment.yaml.bak" ]]; then
        mv k8s/deployment.yaml.bak k8s/deployment.yaml
    fi
    
    log_success "Application deployed"
}

# Deploy monitoring
deploy_monitoring() {
    log_info "Deploying monitoring..."
    
    # Check if Prometheus operator is installed
    if kubectl get crd servicemonitors.monitoring.coreos.com &> /dev/null; then
        kubectl apply -f k8s/monitoring/servicemonitor.yaml -n "$NAMESPACE" ${DRY_RUN:+--dry-run=client}
        log_success "ServiceMonitor deployed"
    else
        log_warning "Prometheus operator not found, skipping ServiceMonitor deployment"
    fi
}

# Wait for deployment
wait_for_deployment() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Dry run mode, skipping deployment wait"
        return
    fi
    
    log_info "Waiting for deployment to be ready..."
    
    if kubectl rollout status deployment/anythingllm-api -n "$NAMESPACE" --timeout=300s; then
        log_success "Deployment is ready"
    else
        log_error "Deployment failed to become ready"
        exit 1
    fi
}

# Health check
health_check() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Dry run mode, skipping health check"
        return
    fi
    
    log_info "Performing health check..."
    
    # Port forward to test health endpoint
    kubectl port-forward service/anythingllm-api-service 8080:80 -n "$NAMESPACE" &
    local port_forward_pid=$!
    
    sleep 5
    
    if curl -f http://localhost:8080/api/v1/health &> /dev/null; then
        log_success "Health check passed"
    else
        log_error "Health check failed"
        kill $port_forward_pid 2>/dev/null || true
        exit 1
    fi
    
    kill $port_forward_pid 2>/dev/null || true
}

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    # Kill any background processes
    jobs -p | xargs -r kill 2>/dev/null || true
}

# Main deployment function
main() {
    log_info "Starting AnythingLLM API deployment..."
    log_info "Environment: $ENVIRONMENT"
    log_info "Namespace: $NAMESPACE"
    log_info "Image Tag: $IMAGE_TAG"
    log_info "Registry: ${REGISTRY:-'Not specified'}"
    log_info "Dry Run: $DRY_RUN"
    
    # Set trap for cleanup
    trap cleanup EXIT
    
    check_prerequisites
    build_and_push_image
    deploy_config
    deploy_app
    deploy_monitoring
    wait_for_deployment
    health_check
    
    log_success "Deployment completed successfully!"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        log_info "Application is available at:"
        kubectl get ingress anythingllm-api-ingress -n "$NAMESPACE" -o jsonpath='{.spec.rules[0].host}' 2>/dev/null || echo "  Service: anythingllm-api-service.$NAMESPACE.svc.cluster.local"
    fi
}

# Script usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -n, --namespace NAMESPACE    Kubernetes namespace (default: anythingllm)"
    echo "  -e, --environment ENV        Environment (development|staging|production)"
    echo "  -t, --tag TAG               Docker image tag (default: latest)"
    echo "  -r, --registry REGISTRY     Docker registry URL"
    echo "  -d, --dry-run               Perform dry run without applying changes"
    echo "  -h, --help                  Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --environment production --registry gcr.io/my-project --tag v1.0.0"
    echo "  $0 --dry-run --namespace anythingllm-dev"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN="true"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Run main function
main