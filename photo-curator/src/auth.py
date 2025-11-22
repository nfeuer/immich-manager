"""
Authentication middleware for Photo Curator
Integrates with Immich's authentication system
"""

from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from typing import Optional, Dict, Any
import requests
import logging

logger = logging.getLogger(__name__)


class ImmichAuth:
    """Handles Immich authentication and session validation"""

    def __init__(self, immich_url: str):
        """
        Initialize auth handler

        Args:
            immich_url: Base URL of Immich instance (e.g., http://localhost:2283)
        """
        self.immich_url = immich_url.rstrip('/')
        self.api_url = f"{self.immich_url}/api"

    def get_user_from_request(self, request: Request) -> Optional[Dict[str, Any]]:
        """
        Extract and validate user from request cookies/headers

        Args:
            request: FastAPI request object

        Returns:
            User dictionary if authenticated, None otherwise
        """
        # Try to get access token from cookie
        access_token = request.cookies.get('immich_access_token')

        if not access_token:
            # Try Authorization header
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                access_token = auth_header.replace('Bearer ', '')

        if not access_token:
            return None

        # Validate token with Immich API
        try:
            response = requests.get(
                f"{self.api_url}/auth/validateToken",
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=5
            )

            if response.status_code == 200:
                # Token is valid, get user info
                user_response = requests.get(
                    f"{self.api_url}/users/me",
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=5
                )

                if user_response.status_code == 200:
                    user_data = user_response.json()
                    # Add token for future API calls
                    user_data['access_token'] = access_token
                    return user_data

        except requests.RequestException as e:
            logger.error(f"Error validating token: {e}")

        return None

    def login_redirect_url(self, request: Request) -> str:
        """
        Get URL to redirect to Immich login

        Args:
            request: FastAPI request object

        Returns:
            Immich login URL with return path
        """
        # Get current path to return to after login
        return_path = str(request.url.path)
        if request.url.query:
            return_path += f"?{request.url.query}"

        # Immich login URL
        return f"{self.immich_url}/auth/login?returnUrl={return_path}"


async def get_current_user(
    request: Request,
    immich_auth: ImmichAuth = None
) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user

    Args:
        request: FastAPI request
        immich_auth: ImmichAuth instance (injected)

    Returns:
        User dictionary

    Raises:
        HTTPException: If not authenticated
    """
    if immich_auth is None:
        # Get from app state
        immich_auth = request.app.state.immich_auth

    user = immich_auth.get_user_from_request(request)

    if not user:
        # Not authenticated - return 401 with login URL
        login_url = immich_auth.login_redirect_url(request)
        raise HTTPException(
            status_code=401,
            detail={
                'error': 'Not authenticated',
                'login_url': login_url
            }
        )

    return user


async def get_current_user_optional(
    request: Request,
    immich_auth: ImmichAuth = None
) -> Optional[Dict[str, Any]]:
    """
    Get current user without requiring authentication
    Useful for optional auth endpoints

    Args:
        request: FastAPI request
        immich_auth: ImmichAuth instance

    Returns:
        User dictionary or None
    """
    if immich_auth is None:
        immich_auth = request.app.state.immich_auth

    return immich_auth.get_user_from_request(request)


class ImmichAPIClient:
    """
    API client that uses user's authentication token
    for making requests to Immich on their behalf
    """

    def __init__(self, api_url: str, user_token: str):
        """
        Initialize client with user's token

        Args:
            api_url: Immich API URL
            user_token: User's access token
        """
        self.api_url = api_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {user_token}',
            'Accept': 'application/json'
        })

    def get(self, endpoint: str, **kwargs) -> requests.Response:
        """Make GET request as user"""
        return self.session.get(f"{self.api_url}/{endpoint.lstrip('/')}", **kwargs)

    def post(self, endpoint: str, **kwargs) -> requests.Response:
        """Make POST request as user"""
        return self.session.post(f"{self.api_url}/{endpoint.lstrip('/')}", **kwargs)

    def put(self, endpoint: str, **kwargs) -> requests.Response:
        """Make PUT request as user"""
        return self.session.put(f"{self.api_url}/{endpoint.lstrip('/')}", **kwargs)

    def delete(self, endpoint: str, **kwargs) -> requests.Response:
        """Make DELETE request as user"""
        return self.session.delete(f"{self.api_url}/{endpoint.lstrip('/')}", **kwargs)


def get_user_api_client(user: Dict[str, Any], api_url: str) -> ImmichAPIClient:
    """
    Create Immich API client for a specific user

    Args:
        user: User dictionary with access_token
        api_url: Immich API URL

    Returns:
        Authenticated API client
    """
    return ImmichAPIClient(api_url, user['access_token'])
