# Deployment Guide

## Docker Deployment

### Using Docker Compose (Recommended)

1. **Setup environment:**
```bash
cp .env.example .env
# Edit .env with production values
```

2. **Deploy with Docker Compose:**
```bash
docker-compose up -d
```

3. **Check status:**
```bash
docker-compose ps
docker-compose logs api
```

### Using Docker Only

1. **Build image:**
```bash
docker build -t anythingllm-api .
```

2. **Run container:**
```bash
docker run -d \
  --name anythingllm-api \
  -p 8000:8000 \
  --env-file .env \
  anythingllm-api
```

## Production Configuration

### Required Environment Variables
```bash
# Database (Required)
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname

# AnythingLLM Integration (Required)
ANYTHINGLLM_URL=https://your-anythingllm-instance.com
ANYTHINGLLM_API_KEY=your-production-api-key

# Security (Required)
SECRET_KEY=your-super-secure-secret-key-min-32-chars

# Server Configuration
HOST=0.0.0.0
PORT=8000
WORKERS=4

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_SANITIZE_SENSITIVE=true
```

### Optional Production Settings
```bash
# Redis (Recommended for production)
REDIS_ENABLED=true
REDIS_URL=redis://redis-host:6379/0

# S3 Storage (Recommended for production)
STORAGE_TYPE=s3
S3_BUCKET=your-production-bucket
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=1000
RATE_LIMIT_WINDOW=3600

# CORS (Restrict in production)
CORS_ORIGINS=https://your-frontend-domain.com,https://your-admin-domain.com
```

## Health Checks

The application provides health check endpoints:

- **Basic health:** `GET /api/v1/health`
- **Detailed health:** `GET /api/v1/health/detailed`

### Load Balancer Configuration
```nginx
# Nginx upstream configuration
upstream anythingllm_api {
    server api1:8000;
    server api2:8000;
}

server {
    listen 80;
    server_name your-api-domain.com;

    location /api/v1/health {
        proxy_pass http://anythingllm_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://anythingllm_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Monitoring

### Prometheus Metrics
The application exposes Prometheus metrics at `/metrics` endpoint.

### Log Aggregation
Structured JSON logs are written to stdout and can be collected by:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Fluentd
- AWS CloudWatch
- Google Cloud Logging

### Example Log Entry
```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "level": "INFO",
  "logger": "app.middleware.logging",
  "message": "Request completed",
  "correlation_id": "abc123-def456",
  "method": "POST",
  "url": "/api/v1/documents/upload",
  "status_code": 200,
  "process_time": 1.234
}
```

## Security Considerations

### Production Checklist
- [ ] Use strong `SECRET_KEY` (min 32 characters)
- [ ] Enable HTTPS with valid SSL certificates
- [ ] Restrict CORS origins to known domains
- [ ] Use environment variables for all secrets
- [ ] Enable rate limiting
- [ ] Use PostgreSQL with SSL
- [ ] Use Redis with authentication if enabled
- [ ] Regularly update dependencies
- [ ] Monitor security logs
- [ ] Use container scanning for vulnerabilities

### Database Security
```bash
# PostgreSQL connection with SSL
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db?ssl=require
```

### Redis Security
```bash
# Redis with authentication
REDIS_URL=redis://:password@host:6379/0
```

## Scaling

### Horizontal Scaling
- Run multiple API instances behind a load balancer
- Use Redis for shared session storage
- Use S3 for shared file storage
- Use PostgreSQL with connection pooling

### Vertical Scaling
- Increase `WORKERS` environment variable
- Increase database connection pool sizes
- Allocate more CPU/memory to containers

## Backup and Recovery

### Database Backups
```bash
# PostgreSQL backup
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql

# Automated backup script
#!/bin/bash
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump $DATABASE_URL | gzip > $BACKUP_DIR/anythingllm_api_$DATE.sql.gz
```

### File Storage Backups
- **S3**: Use S3 versioning and cross-region replication
- **Local**: Regular filesystem backups

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Check DATABASE_URL format
   - Verify PostgreSQL is accessible
   - Check firewall rules

2. **High Memory Usage**
   - Reduce database pool sizes
   - Decrease number of workers
   - Check for memory leaks in logs

3. **Slow Response Times**
   - Enable Redis caching
   - Optimize database queries
   - Check AnythingLLM response times

### Debug Commands
```bash
# Check container logs
docker-compose logs -f api

# Check database connectivity
docker-compose exec api python -c "import asyncio; from app.core.database import init_db; from app.core.config import get_settings; asyncio.run(init_db(get_settings()))"

# Check configuration
docker-compose exec api python -c "from app.core.config import get_settings; print(get_settings().dict())"
```