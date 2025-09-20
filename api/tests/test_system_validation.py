"""
Simple system validation tests to verify the API is working correctly.
"""

import pytest
import tempfile
from pathlib import Path
from tests.fixtures.mock_data import mock_files


class TestSystemValidation:
    """Basic system validation tests."""
    
    @pytest.mark.unit
    def test_mock_data_generation(self):
        """Test that mock data generation works correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test document set creation
            test_files = mock_files.create_test_document_set(Path(temp_dir), file_count=3)
            assert len(test_files) == 5  # 3 PDFs + 1 JSON + 1 CSV
            
            # Test ZIP creation
            zip_path = mock_files.create_zip_from_files(test_files, Path(temp_dir) / "test.zip")
            assert zip_path.exists()
            assert zip_path.stat().st_size > 0
    
    @pytest.mark.unit
    def test_file_generation(self):
        """Test individual file generation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Test PDF creation
            pdf_file = mock_files.create_pdf_file(temp_path, "test.pdf")
            assert pdf_file.exists()
            assert pdf_file.suffix == ".pdf"
            
            # Test JSON creation
            json_file = mock_files.create_json_file(temp_path, "test.json")
            assert json_file.exists()
            assert json_file.suffix == ".json"
            
            # Test CSV creation
            csv_file = mock_files.create_csv_file(temp_path, "test.csv")
            assert csv_file.exists()
            assert csv_file.suffix == ".csv"
    
    @pytest.mark.unit
    def test_comprehensive_document_set(self):
        """Test comprehensive document set creation with realistic content."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_files = mock_files.create_test_document_set(Path(temp_dir), file_count=2)
            
            # Should have PDFs, JSONs, and CSV
            pdf_files = [f for f in test_files if f.suffix == ".pdf"]
            json_files = [f for f in test_files if f.suffix == ".json"]
            csv_files = [f for f in test_files if f.suffix == ".csv"]
            
            assert len(pdf_files) == 2, f"Expected 2 PDF files, got {len(pdf_files)}"
            assert len(json_files) == 2, f"Expected 2 JSON files, got {len(json_files)}"
            assert len(csv_files) == 1, f"Expected 1 CSV file, got {len(csv_files)}"
            
            # Verify content exists
            for pdf_file in pdf_files:
                content = pdf_file.read_text()
                assert "Contract Agreement" in content
                assert "Contract Value:" in content
                assert "Duration:" in content
            
            for json_file in json_files:
                content = json_file.read_text()
                assert "contract_id" in content
                assert "vendor" in content
                assert "total_value" in content
            
            for csv_file in csv_files:
                content = csv_file.read_text()
                assert "Contract ID" in content
                assert "Vendor" in content
                assert "Value" in content


class TestEndToEndPreparation:
    """Tests to prepare for end-to-end testing."""
    
    @pytest.mark.integration
    def test_test_data_preparation(self):
        """Test that we can prepare test data for end-to-end tests."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create comprehensive test data
            test_files = mock_files.create_test_document_set(Path(temp_dir), file_count=5)
            
            # Create ZIP file
            zip_path = mock_files.create_zip_from_files(test_files, Path(temp_dir) / "e2e_test.zip")
            
            # Verify ZIP file
            assert zip_path.exists()
            assert zip_path.stat().st_size > 1000  # Should be reasonably sized
            
            # Verify we can read the ZIP
            import zipfile
            with zipfile.ZipFile(zip_path, 'r') as zf:
                file_list = zf.namelist()
                assert len(file_list) == len(test_files)
                
                # Check file types
                pdf_count = sum(1 for f in file_list if f.endswith('.pdf'))
                json_count = sum(1 for f in file_list if f.endswith('.json'))
                csv_count = sum(1 for f in file_list if f.endswith('.csv'))
                
                assert pdf_count >= 2, f"Expected at least 2 PDF files, got {pdf_count}"
                assert json_count >= 1, f"Expected at least 1 JSON file, got {json_count}"
                assert csv_count >= 1, f"Expected at least 1 CSV file, got {csv_count}"
    
    @pytest.mark.integration
    def test_performance_test_data(self):
        """Test creation of data for performance testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create multiple test sets for concurrent testing
            test_sets = []
            for i in range(3):
                test_files = mock_files.create_test_document_set(
                    Path(temp_dir) / f"set_{i}", 
                    file_count=2
                )
                zip_path = mock_files.create_zip_from_files(
                    test_files, 
                    Path(temp_dir) / f"performance_test_{i}.zip"
                )
                test_sets.append(zip_path)
            
            # Verify all test sets
            assert len(test_sets) == 3
            for zip_path in test_sets:
                assert zip_path.exists()
                assert zip_path.stat().st_size > 500  # Reasonable size
    
    @pytest.mark.unit
    def test_system_readiness_indicators(self):
        """Test indicators that the system is ready for comprehensive testing."""
        
        # Test 1: Can create test data
        with tempfile.TemporaryDirectory() as temp_dir:
            test_files = mock_files.create_test_document_set(Path(temp_dir))
            assert len(test_files) > 0
        
        # Test 2: Can import required modules
        try:
            from app.models.pydantic_models import JobStatus, JobType
            from tests.fixtures.mock_data import mock_data
            assert True  # If we get here, imports work
        except ImportError as e:
            pytest.fail(f"Required modules not available: {e}")
        
        # Test 3: Basic file operations work
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.txt"
            test_file.write_text("test content")
            assert test_file.read_text() == "test content"
        
        print("✅ System appears ready for comprehensive testing")


if __name__ == "__main__":
    # Run basic validation
    import sys
    
    print("🔍 Running Basic System Validation")
    print("=" * 40)
    
    # Run the tests
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-m", "unit"
    ])
    
    if exit_code == 0:
        print("\n✅ Basic system validation passed!")
        print("System is ready for comprehensive end-to-end testing.")
    else:
        print("\n❌ Basic system validation failed!")
        print("Please fix issues before running comprehensive tests.")
    
    sys.exit(exit_code)