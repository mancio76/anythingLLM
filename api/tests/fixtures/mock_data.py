"""Mock data generators for testing."""

import json
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from app.models.pydantic_models import (
    Job,
    JobStatus,
    JobType,
    LLMConfig,
    LLMProvider,
    Question,
    QuestionResult,
    Workspace,
    WorkspaceConfig,
    WorkspaceStatus,
)


class MockDataGenerator:
    """Generate mock data for testing."""

    @staticmethod
    def create_mock_job(
        job_id: Optional[str] = None,
        job_type: JobType = JobType.DOCUMENT_UPLOAD,
        status: JobStatus = JobStatus.PENDING,
        workspace_id: Optional[str] = None,
        progress: float = 0.0,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ) -> Job:
        """Create a mock job."""
        return Job(
            id=job_id or f"job_{uuid4().hex[:8]}",
            type=job_type,
            status=status,
            workspace_id=workspace_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            started_at=datetime.utcnow() if status != JobStatus.PENDING else None,
            completed_at=datetime.utcnow() if status in [JobStatus.COMPLETED, JobStatus.FAILED] else None,
            progress=progress,
            result=result,
            error=error,
            metadata={"test": True, "created_by": "test_suite"},
        )

    @staticmethod
    def create_mock_workspace(
        workspace_id: Optional[str] = None,
        name: Optional[str] = None,
        status: WorkspaceStatus = WorkspaceStatus.ACTIVE,
        document_count: int = 0,
    ) -> Workspace:
        """Create a mock workspace."""
        workspace_name = name or f"Test Workspace {uuid4().hex[:8]}"
        return Workspace(
            id=workspace_id or f"ws_{uuid4().hex[:8]}",
            name=workspace_name,
            slug=workspace_name.lower().replace(" ", "-"),
            description=f"Test workspace for {workspace_name}",
            config=WorkspaceConfig(
                llm_config=LLMConfig(
                    provider=LLMProvider.OPENAI,
                    model="gpt-3.5-turbo",
                    temperature=0.7,
                    max_tokens=1000,
                    timeout=30,
                ),
                procurement_prompts=True,
                auto_embed=True,
                max_documents=100,
            ),
            document_count=document_count,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            status=status,
        )

    @staticmethod
    def create_mock_question(
        question_id: Optional[str] = None,
        text: Optional[str] = None,
        expected_fragments: Optional[List[str]] = None,
    ) -> Question:
        """Create a mock question."""
        return Question(
            id=question_id or f"q_{uuid4().hex[:8]}",
            text=text or "What is the contract value?",
            expected_fragments=expected_fragments or ["$", "value", "amount"],
            llm_config=LLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-3.5-turbo",
                temperature=0.7,
                max_tokens=500,
                timeout=30,
            ),
        )

    @staticmethod
    def create_mock_question_result(
        question_id: Optional[str] = None,
        question_text: Optional[str] = None,
        response: Optional[str] = None,
        confidence_score: float = 0.85,
        success: bool = True,
    ) -> QuestionResult:
        """Create a mock question result."""
        return QuestionResult(
            question_id=question_id or f"q_{uuid4().hex[:8]}",
            question_text=question_text or "What is the contract value?",
            response=response or "The contract value is $100,000.",
            confidence_score=confidence_score,
            processing_time=1.5,
            fragments_found=["$", "value"] if success else [],
            success=success,
        )

    @staticmethod
    def create_test_zip_file(
        temp_dir: Path,
        filename: str = "test_documents.zip",
        include_pdf: bool = True,
        include_json: bool = True,
        include_csv: bool = True,
        include_invalid: bool = False,
    ) -> Path:
        """Create a test ZIP file with various document types."""
        zip_path = temp_dir / filename
        
        with zipfile.ZipFile(zip_path, 'w') as zip_file:
            if include_pdf:
                # Create a mock PDF (just text for testing)
                pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
                zip_file.writestr("contract.pdf", pdf_content)
            
            if include_json:
                json_content = json.dumps({
                    "contract_id": "C001",
                    "vendor": "Test Vendor",
                    "value": 100000,
                    "terms": ["30 days payment", "1 year warranty"]
                }, indent=2)
                zip_file.writestr("contract_data.json", json_content)
            
            if include_csv:
                csv_content = "id,name,value,date\n1,Contract A,50000,2024-01-01\n2,Contract B,75000,2024-01-15"
                zip_file.writestr("contracts.csv", csv_content)
            
            if include_invalid:
                # Add an invalid file type
                zip_file.writestr("invalid.txt", "This is not allowed")
                zip_file.writestr("malware.exe", b"fake executable")
        
        return zip_path

    @staticmethod
    def create_sample_questions() -> List[Question]:
        """Create a list of sample questions for testing."""
        return [
            Question(
                id="q1",
                text="What is the total contract value?",
                expected_fragments=["$", "total", "value", "amount"],
            ),
            Question(
                id="q2", 
                text="Who is the vendor or supplier?",
                expected_fragments=["vendor", "supplier", "company"],
            ),
            Question(
                id="q3",
                text="What are the payment terms?",
                expected_fragments=["payment", "terms", "days", "net"],
            ),
            Question(
                id="q4",
                text="What is the contract duration?",
                expected_fragments=["duration", "term", "year", "month"],
            ),
            Question(
                id="q5",
                text="Are there any penalties or liquidated damages?",
                expected_fragments=["penalty", "liquidated", "damages", "fine"],
            ),
        ]

    @staticmethod
    def create_large_question_set(count: int = 50) -> List[Question]:
        """Create a large set of questions for performance testing."""
        questions = []
        question_templates = [
            "What is the {field} in the contract?",
            "Who is responsible for {field}?",
            "What are the {field} requirements?",
            "When is the {field} due?",
            "How much is the {field} cost?",
        ]
        
        fields = [
            "delivery", "payment", "warranty", "maintenance", "support",
            "insurance", "liability", "termination", "renewal", "compliance",
            "quality", "performance", "security", "confidentiality", "intellectual property"
        ]
        
        for i in range(count):
            template = question_templates[i % len(question_templates)]
            field = fields[i % len(fields)]
            text = template.format(field=field)
            
            questions.append(Question(
                id=f"perf_q_{i+1}",
                text=text,
                expected_fragments=[field, "contract", "document"],
            ))
        
        return questions

    @staticmethod
    def create_mock_anythingllm_responses() -> Dict[str, Dict]:
        """Create mock responses from AnythingLLM API."""
        return {
            "workspace_create": {
                "workspace": {
                    "id": "ws_123456",
                    "name": "Test Workspace",
                    "slug": "test-workspace",
                    "createdAt": "2024-01-01T00:00:00Z",
                    "updatedAt": "2024-01-01T00:00:00Z",
                }
            },
            "workspace_list": {
                "workspaces": [
                    {
                        "id": "ws_123456",
                        "name": "Test Workspace",
                        "slug": "test-workspace",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "updatedAt": "2024-01-01T00:00:00Z",
                    }
                ]
            },
            "document_upload": {
                "success": True,
                "message": "Documents uploaded successfully",
                "documents": [
                    {"filename": "contract.pdf", "status": "uploaded"},
                    {"filename": "contract_data.json", "status": "uploaded"},
                ]
            },
            "thread_create": {
                "thread": {
                    "id": "thread_789012",
                    "name": "Test Thread",
                    "workspace_id": "ws_123456",
                    "createdAt": "2024-01-01T00:00:00Z",
                }
            },
            "message_send": {
                "response": "The contract value is $100,000 as specified in section 3.1.",
                "sources": [
                    {"filename": "contract.pdf", "page": 3},
                    {"filename": "contract_data.json", "field": "value"},
                ],
                "processing_time": 1.2,
            },
        }


class MockFileGenerator:
    """Generate mock files for testing."""

    @staticmethod
    def create_temp_directory() -> Path:
        """Create a temporary directory for testing."""
        return Path(tempfile.mkdtemp())

    @staticmethod
    def create_pdf_file(path: Path, filename: str = "test.pdf") -> Path:
        """Create a mock PDF file."""
        pdf_path = path / filename
        # Simple PDF header for testing
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        pdf_path.write_bytes(pdf_content)
        return pdf_path

    @staticmethod
    def create_json_file(path: Path, filename: str = "test.json", data: Optional[Dict] = None) -> Path:
        """Create a JSON file."""
        json_path = path / filename
        test_data = data or {
            "contract_id": "TEST001",
            "vendor": "Test Vendor Inc.",
            "value": 250000,
            "currency": "USD",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "terms": {
                "payment": "Net 30",
                "warranty": "1 year",
                "delivery": "FOB destination"
            }
        }
        json_path.write_text(json.dumps(test_data, indent=2))
        return json_path

    @staticmethod
    def create_csv_file(path: Path, filename: str = "test.csv") -> Path:
        """Create a CSV file."""
        csv_path = path / filename
        csv_content = """id,vendor,value,date,status
1,Vendor A,100000,2024-01-01,active
2,Vendor B,150000,2024-01-15,pending
3,Vendor C,200000,2024-02-01,completed
4,Vendor D,75000,2024-02-15,active
5,Vendor E,300000,2024-03-01,pending"""
        csv_path.write_text(csv_content)
        return csv_path

    @staticmethod
    def create_invalid_file(path: Path, filename: str = "invalid.txt") -> Path:
        """Create an invalid file type."""
        invalid_path = path / filename
        invalid_path.write_text("This is an invalid file type for the system.")
        return invalid_path

    @staticmethod
    def create_large_file(path: Path, filename: str = "large.pdf", size_mb: int = 10) -> Path:
        """Create a large file for testing size limits."""
        large_path = path / filename
        # Create a file with specified size in MB
        content = b"0" * (size_mb * 1024 * 1024)
        large_path.write_bytes(content)
        return large_path
    
    @staticmethod
    def create_test_document_set(directory: Path, file_count: int = 5) -> List[Path]:
        """Create a set of test documents for comprehensive testing."""
        # Ensure directory exists
        directory.mkdir(parents=True, exist_ok=True)
        
        files = []
        
        # Create PDF files with procurement content
        for i in range(file_count):
            pdf_content = f"""Contract Agreement #{i+1}
            
This is a sample procurement contract document for testing purposes.

Contract Details:
- Contract Value: ${(i+1) * 100000}
- Duration: {12 + i} months
- Contractor: Test Company {i+1}
- Client: Government Agency
- Start Date: 2024-01-{i+1:02d}
- End Date: 2024-12-{i+1:02d}

Terms and Conditions:
1. Payment terms: Net 30 days
2. Deliverables: Software development services
3. Performance metrics: 99.9% uptime
4. Penalties: 1% per day for delays

This document contains confidential information and should be handled accordingly.
"""
            pdf_file = MockFileGenerator.create_pdf_with_content(directory, f"contract_{i+1}.pdf", pdf_content)
            files.append(pdf_file)
        
        # Create JSON files with structured data (only create 2 regardless of file_count)
        json_count = min(2, max(1, file_count // 3))  # At least 1, at most 2
        for i in range(json_count):
            json_data = {
                "contract_id": f"CONTRACT_{i+1:03d}",
                "vendor": f"Vendor Company {i+1}",
                "total_value": (i+1) * 250000,
                "currency": "USD",
                "duration_months": 24 + i,
                "status": "active",
                "key_personnel": [
                    {"name": f"John Doe {i+1}", "role": "Project Manager"},
                    {"name": f"Jane Smith {i+1}", "role": "Technical Lead"}
                ],
                "milestones": [
                    {"name": "Phase 1", "due_date": "2024-03-01", "value": (i+1) * 50000},
                    {"name": "Phase 2", "due_date": "2024-06-01", "value": (i+1) * 75000},
                    {"name": "Phase 3", "due_date": "2024-09-01", "value": (i+1) * 125000}
                ]
            }
            json_file = MockFileGenerator.create_json_file(directory, f"contract_data_{i+1}.json", json_data)
            files.append(json_file)
        
        # Create CSV file with tabular data (always create 1)
        csv_data = [
            ["Contract ID", "Vendor", "Value", "Start Date", "End Date", "Status"],
            ["CNT001", "Alpha Corp", "500000", "2024-01-01", "2024-12-31", "Active"],
            ["CNT002", "Beta LLC", "750000", "2024-02-01", "2025-01-31", "Active"],
            ["CNT003", "Gamma Inc", "300000", "2024-03-01", "2024-08-31", "Completed"],
            ["CNT004", "Delta Solutions", "1000000", "2024-04-01", "2025-03-31", "Active"],
        ]
        csv_file = MockFileGenerator.create_csv_file_with_data(directory, "contracts_summary.csv", csv_data)
        files.append(csv_file)
        
        return files
    
    @staticmethod
    def create_pdf_with_content(directory: Path, filename: str, content: str) -> Path:
        """Create a PDF file with specific text content."""
        file_path = directory / filename
        # For testing purposes, we'll create a simple text file with .pdf extension
        # In a real implementation, you'd use a PDF library like reportlab
        file_path.write_text(content, encoding='utf-8')
        return file_path
    
    @staticmethod
    def create_csv_file_with_data(directory: Path, filename: str, data: List[List[str]]) -> Path:
        """Create a CSV file with specific data."""
        file_path = directory / filename
        csv_content = "\n".join([",".join(row) for row in data])
        file_path.write_text(csv_content, encoding='utf-8')
        return file_path
    
    @staticmethod
    def create_zip_from_files(files: List[Path], zip_path: Path) -> Path:
        """Create a ZIP file containing the specified files."""
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in files:
                zipf.write(file_path, file_path.name)
        return zip_path


# Convenience instances
mock_data = MockDataGenerator()
mock_files = MockFileGenerator()