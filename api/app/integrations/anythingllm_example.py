"""Example usage of AnythingLLM integration client."""

import asyncio
import os
from pathlib import Path
from typing import List

from app.core.config import Settings
from app.integrations.anythingllm_client import (
    AnythingLLMClient,
    create_anythingllm_client,
    AnythingLLMError,
    WorkspaceNotFoundError,
    DocumentUploadError
)


async def example_workspace_management():
    """Example of workspace management operations."""
    print("=== Workspace Management Example ===")
    
    # Set up environment variables (in production, these would be in .env file)
    os.environ.update({
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
        "ANYTHINGLLM_URL": "http://localhost:3001",
        "ANYTHINGLLM_API_KEY": "your-api-key-here",
        "SECRET_KEY": "your-secret-key"
    })
    
    settings = Settings()
    
    # Create client using factory function
    client = create_anythingllm_client(settings)
    
    try:
        async with client:
            # Health check
            print("1. Performing health check...")
            health = await client.health_check()
            print(f"   Health status: {health.status}")
            
            # List existing workspaces
            print("2. Listing existing workspaces...")
            workspaces = await client.get_workspaces()
            print(f"   Found {len(workspaces)} workspaces")
            for ws in workspaces:
                print(f"   - {ws.name} (ID: {ws.id})")
            
            # Create a new workspace
            print("3. Creating new workspace...")
            workspace_config = {
                "openAiTemp": 0.7,
                "chatProvider": "openai",
                "chatModel": "gpt-3.5-turbo"
            }
            
            new_workspace = await client.create_workspace(
                "Procurement Analysis Workspace",
                workspace_config
            )
            print(f"   Created workspace: {new_workspace.workspace.name}")
            print(f"   Workspace ID: {new_workspace.workspace.id}")
            
            # Find workspace by name
            print("4. Finding workspace by name...")
            found_workspace = await client.find_workspace_by_name("Procurement Analysis Workspace")
            if found_workspace:
                print(f"   Found workspace: {found_workspace.name}")
            else:
                print("   Workspace not found")
            
            # Get specific workspace
            print("5. Getting workspace details...")
            workspace_details = await client.get_workspace(new_workspace.workspace.id)
            print(f"   Workspace: {workspace_details.name}")
            print(f"   Created: {workspace_details.createdAt}")
            
    except AnythingLLMError as e:
        print(f"AnythingLLM error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


async def example_document_upload():
    """Example of document upload operations."""
    print("\n=== Document Upload Example ===")
    
    settings = Settings()
    client = create_anythingllm_client(settings)
    
    try:
        async with client:
            # Assume we have a workspace ID from previous example
            workspace_id = "ws_example_123"
            
            # Create some example files (in practice, these would be real files)
            print("1. Preparing documents for upload...")
            
            # In a real scenario, you would have actual files
            example_files = [
                Path("contract_001.pdf"),
                Path("procurement_spec.json"),
                Path("vendor_data.csv")
            ]
            
            # Filter to only existing files
            existing_files = [f for f in example_files if f.exists()]
            
            if existing_files:
                print(f"   Found {len(existing_files)} files to upload")
                
                # Upload documents
                print("2. Uploading documents...")
                upload_result = await client.upload_documents(workspace_id, existing_files)
                
                if upload_result.success:
                    print(f"   Successfully uploaded {len(upload_result.files)} files")
                    for file_info in upload_result.files:
                        print(f"   - {file_info.get('name', 'Unknown')}: {file_info.get('status', 'Unknown')}")
                else:
                    print(f"   Upload failed: {upload_result.message}")
            else:
                print("   No files found for upload (this is expected in the example)")
                
    except DocumentUploadError as e:
        print(f"Document upload error: {e}")
    except AnythingLLMError as e:
        print(f"AnythingLLM error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


async def example_question_processing():
    """Example of question processing operations."""
    print("\n=== Question Processing Example ===")
    
    settings = Settings()
    client = create_anythingllm_client(settings)
    
    try:
        async with client:
            workspace_id = "ws_example_123"
            
            # Create a thread for questions
            print("1. Creating thread for questions...")
            thread_response = await client.create_thread(
                workspace_id,
                "Procurement Analysis Thread"
            )
            thread_id = thread_response.thread.id
            print(f"   Created thread: {thread_id}")
            
            # Send questions to the thread
            questions = [
                "What is the total contract value mentioned in the documents?",
                "Who are the main contractors listed?",
                "What are the key deliverables outlined in the procurement specification?",
                "Are there any compliance requirements mentioned?"
            ]
            
            print("2. Processing questions...")
            for i, question in enumerate(questions, 1):
                print(f"   Question {i}: {question}")
                
                try:
                    response = await client.send_message(
                        workspace_id,
                        thread_id,
                        question
                    )
                    
                    print(f"   Answer: {response.response[:100]}...")
                    if response.sources:
                        print(f"   Sources: {len(response.sources)} documents referenced")
                        
                except Exception as e:
                    print(f"   Error processing question: {e}")
                
                # Small delay between questions
                await asyncio.sleep(1)
                
    except AnythingLLMError as e:
        print(f"AnythingLLM error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


async def example_error_handling():
    """Example of error handling and resilience features."""
    print("\n=== Error Handling Example ===")
    
    # Create client with invalid URL to demonstrate error handling
    os.environ["ANYTHINGLLM_URL"] = "http://invalid-url:9999"
    settings = Settings()
    client = create_anythingllm_client(settings)
    
    try:
        async with client:
            print("1. Testing connection to invalid URL...")
            
            # This should trigger the circuit breaker after several failures
            for attempt in range(7):  # More than circuit breaker threshold
                try:
                    await client.get_workspaces()
                    print(f"   Attempt {attempt + 1}: Success")
                    break
                except AnythingLLMError as e:
                    print(f"   Attempt {attempt + 1}: Failed - {e}")
                    
                    # Check circuit breaker state
                    if "Circuit breaker is OPEN" in str(e):
                        print("   Circuit breaker opened - protecting against further failures")
                        break
                        
    except Exception as e:
        print(f"Final error: {e}")
    
    print("   Error handling demonstration complete")


async def main():
    """Run all examples."""
    print("AnythingLLM Integration Client Examples")
    print("=" * 50)
    
    # Note: These examples assume you have a running AnythingLLM instance
    # and proper configuration. In a real environment, you would set up
    # proper environment variables or configuration files.
    
    print("Note: These examples require a running AnythingLLM instance")
    print("and proper configuration. Errors are expected in this demo environment.\n")
    
    await example_workspace_management()
    await example_document_upload()
    await example_question_processing()
    await example_error_handling()
    
    print("\n" + "=" * 50)
    print("Examples completed!")


if __name__ == "__main__":
    asyncio.run(main())