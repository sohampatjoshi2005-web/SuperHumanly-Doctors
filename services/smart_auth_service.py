import httpx
import secrets
import hashlib
import base64
import time
from typing import Dict, Any, Optional
from app.core.config import settings

class SMARTAuthService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)

    async def get_smart_config(self, iss: str) -> Dict[str, Any]:
        """
        Fetch SMART configuration from the FHIR server's .well-known endpoint.
        """
        url = f"{iss.rstrip('/')}/.well-known/smart-configuration"
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            # Fallback to metadata if .well-known is not available (older FHIR servers)
            metadata_url = f"{iss.rstrip('/')}/metadata"
            response = await self.client.get(metadata_url)
            response.raise_for_status()
            metadata = response.json()
            # Extract from rest[0].security.extension
            for rest in metadata.get("rest", []):
                for ext in rest.get("security", {}).get("extension", []):
                    if ext.get("url") == "http://fhir-navigation.eastus.cloudapp.azure.com/smart-configuration":
                        # This is a simplification, usually it's a list of extensions
                        pass
            # For simplicity in this implementation, we assume .well-known exists or we fail
            raise RuntimeError(f"Failed to fetch SMART configuration: {e}")

    def generate_pkce(self) -> Dict[str, str]:
        """
        Generate PKCE code_verifier and code_challenge.
        """
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        return {
            "code_verifier": code_verifier,
            "code_challenge": code_challenge
        }

    async def get_authorization_url(
        self, 
        iss: str, 
        redirect_uri: str, 
        client_id: str, 
        scope: str, 
        launch: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Prepare the authorization URL and PKCE/state context.
        """
        config = await self.get_smart_config(iss)
        auth_endpoint = config.get("authorization_endpoint")
        
        if not auth_endpoint:
            raise ValueError("Authorization endpoint not found in SMART config")

        pkce = self.generate_pkce()
        state = secrets.token_urlsafe(32)
        
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "aud": iss,
            "code_challenge": pkce["code_challenge"],
            "code_challenge_method": "S256"
        }
        
        if launch:
            params["launch"] = launch

        auth_url = str(httpx.URL(auth_endpoint).copy_with(params=params))
        
        return {
            "auth_url": auth_url,
            "state": state,
            "code_verifier": pkce["code_verifier"]
        }

    async def exchange_code_for_token(
        self, 
        iss: str, 
        code: str, 
        code_verifier: str, 
        redirect_uri: str, 
        client_id: str
    ) -> Dict[str, Any]:
        """
        Exchange the authorization code for an access token.
        """
        config = await self.get_smart_config(iss)
        token_endpoint = config.get("token_endpoint")
        
        if not token_endpoint:
            raise ValueError("Token endpoint not found in SMART config")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier
        }
        
        response = await self.client.post(token_endpoint, data=data)
        response.raise_for_status()
        return response.json()

smart_auth_service = SMARTAuthService()
