# AnythingLLM API Deployment Guide

This guide covers deployment options for the AnythingLLM API service, including Docker, Kubernetes, and production configurations.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Environment Configuration](#environment-configuration)
- [Monitoring and Logging](#monitoring-and-logging)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **CPU**: Minimum 2 cores, recommended 4+ cores
- **Memory**: Minimum 2GB RAM, recommended 4GB+ RAM
- **Storage**: Minimum 10GB, recommended 50GB+ for document storage
- **Network**: HTTPS/TLS termination capability

### Dependencies

- **PostgreSQL**: Version 12+ (required)
- **Redis**: Version 6+ (optional but recommended for production)
- **AnythingLLM**: Compatible instance with API access

### Tools Required

- Docker 20.10+
- Docker Compose 2.0+ (for Docker deployment)
- kubectl 1.20+ (for Kubernetes deployment)
- Kubernetes cluster 1.20+ (for Kubernetes deployment)
- PowerShell 5.1+ (for Windows PowerShell scripts)
- Python 3.8+ (for health check scripts)

## Docker Deployment

### Quick Start with Docker Compose

1. **Clone and prepare environment**:
   ```bash
   git clone <repository>
   cd api
   cp .env.example .env
   ```

2. **Configure environment variables**:
   ```bash
   # Edit .env file with your configuration
   nano .env
   ```

3. **Deploy with Docker Compose**:

   #### Linux/macOS (Bash)
   ```bash
   # Production deployment
   docker-compose -f docker-compose.production.yml up -d
   
   # Development deployment
   docker-compose up -d
   ```

   #### Windows (PowerShell)
   ```powershell
   # Using the PowerShell script
   .\scripts\Start-DockerCompose.ps1 -Action up -Environment production
   
   # Or directly with Docker Compose
   docker-compose -f docker-compose.production.yml up -d
   ```

4. **Verify deployment**:

   #### Linux/macOS (Bash)
   ```bash
   # Check service health
   curl http://localhost:8000/api/v1/health
   
   # View logs
   docker-compose logs -f anythingllm-api
   ```

   #### Windows (PowerShell)
   ```powershell
   # Check service health
   .\scripts\Test-Health.ps1 -Host localhost -Port 8000
   
   # View logs
   .\scripts\Start-DockerCompose.ps1 -Action logs -Service anythingllm-api
   ```

### Docker Build Options

```bash
# Build with specific version
docker build \
  --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
  --build-arg VERSION="1.0.0" \
  --build-arg VCS_REF="$(git rev-parse HEAD)" \
  -t anythingllm-api:1.0.0 .

# Multi-platform build
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t anythingllm-api:1.0.0 \
  --push .
```

## Kubernetes Deployment

### Prerequisites

1. **Create namespace**:
   ```bash
   kubectl create namespace anythingllm
   kubectl label namespace anythingllm name=anythingllm
   ```

2. **Configure secrets**:
   ```bash
   # Create secrets from environment file
   kubectl create secret generic anythingllm-api-secrets \
     --from-env-file=config/production.env \
     -n anythingllm
   ```

### Automated Deployment

Use the provided deployment script:

#### Linux/macOS (Bash)
```bash
# Production deployment
./scripts/deploy.sh \
  --environment production \
  --registry gcr.io/my-project \
  --tag v1.0.0 \
  --namespace anythingllm

# Staging deployment
./scripts/deploy.sh \
  --environment staging \
  --registry gcr.io/my-project \
  --tag v1.0.0-staging \
  --namespace anythingllm-staging

# Dry run
./scripts/deploy.sh --dry-run
```

#### Windows (PowerShell)
```powershell
# Production deployment
.\scripts\Deploy.ps1 `
  -Environment production `
  -Registry gcr.io/my-project `
  -ImageTag v1.0.0 `
  -Namespace anythingllm

# Staging deployment
.\scripts\Deploy.ps1 `
  -Environment staging `
  -Registry gcr.io/my-project `
  -ImageTag v1.0.0-staging `
  -Namespace anythingllm-staging

# Dry run
.\scripts\Deploy.ps1 -DryRun
```

### Manual Deployment

1. **Deploy configuration**:
   ```bash
   kubectl apply -f k8s/rbac.yaml -n anythingllm
   kubectl apply -f k8s/configmap.yaml -n anythingllm
   kubectl apply -f k8s/secret.yaml -n anythingllm
   kubectl apply -f k8s/pvc.yaml -n anythingllm
   ```

2. **Deploy application**:
   ```bash
   kubectl apply -f k8s/deployment.yaml -n anythingllm
   kubectl apply -f k8s/service.yaml -n anythingllm
   kubectl apply -f k8s/hpa.yaml -n anythingllm
   kubectl apply -f k8s/ingress.yaml -n anythingllm
   ```

3. **Deploy monitoring**:
   ```bash
   kubectl apply -f k8s/monitoring/servicemonitor.yaml -n anythingllm
   ```

4. **Verify deployment**:
   ```bash
   # Check pod status
   kubectl get pods -n anythingllm
   
   # Check service health
   kubectl port-forward service/anythingllm-api-service 8080:80 -n anythingllm
   curl http://localhost:8080/api/v1/health
   ```

### Scaling

```bash
# Manual scaling
kubectl scale deployment anythingllm-api --replicas=5 -n anythingllm

# Auto-scaling is configured via HPA
kubectl get hpa -n anythingllm
```

## Environment Configuration

### Development Environment

```bash
# Use development configuration
cp config/development.env .env

# Key settings for development
DEBUG=true
LOG_LEVEL=DEBUG
RATE_LIMIT_ENABLED=false
REDIS_ENABLED=false
```

### Staging Environment

```bash
# Use staging configuration
cp config/staging.env .env

# Key settings for staging
STORAGE_TYPE=s3
REDIS_ENABLED=true
LOG_FORMAT=json
RATE_LIMIT_ENABLED=true
```

### Production Environment

```bash
# Use production configuration
cp config/production.env .env

# Key settings for production
STORAGE_TYPE=s3
REDIS_ENABLED=true
LOG_FORMAT=json
LOG_SANITIZE_SENSITIVE=true
RATE_LIMIT_ENABLED=true
WORKERS=4
```

### Required Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Yes | - |
| `ANYTHINGLLM_URL` | AnythingLLM service URL | Yes | - |
| `ANYTHINGLLM_API_KEY` | AnythingLLM API key | Yes | - |
| `SECRET_KEY` | JWT signing secret | Yes | - |
| `STORAGE_TYPE` | Storage backend (local/s3) | No | local |
| `REDIS_ENABLED` | Enable Redis cache | No | false |

### Optional S3 Configuration

```bash
# Required when STORAGE_TYPE=s3
S3_BUCKET=your-bucket-name
S3_REGION=us-west-2
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

## Monitoring and Logging

### Prometheus Metrics

The API exposes metrics at `/api/v1/metrics`:

- HTTP request metrics (rate, duration, status codes)
- Job processing metrics (active jobs, completion rate)
- System metrics (memory, CPU usage)
- External service health metrics

### Grafana Dashboard

Import the provided dashboard:

```bash
# Import dashboard configuration
kubectl create configmap grafana-dashboard \
  --from-file=k8s/monitoring/grafana-dashboard.json \
  -n monitoring
```

### Log Aggregation

#### Fluentd Configuration

```bash
# Deploy Fluentd for log collection
kubectl apply -f k8s/logging/fluentd-config.yaml -n anythingllm
```

#### Log Format

The API produces structured JSON logs:

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "level": "INFO",
  "message": "Request processed",
  "correlation_id": "req_123456",
  "user_id": "user_789",
  "method": "POST",
  "endpoint": "/api/v1/documents/upload",
  "status_code": 200,
  "response_time": 1.234
}
```

### Health Checks

#### Kubernetes Health Checks

- **Liveness Probe**: `/api/v1/health` (basic health)
- **Readiness Probe**: `/api/v1/health/detailed` (with dependencies)
- **Startup Probe**: `/api/v1/health` (initial startup)

#### Manual Health Check

##### Linux/macOS (Python)
```bash
# Basic health check
python scripts/health-check.py --check-type basic

# Detailed health check with dependencies
python scripts/health-check.py --check-type detailed

# Readiness check
python scripts/health-check.py --check-type readiness
```

##### Windows (PowerShell)
```powershell
# Basic health check
.\scripts\Test-Health.ps1 -CheckType basic

# Detailed health check with dependencies
.\scripts\Test-Health.ps1 -CheckType detailed

# Readiness check
.\scripts\Test-Health.ps1 -CheckType readiness

# With retries and verbose output
.\scripts\Test-Health.ps1 -CheckType readiness -Retries 3 -RetryDelay 2 -Verbose
```

## Security Considerations

### Container Security

- **Non-root user**: Containers run as non-root user (UID 1000)
- **Read-only filesystem**: Root filesystem is read-only
- **No new privileges**: `no-new-privileges` security option enabled
- **Minimal base image**: Uses Python slim image with minimal packages

### Network Security

- **Network policies**: Restrict pod-to-pod communication
- **TLS termination**: HTTPS/TLS at ingress/load balancer
- **Rate limiting**: Request throttling per IP/user
- **CORS configuration**: Proper cross-origin resource sharing

### Data Security

- **Secrets management**: Sensitive data in Kubernetes secrets
- **Log sanitization**: Sensitive data redacted from logs
- **File validation**: Strict file type and size validation
- **Input validation**: Comprehensive request validation

### Authentication & Authorization

- **JWT tokens**: Secure token-based authentication
- **API keys**: Alternative API key authentication
- **Role-based access**: User role and permission system
- **Audit logging**: Security event logging

## Troubleshooting

### Common Issues

#### 1. Database Connection Errors

```bash
# Check database connectivity
kubectl exec -it deployment/anythingllm-api -n anythingllm -- \
  python -c "import psycopg2; psycopg2.connect('$DATABASE_URL')"

# Check database logs
kubectl logs deployment/postgres -n anythingllm
```

#### 2. AnythingLLM Connection Issues

```bash
# Test AnythingLLM connectivity
curl -H "Authorization: Bearer $ANYTHINGLLM_API_KEY" \
  $ANYTHINGLLM_URL/api/v1/system/health

# Check API logs for external service errors
kubectl logs deployment/anythingllm-api -n anythingllm | grep "anythingllm"
```

#### 3. File Upload Issues

```bash
# Check storage configuration
kubectl describe configmap anythingllm-api-config -n anythingllm

# Check PVC status
kubectl get pvc -n anythingllm

# Check file permissions
kubectl exec -it deployment/anythingllm-api -n anythingllm -- \
  ls -la /app/uploads
```

#### 4. High Memory Usage

```bash
# Check memory metrics
kubectl top pods -n anythingllm

# Check for memory leaks in logs
kubectl logs deployment/anythingllm-api -n anythingllm | grep -i memory

# Restart deployment if needed
kubectl rollout restart deployment/anythingllm-api -n anythingllm
```

### Debugging Commands

```bash
# Get pod status and events
kubectl describe pod <pod-name> -n anythingllm

# Access pod shell
kubectl exec -it <pod-name> -n anythingllm -- /bin/bash

# View application logs
kubectl logs -f deployment/anythingllm-api -n anythingllm

# Check resource usage
kubectl top pods -n anythingllm
kubectl top nodes

# Check network connectivity
kubectl exec -it <pod-name> -n anythingllm -- nslookup postgres
kubectl exec -it <pod-name> -n anythingllm -- curl -I http://anythingllm:3001
```

### Performance Tuning

#### Resource Limits

```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "1Gi"
    cpu: "500m"
```

#### Scaling Configuration

```yaml
# HPA configuration
minReplicas: 2
maxReplicas: 10
targetCPUUtilizationPercentage: 70
targetMemoryUtilizationPercentage: 80
```

#### Database Optimization

```bash
# PostgreSQL connection pooling
DATABASE_URL=postgresql://user:pass@host:port/db?pool_size=20&max_overflow=30

# Redis configuration for caching
REDIS_ENABLED=true
REDIS_URL=redis://redis:6379/0
```

### Support and Maintenance

#### Regular Maintenance Tasks

1. **Log rotation**: Ensure log files don't fill disk space
2. **Database maintenance**: Regular VACUUM and ANALYZE
3. **Certificate renewal**: Update TLS certificates
4. **Security updates**: Keep base images updated
5. **Backup verification**: Test backup and restore procedures

#### Monitoring Checklist

- [ ] Service health endpoints responding
- [ ] Database connections healthy
- [ ] External service (AnythingLLM) accessible
- [ ] Disk space sufficient
- [ ] Memory usage within limits
- [ ] Error rates acceptable
- [ ] Response times acceptable

## Windows PowerShell Scripts

The deployment includes PowerShell scripts for Windows environments:

### Deploy.ps1
Kubernetes deployment script with the same functionality as the bash version:

```powershell
# Get help
.\scripts\Deploy.ps1 -Help

# Production deployment
.\scripts\Deploy.ps1 -Environment production -Registry gcr.io/my-project -ImageTag v1.0.0

# Dry run deployment
.\scripts\Deploy.ps1 -DryRun -Namespace anythingllm-dev
```

### Test-Health.ps1
Health check script for container and service health validation:

```powershell
# Get help
.\scripts\Test-Health.ps1 -Help

# Basic health check
.\scripts\Test-Health.ps1 -CheckType basic

# Readiness check with retries
.\scripts\Test-Health.ps1 -CheckType readiness -Retries 3 -Verbose
```

### Start-DockerCompose.ps1
Docker Compose management script for local development and testing:

```powershell
# Get help
.\scripts\Start-DockerCompose.ps1 -Help

# Start production environment
.\scripts\Start-DockerCompose.ps1 -Action up -Environment production

# View logs
.\scripts\Start-DockerCompose.ps1 -Action logs -Service anythingllm-api -Follow 50

# Stop services
.\scripts\Start-DockerCompose.ps1 -Action down -RemoveOrphans
```

### Script Features

- **Cross-platform compatibility**: PowerShell scripts work on Windows PowerShell 5.1+ and PowerShell Core 6+
- **Error handling**: Comprehensive error handling with cleanup
- **Logging**: Colored output with different log levels
- **Parameter validation**: Input validation and help documentation
- **Retry logic**: Built-in retry mechanisms for health checks
- **Dry run support**: Test deployments without making changes

For additional support, check the application logs and monitoring dashboards for detailed error information.