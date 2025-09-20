# Health Monitoring and Metrics

This document describes the health monitoring and metrics collection system implemented for the AnythingLLM API service.

## Overview

The health monitoring system provides comprehensive observability into the API service's health and performance through:

- **Health Check Endpoints**: Basic and detailed health checks for service dependencies
- **Prometheus Metrics**: Comprehensive metrics collection for monitoring and alerting
- **System Resource Monitoring**: Real-time system resource utilization tracking
- **External Service Monitoring**: Health and performance tracking for external dependencies

## Health Check Endpoints

### Basic Health Check

**Endpoint**: `GET /api/v1/health/`

Returns a simple health status without checking dependencies. This endpoint is fast and suitable for basic liveness checks.

**Response**:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0"
}
```

### Detailed Health Check

**Endpoint**: `GET /api/v1/health/detailed`

Performs comprehensive health checks on all critical dependencies. This endpoint may take longer and is suitable for readiness checks.

**Response**:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "services": {
    "database": {
      "status": "healthy",
      "message": "Database connection successful",
      "response_time_ms": 15.2,
      "details": {
        "pool_size": 10,
        "checked_in": 8,
        "checked_out": 2,
        "overflow": 0,
        "invalid": 0
      }
    },
    "redis": {
      "status": "healthy",
      "message": "Redis connection successful",
      "response_time_ms": 5.1,
      "details": {
        "redis_version": "7.0.0",
        "connected_clients": 5,
        "used_memory": 1048576,
        "uptime_in_seconds": 3600
      }
    },
    "anythingllm": {
      "status": "healthy",
      "message": "AnythingLLM connection successful",
      "response_time_ms": 45.8,
      "details": {
        "status": "healthy",
        "version": "1.0.0"
      }
    }
  },
  "system": {
    "cpu_usage_percent": 25.5,
    "memory_usage_bytes": 1073741824,
    "memory_usage_percent": 50.0,
    "disk_usage_bytes": 10737418240,
    "disk_usage_percent": 75.0,
    "uptime_seconds": 3600.0
  }
}
```

**Health Status Values**:

- `healthy`: Service is fully operational
- `degraded`: Service is operational but has issues
- `unhealthy`: Service is not operational
- `disabled`: Service is not configured/enabled

### System Metrics

**Endpoint**: `GET /api/v1/health/system`

Returns current system resource utilization metrics.

**Response**:

```json
{
  "cpu_usage_percent": 25.5,
  "memory_usage_bytes": 1073741824,
  "memory_usage_percent": 50.0,
  "disk_usage_bytes": 10737418240,
  "disk_usage_percent": 75.0,
  "uptime_seconds": 3600.0
}
```

## Prometheus Metrics

### Metrics Endpoint

**Endpoint**: `GET /api/v1/health/metrics`

Returns metrics in Prometheus text format for scraping by monitoring systems.

**Content-Type**: `text/plain; version=0.0.4; charset=utf-8`

### Available Metrics

#### HTTP Request Metrics

- **`http_requests_total`**: Total number of HTTP requests
  - Labels: `method`, `endpoint`, `status_code`
- **`http_request_duration_seconds`**: HTTP request duration histogram
  - Labels: `method`, `endpoint`

#### Job Metrics

- **`jobs_total`**: Total number of jobs created
  - Labels: `job_type`, `status`
- **`job_duration_seconds`**: Job processing duration histogram
  - Labels: `job_type`
- **`active_jobs`**: Number of currently active jobs
  - Labels: `job_type`

#### External Service Metrics

- **`external_requests_total`**: Total external service requests
  - Labels: `service`, `endpoint`, `status`
- **`external_request_duration_seconds`**: External service request duration histogram
  - Labels: `service`, `endpoint`

#### Database Metrics

- **`db_connections_active`**: Active database connections
- **`db_query_duration_seconds`**: Database query duration histogram
  - Labels: `operation`

#### System Resource Metrics

- **`system_cpu_usage_percent`**: System CPU usage percentage
- **`system_memory_usage_bytes`**: System memory usage in bytes
- **`system_disk_usage_bytes`**: System disk usage in bytes
  - Labels: `path`

#### Application Info

- **`app_info`**: Application information
  - Labels: `version`, `environment`

### Example Metrics Output

```plaintext
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{endpoint="/api/v1/health",method="GET",status_code="200"} 1.0

# HELP http_request_duration_seconds HTTP request duration in seconds
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="0.005"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="0.01"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="0.025"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="0.05"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="0.075"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="0.1"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="0.25"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="0.5"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="0.75"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="1.0"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="2.5"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="5.0"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="7.5"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="10.0"} 1.0
http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET",le="+Inf"} 1.0
http_request_duration_seconds_count{endpoint="/api/v1/health",method="GET"} 1.0
http_request_duration_seconds_sum{endpoint="/api/v1/health",method="GET"} 0.1

# HELP system_cpu_usage_percent System CPU usage percentage
# TYPE system_cpu_usage_percent gauge
system_cpu_usage_percent 25.5

# HELP app_info Application information
# TYPE app_info info
app_info{environment="production",version="1.0.0"} 1.0
```

## Automatic Metrics Collection

### Middleware Integration

The `MetricsMiddleware` automatically collects HTTP request metrics for all API endpoints (excluding `/metrics` and `/health` by default).

**Features**:

- Automatic request/response time tracking
- HTTP status code recording
- Endpoint pattern extraction
- Error handling and recording

### Decorators

The system provides decorators for manual metrics collection:

#### `@track_external_request(service, endpoint)`

Tracks external service calls:

```python
from app.core.decorators import track_external_request

@track_external_request("anythingllm", "create_workspace")
async def create_workspace(self, name: str):
    # Implementation
    pass
```

#### `@track_database_query(operation)`

Tracks database query performance:

```python
from app.core.decorators import track_database_query

@track_database_query("select")
async def get_jobs(self, filters):
    # Implementation
    pass
```

#### `@track_job_lifecycle(job_type)`

Tracks job creation and completion:

```python
from app.core.decorators import track_job_lifecycle

@track_job_lifecycle("document_upload")
async def process_documents(self, files):
    # Implementation
    pass
```

## Configuration

### Environment Variables

No additional configuration is required for basic health monitoring. The system uses existing configuration from the main application settings.

### Metrics Collection

Metrics collection is enabled by default and integrated into the application startup process.

### Exclusions

By default, the following paths are excluded from HTTP metrics collection:

- `/metrics`
- `/health`

Additional paths can be excluded by configuring the `MetricsMiddleware`.

## Monitoring Integration

### Prometheus Setup

To scrape metrics with Prometheus, add the following job configuration:

```yaml
scrape_configs:
  - job_name: 'anythingllm-api'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/api/v1/health/metrics'
    scrape_interval: 15s
```

### Grafana Dashboard

Key metrics to monitor:

1. **Request Rate**: `rate(http_requests_total[5m])`
2. **Request Duration**: `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))`
3. **Error Rate**: `rate(http_requests_total{status_code=~"5.."}[5m])`
4. **Active Jobs**: `active_jobs`
5. **System Resources**: `system_cpu_usage_percent`, `system_memory_usage_bytes`

### Alerting Rules

Example Prometheus alerting rules:

```yaml
groups:
  - name: anythingllm-api
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status_code=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          
      - alert: HighResponseTime
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High response time detected"
          
      - alert: ServiceUnhealthy
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service is down"
```

## Troubleshooting

### Common Issues

1. **Metrics not appearing**: Check that the `/api/v1/health/metrics` endpoint is accessible
2. **High memory usage**: System metrics collection uses minimal resources, but check for memory leaks in application code
3. **Missing external service metrics**: Ensure decorators are applied to external service calls

### Debug Information

Enable debug logging to see metrics collection activity:

```python
import logging
logging.getLogger('app.core.metrics').setLevel(logging.DEBUG)
```

### Performance Impact

The metrics collection system is designed to have minimal performance impact:

- HTTP middleware adds ~1-2ms per request
- System metrics are collected only when requested
- Prometheus metrics are generated on-demand

## Dependencies

- **prometheus-client**: Prometheus metrics collection
- **psutil**: System resource monitoring
- **FastAPI**: Web framework integration
- **Pydantic**: Data validation and serialization
