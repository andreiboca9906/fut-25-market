"""Test authentication schemas with sample JSON data."""

import json
from pathlib import Path

from django.test import TestCase

from auth_api.schemas import LoginResponse


class AuthSchemaTestCase(TestCase):
    """Test authentication schemas against sample JSON data."""
    
    fixtures_dir = Path(__file__).parent / "fixtures"
    
    def load_json_fixture(self, filename: str) -> dict:
        """Load JSON fixture data."""
        with open(self.fixtures_dir / filename, "r") as f:
            return json.load(f)
    
    def test_login_response_schema(self):
        """Test LoginResponse schema with sample login data."""
        data = self.load_json_fixture("login.json")
        
        if data:
            response = LoginResponse(**data)
            self.assertEqual(response.message, "Login successful")
            self.assertIsNotNone(response.session_id)
            self.assertIsNotNone(response.persona_id)
    
    def test_login_with_2fa_response_schema(self):
        """Test LoginResponse schema with 2FA login data."""
        data = self.load_json_fixture("login_with_2fa.json")
        
        if data:
            response = LoginResponse(**data)
            self.assertEqual(response.message, "Login successful")
            self.assertIsNotNone(response.session_id)
