import pytest
import tempfile
import os
from pathlib import Path


def test_basic_import(cime_available):
    """Test that we can import our modules."""
    if not cime_available:
        pytest.skip("CIME not available, skipping buildnml import test")
    
    try:
        # Try to import buildnml functions by executing the script
        import importlib.util
        buildnml_path = Path(__file__).parent.parent.parent / "cime_config" / "buildnml"
        spec = importlib.util.spec_from_file_location("buildnml_test", buildnml_path)
        buildnml_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(buildnml_module)
        
        # Check that key functions exist
        assert hasattr(buildnml_module, 'buildnml')
        
    except ImportError as e:
        pytest.fail(f"Failed to import buildnml with CIME available: {e}")


@pytest.mark.skipif(not pytest.importorskip("CIME", reason="CIME not available"), reason="CIME required")
class TestCIMEIntegration:
    """Tests that require CIME to be available."""
    
    def test_buildnml_with_cime(self):
        """Test buildnml function with mocked CIME case."""
        pytest.skip("CIME integration test - implement when CIME environment available")