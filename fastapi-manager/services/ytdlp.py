"""yt-dlp service for downloading media."""


async def download(url: str, output_path: str) -> dict:
    """Download media from URL using yt-dlp.

    Args:
        url: URL to download from
        output_path: Directory to save downloaded files

    Returns:
        Download result with file information
    """
    # TODO: Implement yt-dlp download logic
    pass


async def get_info(url: str) -> dict:
    """Extract media info without downloading.

    Args:
        url: URL to extract info from

    Returns:
        Media metadata
    """
    # TODO: Implement info extraction
    pass
