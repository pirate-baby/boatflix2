"""Jellyfin API client for playlist management and library operations."""

import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class JellyfinClient:
    """Client for Jellyfin REST API."""

    def __init__(self):
        self.base_url = settings.JELLYFIN_URL.rstrip("/")
        self.api_key = settings.JELLYFIN_API_KEY

    @property
    def _enabled(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f'MediaBrowser Token="{self.api_key}"'}

    async def _get_admin_user_id(self) -> Optional[str]:
        """Get the first admin user ID (needed for playlist operations)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/Users",
                headers=self._headers(),
            )
            resp.raise_for_status()
            users = resp.json()
            for user in users:
                if user.get("Policy", {}).get("IsAdministrator"):
                    return user["Id"]
            if users:
                return users[0]["Id"]
        return None

    async def get_or_create_playlist(
        self, name: str, user_id: Optional[str] = None
    ) -> Optional[str]:
        """Get an existing playlist by name, or create a new one.

        Returns the Jellyfin playlist ID.
        """
        if not self._enabled:
            logger.debug("Jellyfin API key not configured, skipping playlist sync")
            return None

        try:
            if not user_id:
                user_id = await self._get_admin_user_id()
            if not user_id:
                logger.error("No Jellyfin user found")
                return None

            # Search for existing playlist
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/Users/{user_id}/Items",
                    headers=self._headers(),
                    params={
                        "IncludeItemTypes": "Playlist",
                        "Recursive": "true",
                        "SearchTerm": name,
                    },
                )
                resp.raise_for_status()
                results = resp.json()

                for item in results.get("Items", []):
                    if item["Name"] == name:
                        return item["Id"]

                # Create new playlist
                resp = await client.post(
                    f"{self.base_url}/Playlists",
                    headers=self._headers(),
                    json={
                        "Name": name,
                        "UserId": user_id,
                        "MediaType": "Audio",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                playlist_id = data.get("Id")
                logger.info(f"Created Jellyfin playlist: {name} ({playlist_id})")
                return playlist_id

        except Exception as e:
            logger.error(f"Jellyfin playlist error: {e}")
            return None

    async def add_item_to_playlist(
        self, playlist_id: str, file_path: str, user_id: Optional[str] = None
    ) -> bool:
        """Add a music file to a Jellyfin playlist by finding its library item ID.

        Args:
            playlist_id: Jellyfin playlist ID
            file_path: Path to the downloaded file (as seen by Jellyfin)
            user_id: Jellyfin user ID (auto-detected if not provided)
        """
        if not self._enabled:
            return False

        try:
            if not user_id:
                user_id = await self._get_admin_user_id()
            if not user_id:
                return False

            # Find the library item by path
            item_id = await self._find_item_by_path(file_path, user_id)
            if not item_id:
                logger.warning(f"Could not find Jellyfin item for: {file_path}")
                return False

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/Playlists/{playlist_id}/Items",
                    headers=self._headers(),
                    params={"Ids": item_id, "UserId": user_id},
                )
                resp.raise_for_status()
                logger.info(f"Added item {item_id} to playlist {playlist_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to add item to playlist: {e}")
            return False

    async def _find_item_by_path(self, file_path: str, user_id: str) -> Optional[str]:
        """Find a Jellyfin library item by its file path."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/Users/{user_id}/Items",
                headers=self._headers(),
                params={
                    "IncludeItemTypes": "Audio",
                    "Recursive": "true",
                    "Path": file_path,
                },
            )
            resp.raise_for_status()
            items = resp.json().get("Items", [])
            if items:
                return items[0]["Id"]
        return None

    async def refresh_music_library(self) -> bool:
        """Trigger a music library scan in Jellyfin."""
        if not self._enabled:
            return False

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/Library/Refresh",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                logger.info("Triggered Jellyfin library refresh")
                return True
        except Exception as e:
            logger.error(f"Failed to refresh Jellyfin library: {e}")
            return False


jellyfin_client = JellyfinClient()
