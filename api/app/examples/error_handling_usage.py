"""Examples of how to use the error handling and resilience systems."""

import asyncio
from typing import Dict, Any

from app.core.exceptions import (
    ValidationError,
    ExternalServiceError,
    ProcessingError,
)
from app.core.circuit_breaker import get_circuit_breaker, CircuitBreakerConfig
from app.core.retry import retry_async, RetryConfig
from app.core.error_tracking import get_error_tracker
from app.core.graceful_degradation import check_service_availability
from app.core.validation import InputValidator, validate_and_raise


class ExampleService:
    """Example service demonstrating error handling patterns."""
    
    def __init__(self):
        self.error_tracker = get_error_tracker()
        
        # Configure circuit breaker for external service
        self.circuit_breaker = get_circuit_breaker(
            "external_api",
            CircuitBreakerConfig(
                failure_threshold=3,
                timeout=60,
                success_threshold=2
            )
        )
        
        # Configure retry policy
        self.retry_config = RetryConfig(
            max_retries=3,
            base_delay=1.0,
            max_delay=30.0,
            exponential_base=2.0,
            jitter=True
        )
    
    async def process_user_input(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Example of input validation with detailed error messages."""
        try:
            # Check service availability first
            await check_service_availability("upload")
            
            # Validate required fields
            username = user_data.get("username", "")
            email = user_data.get("email", "")
            age = user_data.get("age")
            
            # Validate username
            username_result = InputValidator.validate_string(
                username, "username", min_length=3, max_length=50
            )
            validate_and_raise(username_result, "username")
            
            # Validate email
            email_result = InputValidator.validate_email(email, "email")
            validate_and_raise(email_result, "email")
            
            # Validate age
            age_result = InputValidator.validate_integer(
                age, "age", min_value=18, max_value=120
            )
            validate_and_raise(age_result, "age")
            
            # Log successful validation
            self.error_tracker.log_info(
                "User input validation successful",
                context={"username": username, "email": email}
            )
            
            return {
                "status": "valid",
                "username": username,
                "email": email,
                "age": age
            }
            
        except ValidationError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            # Log unexpected errors
            self.error_tracker.log_error(
                e,
                context={"operation": "process_user_input", "user_data": user_data}
            )
            raise ProcessingError(
                message="Failed to process user input",
                stage="validation"
            )
    
    async def call_external_service(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Example of external service call with circuit breaker and retry."""
        try:
            # Use circuit breaker to protect against cascading failures
            result = await self.circuit_breaker.call(
                self._make_external_call_with_retry,
                data
            )
            
            self.error_tracker.log_info(
                "External service call successful",
                context={"data_size": len(str(data))}
            )
            
            return result
            
        except Exception as e:
            self.error_tracker.log_error(
                e,
                context={
                    "operation": "call_external_service",
                    "circuit_breaker_state": self.circuit_breaker.state.value
                }
            )
            
            if "circuit breaker" in str(e).lower():
                raise ExternalServiceError(
                    service="external_api",
                    message="Service temporarily unavailable due to circuit breaker"
                )
            else:
                raise ExternalServiceError(
                    service="external_api",
                    message=f"External service call failed: {str(e)}"
                )
    
    async def _make_external_call_with_retry(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make external call with retry logic."""
        return await retry_async(
            self._simulate_external_call,
            data,
            config=self.retry_config,
            correlation_id=self.error_tracker.get_correlation_id()
        )
    
    async def _simulate_external_call(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate an external service call that might fail."""
        import random
        
        # Simulate random failures for demonstration
        if random.random() < 0.3:  # 30% failure rate
            raise ConnectionError("Simulated connection failure")
        
        # Simulate processing delay
        await asyncio.sleep(0.1)
        
        return {
            "status": "success",
            "processed_data": data,
            "timestamp": "2024-01-01T00:00:00Z"
        }
    
    async def process_file_upload(self, filename: str, file_size: int) -> Dict[str, Any]:
        """Example of file processing with validation and error handling."""
        try:
            # Check service availability for upload operations
            await check_service_availability("upload")
            
            # Validate file type
            allowed_types = ["pdf", "json", "csv"]
            file_type_result = InputValidator.validate_file_type(
                filename, allowed_types, "file"
            )
            validate_and_raise(file_type_result, "filename")
            
            # Validate file size (100MB limit)
            max_size = 100 * 1024 * 1024
            file_size_result = InputValidator.validate_file_size(
                file_size, max_size, "file"
            )
            validate_and_raise(file_size_result, "file_size")
            
            # Process the file (simulate)
            await asyncio.sleep(0.1)
            
            self.error_tracker.log_info(
                "File upload processed successfully",
                context={
                    "filename": filename,
                    "file_size": file_size,
                    "file_type": filename.split('.')[-1].lower()
                }
            )
            
            return {
                "status": "processed",
                "filename": filename,
                "file_size": file_size,
                "processing_time": 0.1
            }
            
        except ValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            self.error_tracker.log_error(
                e,
                context={
                    "operation": "process_file_upload",
                    "filename": filename,
                    "file_size": file_size
                }
            )
            raise ProcessingError(
                message="File upload processing failed",
                stage="file_processing"
            )


# Example usage
async def main():
    """Demonstrate error handling usage."""
    service = ExampleService()
    
    print("=== Error Handling Examples ===\n")
    
    # Example 1: Valid input
    print("1. Processing valid user input:")
    try:
        result = await service.process_user_input({
            "username": "john_doe",
            "email": "john@example.com",
            "age": 25
        })
        print(f"   Success: {result}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Example 2: Invalid input
    print("\n2. Processing invalid user input:")
    try:
        result = await service.process_user_input({
            "username": "jo",  # Too short
            "email": "invalid-email",  # Invalid format
            "age": 15  # Too young
        })
        print(f"   Success: {result}")
    except ValidationError as e:
        print(f"   Validation Error: {e.message}")
        print(f"   Details: {e.details}")
    
    # Example 3: External service call
    print("\n3. Calling external service:")
    try:
        result = await service.call_external_service({"key": "value"})
        print(f"   Success: {result}")
    except ExternalServiceError as e:
        print(f"   External Service Error: {e.message}")
    
    # Example 4: File upload validation
    print("\n4. Processing file upload:")
    try:
        result = await service.process_file_upload("document.pdf", 1024 * 1024)  # 1MB
        print(f"   Success: {result}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Example 5: Invalid file upload
    print("\n5. Processing invalid file upload:")
    try:
        result = await service.process_file_upload("document.txt", 200 * 1024 * 1024)  # 200MB
        print(f"   Success: {result}")
    except ValidationError as e:
        print(f"   Validation Error: {e.message}")


if __name__ == "__main__":
    asyncio.run(main())