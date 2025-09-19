"""Test that all required packages can be imported."""

import sys

def test_imports():
    """Test that all critical packages can be imported."""
    
    try:
        # Core FastAPI imports
        import fastapi
        import uvicorn
        print("✅ FastAPI and Uvicorn")
        
        # Database imports
        import sqlalchemy
        import asyncpg
        import alembic
        print("✅ Database packages")
        
        # Configuration imports
        import pydantic
        import pydantic_settings
        print("✅ Pydantic packages")
        
        # HTTP client
        import httpx
        print("✅ HTTP client")
        
        # Security
        import jose
        import passlib
        print("✅ Security packages")
        
        # File processing
        import aiofiles
        print("✅ File processing")
        
        # Optional packages (may not be installed)
        try:
            import redis
            print("✅ Redis (optional)")
        except ImportError:
            print("⚠️  Redis not installed (optional)")
        
        try:
            import boto3
            print("✅ AWS SDK (optional)")
        except ImportError:
            print("⚠️  AWS SDK not installed (optional)")
        
        print("\n🎉 All critical packages can be imported!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)