#!/usr/bin/env python3
"""
Health check script for AnythingLLM API container
This script is used by Docker and Kubernetes health checks
"""

import sys
import requests
import json
import time
from typing import Dict, Any
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HealthChecker:
    def __init__(self, host: str = "localhost", port: int = 8000, timeout: int = 10):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"
    
    def check_basic_health(self) -> Dict[str, Any]:
        """Check basic health endpoint"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/health",
                timeout=self.timeout
            )
            response.raise_for_status()
            return {
                "status": "healthy",
                "response_time": response.elapsed.total_seconds(),
                "status_code": response.status_code,
                "data": response.json()
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    def check_detailed_health(self) -> Dict[str, Any]:
        """Check detailed health endpoint with dependencies"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/health/detailed",
                timeout=self.timeout
            )
            response.raise_for_status()
            return {
                "status": "healthy",
                "response_time": response.elapsed.total_seconds(),
                "status_code": response.status_code,
                "data": response.json()
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    def check_readiness(self) -> Dict[str, Any]:
        """Check if service is ready to accept traffic"""
        try:
            # Check basic health first
            basic_health = self.check_basic_health()
            if basic_health["status"] != "healthy":
                return basic_health
            
            # Check detailed health for dependencies
            detailed_health = self.check_detailed_health()
            if detailed_health["status"] != "healthy":
                return detailed_health
            
            # Check if all critical dependencies are healthy
            health_data = detailed_health["data"]
            if "dependencies" in health_data:
                for dep_name, dep_status in health_data["dependencies"].items():
                    if dep_status.get("status") != "healthy":
                        return {
                            "status": "not_ready",
                            "error": f"Dependency {dep_name} is not healthy",
                            "dependency_status": dep_status
                        }
            
            return {
                "status": "ready",
                "response_time": detailed_health["response_time"],
                "dependencies": health_data.get("dependencies", {})
            }
            
        except Exception as e:
            return {
                "status": "not_ready",
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    def check_liveness(self) -> Dict[str, Any]:
        """Check if service is alive (basic health check)"""
        return self.check_basic_health()

def main():
    """Main health check function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AnythingLLM API Health Checker")
    parser.add_argument("--host", default="localhost", help="Host to check")
    parser.add_argument("--port", type=int, default=8000, help="Port to check")
    parser.add_argument("--timeout", type=int, default=10, help="Request timeout in seconds")
    parser.add_argument("--check-type", choices=["liveness", "readiness", "basic", "detailed"], 
                       default="basic", help="Type of health check to perform")
    parser.add_argument("--retries", type=int, default=1, help="Number of retries")
    parser.add_argument("--retry-delay", type=int, default=1, help="Delay between retries in seconds")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    checker = HealthChecker(args.host, args.port, args.timeout)
    
    # Perform health check with retries
    for attempt in range(args.retries):
        if attempt > 0:
            logger.info(f"Retry attempt {attempt + 1}/{args.retries}")
            time.sleep(args.retry_delay)
        
        try:
            if args.check_type == "liveness":
                result = checker.check_liveness()
            elif args.check_type == "readiness":
                result = checker.check_readiness()
            elif args.check_type == "detailed":
                result = checker.check_detailed_health()
            else:  # basic
                result = checker.check_basic_health()
            
            # Output result
            if args.verbose:
                print(json.dumps(result, indent=2))
            else:
                print(f"Status: {result['status']}")
                if result["status"] in ["unhealthy", "not_ready"] and "error" in result:
                    print(f"Error: {result['error']}")
            
            # Exit with appropriate code
            if result["status"] in ["healthy", "ready"]:
                logger.info("Health check passed")
                sys.exit(0)
            else:
                logger.error(f"Health check failed: {result.get('error', 'Unknown error')}")
                if attempt == args.retries - 1:  # Last attempt
                    sys.exit(1)
                    
        except Exception as e:
            logger.error(f"Health check error: {e}")
            if attempt == args.retries - 1:  # Last attempt
                sys.exit(1)

if __name__ == "__main__":
    main()