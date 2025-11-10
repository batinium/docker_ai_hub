#!/usr/bin/env python3
"""
Tests for OpenRouter integration through the AI Hub gateway.

These tests verify:
1. OpenRouter models list endpoint
2. OpenRouter chat completions endpoint
3. Authentication and error handling
4. Response format validation
"""

import os
import sys
from pathlib import Path

import pytest
import requests

# Add parent directory to path for imports
_TEST_DIR = Path(__file__).resolve().parent
_DASHBOARD_DIR = _TEST_DIR.parent
if str(_DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_DIR))

# Test configuration
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8080")
DASHBOARD_API_KEY = os.environ.get("DASHBOARD_API_KEY", "testing")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/auto")
TIMEOUT = int(os.environ.get("TEST_TIMEOUT", "120"))


@pytest.fixture
def headers():
    """Return headers with dashboard API key."""
    return {"X-API-Key": DASHBOARD_API_KEY, "Content-Type": "application/json"}


@pytest.fixture
def session():
    """Create a requests session with default headers."""
    sess = requests.Session()
    sess.headers.update({"X-API-Key": DASHBOARD_API_KEY})
    return sess


class TestOpenRouterModels:
    """Test OpenRouter models list endpoint."""

    def test_list_models(self, session):
        """Test that we can retrieve the list of available models."""
        url = f"{GATEWAY_URL}/openrouter/v1/models"
        response = session.get(url, timeout=TIMEOUT)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "data" in data, "Response should contain 'data' field"
        assert isinstance(data["data"], list), "Data should be a list"
        assert len(data["data"]) > 0, "Should have at least one model"
        
        # Verify model structure
        model = data["data"][0]
        assert "id" in model, "Model should have an 'id' field"

    def test_list_models_without_auth(self):
        """Test that models endpoint requires authentication."""
        url = f"{GATEWAY_URL}/openrouter/v1/models"
        response = requests.get(url, timeout=TIMEOUT)
        
        # Should return 401 if auth is required
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"


class TestOpenRouterChat:
    """Test OpenRouter chat completions endpoint."""

    def test_chat_completion(self, session):
        """Test basic chat completion."""
        url = f"{GATEWAY_URL}/openrouter/v1/chat/completions"
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": "Say 'Hello' in one word."}],
            "stream": False,
        }
        
        response = session.post(url, json=payload, timeout=TIMEOUT)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "choices" in data, "Response should contain 'choices' field"
        assert len(data["choices"]) > 0, "Should have at least one choice"
        
        choice = data["choices"][0]
        assert "message" in choice, "Choice should have 'message' field"
        assert "content" in choice["message"], "Message should have 'content' field"
        
        content = choice["message"]["content"]
        assert isinstance(content, str), "Content should be a string"
        assert len(content) > 0, "Content should not be empty"

    def test_chat_completion_different_models(self, session):
        """Test chat completion with different model options."""
        models_to_test = [
            "openrouter/auto",
            "openrouter/anthropic/claude-3.5-sonnet",
            "openrouter/google/gemini-pro-1.5",
        ]
        
        for model in models_to_test:
            url = f"{GATEWAY_URL}/openrouter/v1/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "Reply with just 'OK'."}],
                "stream": False,
            }
            
            try:
                response = session.post(url, json=payload, timeout=TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    assert "choices" in data, f"Model {model} should return choices"
                    print(f"✓ Model {model} works")
                else:
                    print(f"⚠ Model {model} returned {response.status_code}: {response.text[:100]}")
            except Exception as e:
                print(f"⚠ Model {model} failed: {e}")

    def test_chat_completion_without_auth(self):
        """Test that chat endpoint requires authentication."""
        url = f"{GATEWAY_URL}/openrouter/v1/chat/completions"
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
        }
        
        response = requests.post(url, json=payload, timeout=TIMEOUT)
        
        # Should return 401 if auth is required
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"

    def test_chat_completion_invalid_model(self, session):
        """Test chat completion with invalid model."""
        url = f"{GATEWAY_URL}/openrouter/v1/chat/completions"
        payload = {
            "model": "invalid/model/name",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
        }
        
        response = session.post(url, json=payload, timeout=TIMEOUT)
        
        # Should return an error for invalid model
        assert response.status_code != 200, "Invalid model should not return 200"
        # OpenRouter typically returns 400 or 404 for invalid models
        assert response.status_code in [400, 404, 422], f"Unexpected status code: {response.status_code}"

    def test_chat_completion_streaming(self, session):
        """Test chat completion with streaming enabled."""
        url = f"{GATEWAY_URL}/openrouter/v1/chat/completions"
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": "Count to 3."}],
            "stream": True,
        }
        
        response = session.post(url, json=payload, timeout=TIMEOUT, stream=True)
        
        # Streaming responses should return 200
        assert response.status_code == 200, f"Expected 200 for streaming, got {response.status_code}"
        
        # Check that we get streaming data
        chunks = []
        for line in response.iter_lines():
            if line:
                chunks.append(line)
                if len(chunks) >= 3:  # Get a few chunks to verify streaming works
                    break
        
        assert len(chunks) > 0, "Should receive streaming chunks"

    def test_chat_completion_conversation(self, session):
        """Test multi-turn conversation."""
        url = f"{GATEWAY_URL}/openrouter/v1/chat/completions"
        
        # First message
        payload1 = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": "My name is Alice."}],
            "stream": False,
        }
        response1 = session.post(url, json=payload1, timeout=TIMEOUT)
        assert response1.status_code == 200
        
        # Second message with context
        payload2 = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "user", "content": "My name is Alice."},
                {"role": "assistant", "content": response1.json()["choices"][0]["message"]["content"]},
                {"role": "user", "content": "What is my name?"},
            ],
            "stream": False,
        }
        response2 = session.post(url, json=payload2, timeout=TIMEOUT)
        assert response2.status_code == 200
        
        data2 = response2.json()
        content = data2["choices"][0]["message"]["content"].lower()
        assert "alice" in content, "Model should remember the name from context"


class TestOpenRouterDashboardAPI:
    """Test OpenRouter through the dashboard API endpoint."""

    def test_dashboard_api_chat(self):
        """Test the dashboard's /api/openrouter/chat endpoint."""
        dashboard_url = os.environ.get("DASHBOARD_URL", "http://127.0.0.1:8090")
        url = f"{dashboard_url}/api/openrouter/chat"
        
        payload = {
            "model": OPENROUTER_MODEL,
            "message": "Say 'Hello' in one word.",
        }
        
        headers = {"X-API-Key": DASHBOARD_API_KEY}
        response = requests.post(url, data=payload, headers=headers, timeout=TIMEOUT)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "status" in data, "Response should contain 'status' field"
        assert "response" in data, "Response should contain 'response' field"
        assert data["status"] == 200, "Status should be 200"


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])

