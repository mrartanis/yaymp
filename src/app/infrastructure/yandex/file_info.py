from typing import Any

_CODECS = ("flac-mp4", "mp3")


def get_lossless_file_info(client: Any, track_id: str) -> dict[str, Any]:
    """Read the SDK's original file-info response."""
    info = client.tracks_file_info(
        track_id, quality="lossless", codecs=list(_CODECS), transport="raw"
    )
    download = getattr(info, "download_info", None)
    return {
        key: getattr(download, key, None)
        for key in ("transport", "url", "urls", "codec", "bitrate")
    }


def get_lossless_file_info_v2(client: Any, track_id: str) -> dict[str, Any]:
    """Request the same formats from the experimental API with the SDK signature."""
    from yandex_music.utils.sign_request import DESKTOP_CLIENT, get_file_info_sign

    codecs = list(_CODECS)
    sign = get_file_info_sign(track_id, "lossless", codecs, "raw")
    result = client.request.get(
        f"{client.base_url}/resources/v2/file-info",
        headers={"X-Yandex-Music-Client": DESKTOP_CLIENT},
        params={
            "trackId": track_id,
            "ts": sign.timestamp,
            "sign": sign.value,
            "quality": "lossless",
            "codecs": ",".join(codecs),
            "transports": "raw",
        },
    )
    if not isinstance(result, dict):
        return {}
    info = result.get("fileInfo", result)
    return info if isinstance(info, dict) else {}
