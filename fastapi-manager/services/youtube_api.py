"""YouTube API service with OAuth2 authentication."""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import settings

logger = logging.getLogger(__name__)

# YouTube API quota costs
QUOTA_COSTS = {
    "playlists.list": 1,
    "playlistItems.list": 1,
    "videos.list": 1,
    "channels.list": 1,
}

DAILY_QUOTA_LIMIT = 10000

# OAuth2 scopes
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


class YouTubeAPIError(Exception):
    """Custom exception for YouTube API errors."""
    pass


class YouTubeQuotaExceeded(Exception):
    """Exception raised when YouTube API quota is exceeded."""
    pass


class YouTubeAPIService:
    """Service for interacting with YouTube Data API v3."""

    def __init__(self):
        """Initialize YouTube API service."""
        self.client_id = settings.YOUTUBE_CLIENT_ID
        self.client_secret = settings.YOUTUBE_CLIENT_SECRET
        # redirect_uri is now built dynamically per request

        # Initialize Fernet cipher for token encryption
        if settings.YOUTUBE_ENCRYPTION_KEY:
            self.cipher = Fernet(settings.YOUTUBE_ENCRYPTION_KEY.encode())
        else:
            logger.warning("No YOUTUBE_ENCRYPTION_KEY set - generating temporary key")
            self.cipher = Fernet(Fernet.generate_key())

    def encrypt_token(self, token: str) -> str:
        """Encrypt an OAuth token."""
        return self.cipher.encrypt(token.encode()).decode()

    def decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt an OAuth token."""
        return self.cipher.decrypt(encrypted_token.encode()).decode()

    def create_oauth_flow(self, redirect_uri: str, state: Optional[str] = None) -> tuple[Flow, str]:
        """
        Create OAuth2 flow for user authentication.

        Args:
            redirect_uri: The redirect URI for this OAuth flow
            state: Optional state parameter

        Returns:
            Tuple of (Flow object, state string)
        """
        if not self.client_id or not self.client_secret:
            raise YouTubeAPIError(
                "YouTube OAuth credentials not configured. "
                "Please set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in your .env file. "
                "See YOUTUBE_SETUP.md for instructions."
            )

        client_config = {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }

        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )

        if not state:
            state = secrets.token_urlsafe(32)

        return flow, state

    def get_authorization_url(self, redirect_uri: str) -> tuple[str, str]:
        """
        Get the OAuth2 authorization URL to redirect user to.

        Args:
            redirect_uri: The redirect URI for this OAuth flow

        Returns:
            Tuple of (authorization_url, state)
        """
        flow, state = self.create_oauth_flow(redirect_uri)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",  # Force consent to get refresh token
            state=state,
        )
        return auth_url, state

    async def exchange_code_for_tokens(
        self, code: str, state: str, redirect_uri: str
    ) -> dict:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback
            state: State parameter for CSRF protection
            redirect_uri: The redirect URI (must match the one used in auth request)

        Returns:
            Dict with user info and tokens
        """
        flow, _ = self.create_oauth_flow(redirect_uri, state)

        try:
            flow.fetch_token(code=code)
            credentials = flow.credentials

            # Get user profile information
            service = build("oauth2", "v2", credentials=credentials)
            user_info = service.userinfo().get().execute()

            # Get YouTube channel info
            youtube = build("youtube", "v3", credentials=credentials)
            channels_response = youtube.channels().list(
                part="snippet",
                mine=True
            ).execute()

            channel_id = None
            if channels_response.get("items"):
                channel_id = channels_response["items"][0]["id"]

            return {
                "email": user_info.get("email"),
                "display_name": user_info.get("name"),
                "channel_id": channel_id or user_info.get("id"),
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_expiry": credentials.expiry,
            }

        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {e}")
            raise YouTubeAPIError(f"OAuth token exchange failed: {str(e)}")

    def get_credentials(
        self, access_token: str, refresh_token: str, token_expiry: datetime
    ) -> Credentials:
        """
        Create Credentials object from stored tokens.

        Args:
            access_token: Encrypted access token
            refresh_token: Encrypted refresh token
            token_expiry: Token expiration datetime

        Returns:
            Google OAuth2 Credentials object
        """
        decrypted_access = self.decrypt_token(access_token)
        decrypted_refresh = self.decrypt_token(refresh_token)

        return Credentials(
            token=decrypted_access,
            refresh_token=decrypted_refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=SCOPES,
            expiry=token_expiry,
        )

    async def refresh_access_token(
        self, credentials: Credentials
    ) -> tuple[str, str, datetime]:
        """
        Refresh an expired access token.

        Args:
            credentials: Google OAuth2 Credentials object

        Returns:
            Tuple of (encrypted_access_token, encrypted_refresh_token, expiry)
        """
        try:
            credentials.refresh(None)

            encrypted_access = self.encrypt_token(credentials.token)
            encrypted_refresh = self.encrypt_token(credentials.refresh_token)

            return encrypted_access, encrypted_refresh, credentials.expiry

        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            raise YouTubeAPIError(f"Token refresh failed: {str(e)}")

    async def get_user_playlists(
        self, credentials: Credentials, page_token: Optional[str] = None
    ) -> dict:
        """
        Get user's playlists from YouTube.

        Args:
            credentials: OAuth2 credentials
            page_token: Token for pagination

        Returns:
            Dict with playlists and next page token
        """
        try:
            youtube = build("youtube", "v3", credentials=credentials)

            request = youtube.playlists().list(
                part="snippet,contentDetails",
                mine=True,
                maxResults=50,
                pageToken=page_token,
            )

            response = request.execute()

            playlists = []
            for item in response.get("items", []):
                playlists.append({
                    "id": item["id"],
                    "title": item["snippet"]["title"],
                    "description": item["snippet"].get("description"),
                    "item_count": item["contentDetails"]["itemCount"],
                })

            return {
                "playlists": playlists,
                "next_page_token": response.get("nextPageToken"),
            }

        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                raise YouTubeQuotaExceeded("YouTube API quota exceeded")
            logger.error(f"YouTube API error: {e}")
            raise YouTubeAPIError(f"Failed to fetch playlists: {str(e)}")

    async def get_liked_videos_playlist_id(self, credentials: Credentials) -> str:
        """
        Get the playlist ID for the user's liked videos.

        Args:
            credentials: OAuth2 credentials

        Returns:
            Playlist ID for liked videos
        """
        try:
            youtube = build("youtube", "v3", credentials=credentials)

            request = youtube.channels().list(
                part="contentDetails",
                mine=True,
            )

            response = request.execute()

            if response.get("items"):
                # Liked videos playlist ID is in relatedPlaylists.likes
                return response["items"][0]["contentDetails"]["relatedPlaylists"]["likes"]

            raise YouTubeAPIError("Could not find liked videos playlist")

        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                raise YouTubeQuotaExceeded("YouTube API quota exceeded")
            logger.error(f"YouTube API error: {e}")
            raise YouTubeAPIError(f"Failed to fetch liked videos playlist: {str(e)}")

    async def get_playlist_items(
        self,
        credentials: Credentials,
        playlist_id: str,
        page_token: Optional[str] = None,
    ) -> dict:
        """
        Get items from a YouTube playlist.

        Args:
            credentials: OAuth2 credentials
            playlist_id: YouTube playlist ID
            page_token: Token for pagination

        Returns:
            Dict with items and next page token
        """
        try:
            youtube = build("youtube", "v3", credentials=credentials)

            request = youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=page_token,
            )

            response = request.execute()

            items = []
            for idx, item in enumerate(response.get("items", [])):
                video_id = item["contentDetails"]["videoId"]
                snippet = item["snippet"]

                items.append({
                    "video_id": video_id,
                    "title": snippet["title"],
                    "artist": snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle") or "Unknown Artist",
                    "position": snippet.get("position", idx),
                    "added_at": datetime.fromisoformat(
                        snippet["publishedAt"].replace("Z", "+00:00")
                    ),
                })

            return {
                "items": items,
                "next_page_token": response.get("nextPageToken"),
            }

        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                raise YouTubeQuotaExceeded("YouTube API quota exceeded")
            logger.error(f"YouTube API error: {e}")
            raise YouTubeAPIError(f"Failed to fetch playlist items: {str(e)}")


# Global instance
youtube_api = YouTubeAPIService()
