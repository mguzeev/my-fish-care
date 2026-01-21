"""
Test admin LLM model vision/text capabilities configuration
"""
import pytest
from app.models.llm_model import LLMModel


def test_llm_model_has_vision_text_fields():
    """Test that LLMModel has supports_text and supports_vision fields"""
    model = LLMModel(
        name="test-model",
        display_name="Test Model",
        provider="openai",
        api_key="test-key",
        max_tokens_limit=4000,
        context_window=8000,
        supports_text=True,
        supports_vision=False
    )
    
    assert hasattr(model, 'supports_text')
    assert hasattr(model, 'supports_vision')
    assert model.supports_text is True
    assert model.supports_vision is False


def test_llm_model_defaults():
    """Test that LLMModel fields have correct defaults when provided"""
    model = LLMModel(
        name="test-model-2",
        display_name="Test Model 2",
        provider="openai",
        api_key="test-key",
        max_tokens_limit=4000,
        context_window=8000,
        supports_text=True,
        supports_vision=False
    )
    
    # Check values are set correctly
    assert model.supports_text is True
    assert model.supports_vision is False


def test_admin_api_schema_structure():
    """Test that admin API schemas include new fields"""
    from app.admin.router import CreateLLMModelRequest, UpdateLLMModelRequest, LLMModelResponse
    
    # Check CreateLLMModelRequest has the fields
    create_fields = CreateLLMModelRequest.__fields__.keys()
    assert 'supports_text' in create_fields
    assert 'supports_vision' in create_fields
    
    # Check UpdateLLMModelRequest has the fields
    update_fields = UpdateLLMModelRequest.__fields__.keys()
    assert 'supports_text' in update_fields
    assert 'supports_vision' in update_fields
    
    # Check LLMModelResponse has the fields
    response_fields = LLMModelResponse.__fields__.keys()
    assert 'supports_text' in response_fields
    assert 'supports_vision' in response_fields


def test_create_request_defaults():
    """Test that CreateLLMModelRequest has correct defaults"""
    from app.admin.router import CreateLLMModelRequest
    
    request = CreateLLMModelRequest(
        name="test",
        display_name="Test",
        provider="openai",
        api_key="test-key"
    )
    
    assert request.supports_text is True
    assert request.supports_vision is False


def test_html_template_fields():
    """Test that admin.html template includes vision/text checkboxes"""
    import os
    template_path = os.path.join(
        os.path.dirname(__file__), 
        '..', 
        'app', 
        'templates', 
        'admin.html'
    )
    
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for create modal checkboxes
    assert 'llmModelSupportsText' in content
    assert 'llmModelSupportsVision' in content
    assert 'Supports Text' in content
    assert 'Supports Vision' in content or 'Vision (Images)' in content
    
    # Check for edit modal checkboxes
    assert 'editLLMModelSupportsText' in content
    assert 'editLLMModelSupportsVision' in content
    
    # Check that capabilities are displayed in table
    assert 'supports_text' in content
    assert 'supports_vision' in content
    
    # Check JavaScript handling
    assert 'supportsText' in content
    assert 'supportsVision' in content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
