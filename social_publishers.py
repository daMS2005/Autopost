import json
import mimetypes
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SOCIAL_DATA_DIR = PROJECT_ROOT / "data" / "social"
DEFAULT_TIKTOK_TOKEN_FILE = DEFAULT_SOCIAL_DATA_DIR / "tiktok_tokens.json"
DEFAULT_YOUTUBE_TOKEN_FILE = DEFAULT_SOCIAL_DATA_DIR / "youtube_token.json"
DEFAULT_YOUTUBE_CLIENT_SECRETS_FILE = PROJECT_ROOT / "client_secrets.json"

TIKTOK_OPEN_API_BASE = "https://open.tiktokapis.com"
TIKTOK_OAUTH_AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_OAUTH_TOKEN_URL = f"{TIKTOK_OPEN_API_BASE}/v2/oauth/token/"
TIKTOK_CREATOR_INFO_URL = f"{TIKTOK_OPEN_API_BASE}/v2/post/publish/creator_info/query/"
TIKTOK_DIRECT_POST_INIT_URL = f"{TIKTOK_OPEN_API_BASE}/v2/post/publish/video/init/"
TIKTOK_UPLOAD_DRAFT_INIT_URL = f"{TIKTOK_OPEN_API_BASE}/v2/post/publish/inbox/video/init/"
TIKTOK_POST_STATUS_URL = f"{TIKTOK_OPEN_API_BASE}/v2/post/publish/status/fetch/"

DEFAULT_TIKTOK_SCOPES = ("user.info.basic", "video.publish")
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

TIKTOK_CHUNK_SIZE = 10 * 1024 * 1024


@dataclass
class PublishMetadata:
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    caption: str = ""
    privacy_status: str = "private"
    category_id: str = "22"
    made_for_kids: bool = False


def build_publish_metadata(
    *,
    title: str,
    subreddit: str | None = None,
    category: str | None = None,
    part_number: int | None = None,
    total_parts: int | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    privacy_status: str = "private",
) -> PublishMetadata:
    base_title = str(title or "").strip() or "Untitled"
    full_title = (
        f"{base_title} (Part {part_number})"
        if part_number and total_parts and total_parts > 1
        else base_title
    )
    default_tags = [
        tag
        for tag in [
            subreddit,
            category,
            "reddit",
            "viral",
            "storytime" if category != "ask" else "questions",
        ]
        if tag
    ]
    formatted_tags = list(dict.fromkeys([*(tags or []), *default_tags]))
    formatted_caption = f"{full_title}\n\n" + " ".join(
        f"#{str(tag).replace(' ', '').lower()}" for tag in formatted_tags
    )
    return PublishMetadata(
        title=full_title,
        description=(description or "").strip(),
        tags=formatted_tags,
        caption=formatted_caption.strip(),
        privacy_status=privacy_status,
    )


def _json_request(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 240) -> dict[str, Any]:
    body = None
    merged_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        merged_headers.setdefault("Content-Type", "application/json; charset=UTF-8")
    request = Request(url, data=body, headers=merged_headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _form_request(url: str, form_data: dict[str, Any], *, timeout: int = 240) -> dict[str, Any]:
    request = Request(
        url,
        data=urlencode(form_data).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


class TikTokPublisher:
    def __init__(
        self,
        client_key: str | None = None,
        client_secret: str | None = None,
        token_file: str | Path = DEFAULT_TIKTOK_TOKEN_FILE,
    ):
        self.client_key = client_key or os.getenv("TIKTOK_CLIENT_KEY")
        self.client_secret = client_secret or os.getenv("TIKTOK_CLIENT_SECRET")
        self.token_file = Path(token_file).expanduser().resolve()
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.client_key or not self.client_secret:
            raise RuntimeError("Missing TikTok client credentials.")

    def build_authorization_url(
        self,
        redirect_uri: str,
        scopes: tuple[str, ...] = DEFAULT_TIKTOK_SCOPES,
        state: str | None = None,
    ) -> tuple[str, str]:
        resolved_state = state or secrets.token_urlsafe(24)
        query = urlencode(
            {
                "client_key": self.client_key,
                "response_type": "code",
                "scope": ",".join(scopes),
                "redirect_uri": redirect_uri,
                "state": resolved_state,
            }
        )
        return f"{TIKTOK_OAUTH_AUTHORIZE_URL}?{query}", resolved_state

    def exchange_code_for_token(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier
        token_bundle = _form_request(TIKTOK_OAUTH_TOKEN_URL, payload)
        self.save_tokens(token_bundle)
        return token_bundle

    def refresh_access_token(self, refresh_token: str | None = None) -> dict[str, Any]:
        current = self.load_tokens()
        token_to_refresh = refresh_token or current.get("refresh_token")
        if not token_to_refresh:
            raise RuntimeError("No TikTok refresh token is available.")
        token_bundle = _form_request(
            TIKTOK_OAUTH_TOKEN_URL,
            {
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": token_to_refresh,
            },
        )
        merged = {**current, **token_bundle}
        self.save_tokens(merged)
        return merged

    def load_tokens(self) -> dict[str, Any]:
        if not self.token_file.exists():
            return {}
        return json.loads(self.token_file.read_text(encoding="utf-8"))

    def save_tokens(self, tokens: dict[str, Any]) -> Path:
        self.token_file.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
        return self.token_file

    def _authorized_headers(self) -> dict[str, str]:
        tokens = self.load_tokens()
        access_token = tokens.get("access_token")
        if not access_token:
            raise RuntimeError("No TikTok access token is available.")
        return {"Authorization": f"Bearer {access_token}"}

    def query_creator_info(self) -> dict[str, Any]:
        return _json_request(
            TIKTOK_CREATOR_INFO_URL,
            method="POST",
            payload={},
            headers=self._authorized_headers(),
        )

    def init_direct_post(
        self,
        video_path: str | Path,
        *,
        title: str,
        privacy_level: str = "SELF_ONLY",
        disable_duet: bool = False,
        disable_comment: bool = False,
        disable_stitch: bool = False,
        video_cover_timestamp_ms: int | None = None,
        is_aigc: bool = False,
        brand_content_toggle: bool = False,
        brand_organic_toggle: bool = False,
    ) -> dict[str, Any]:
        video_file = Path(video_path).expanduser().resolve()
        video_size = video_file.stat().st_size
        chunk_size = min(max(TIKTOK_CHUNK_SIZE, 5 * 1024 * 1024), 64 * 1024 * 1024)
        total_chunk_count = max(1, (video_size + chunk_size - 1) // chunk_size)

        payload = {
            "post_info": {
                "title": title,
                "privacy_level": privacy_level,
                "disable_duet": disable_duet,
                "disable_comment": disable_comment,
                "disable_stitch": disable_stitch,
                "brand_content_toggle": brand_content_toggle,
                "brand_organic_toggle": brand_organic_toggle,
                "is_aigc": is_aigc,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunk_count,
            },
        }
        if video_cover_timestamp_ms is not None:
            payload["post_info"]["video_cover_timestamp_ms"] = int(
                video_cover_timestamp_ms
            )
        return _json_request(
            TIKTOK_DIRECT_POST_INIT_URL,
            method="POST",
            payload=payload,
            headers=self._authorized_headers(),
        )

    def init_upload_draft(self, video_path: str | Path) -> dict[str, Any]:
        video_file = Path(video_path).expanduser().resolve()
        video_size = video_file.stat().st_size
        chunk_size = min(max(TIKTOK_CHUNK_SIZE, 5 * 1024 * 1024), 64 * 1024 * 1024)
        total_chunk_count = max(1, (video_size + chunk_size - 1) // chunk_size)
        return _json_request(
            TIKTOK_UPLOAD_DRAFT_INIT_URL,
            method="POST",
            payload={
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": total_chunk_count,
                }
            },
            headers=self._authorized_headers(),
        )

    def upload_video_file(self, upload_url: str, video_path: str | Path) -> None:
        video_file = Path(video_path).expanduser().resolve()
        total_size = video_file.stat().st_size
        mime_type = mimetypes.guess_type(video_file.name)[0] or "video/mp4"

        with video_file.open("rb") as handle:
            start = 0
            while start < total_size:
                end = min(start + TIKTOK_CHUNK_SIZE, total_size)
                chunk = handle.read(end - start)
                request = Request(
                    upload_url,
                    data=chunk,
                    headers={
                        "Content-Type": mime_type,
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end - 1}/{total_size}",
                    },
                    method="PUT",
                )
                with urlopen(request, timeout=240):
                    pass
                start = end

    def get_post_status(self, publish_id: str) -> dict[str, Any]:
        return _json_request(
            TIKTOK_POST_STATUS_URL,
            method="POST",
            payload={"publish_id": publish_id},
            headers=self._authorized_headers(),
        )


class YouTubePublisher:
    def __init__(
        self,
        client_secrets_file: str | Path = DEFAULT_YOUTUBE_CLIENT_SECRETS_FILE,
        token_file: str | Path = DEFAULT_YOUTUBE_TOKEN_FILE,
    ):
        self.client_secrets_file = Path(client_secrets_file).expanduser().resolve()
        self.token_file = Path(token_file).expanduser().resolve()
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

    def get_authenticated_service(self):
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        credentials = None
        if self.token_file.exists():
            credentials = Credentials.from_authorized_user_file(
                str(self.token_file),
                [YOUTUBE_UPLOAD_SCOPE],
            )

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleRequest())
        elif not credentials or not credentials.valid:
            if not self.client_secrets_file.exists():
                raise RuntimeError(
                    f"YouTube client secrets file not found: {self.client_secrets_file}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secrets_file),
                [YOUTUBE_UPLOAD_SCOPE],
            )
            credentials = flow.run_local_server(
                port=0,
                open_browser=False,
                authorization_prompt_message=(
                    "Open this URL in your browser to authorize YouTube upload access: "
                    "{url}"
                ),
                success_message=(
                    "YouTube authorization completed. You can close this browser tab."
                ),
            )

        self.token_file.write_text(credentials.to_json(), encoding="utf-8")
        return build(
            YOUTUBE_API_SERVICE_NAME,
            YOUTUBE_API_VERSION,
            credentials=credentials,
        )

    def upload_video(self, video_path: str | Path, metadata: PublishMetadata) -> dict[str, Any]:
        from googleapiclient.http import MediaFileUpload

        service = self.get_authenticated_service()
        video_file = Path(video_path).expanduser().resolve()
        body = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "categoryId": metadata.category_id,
            },
            "status": {
                "privacyStatus": metadata.privacy_status,
                "selfDeclaredMadeForKids": metadata.made_for_kids,
            },
        }

        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=MediaFileUpload(str(video_file), chunksize=-1, resumable=True),
        )

        response = None
        while response is None:
            _, response = request.next_chunk()
        return response
