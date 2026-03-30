import os
from urllib.parse import urlparse


def normalize_channel(raw: str) -> tuple[str, str]:
    raw = (raw or "").strip()

    if raw.startswith(("http://", "https://")):
        channel_url = raw.rstrip("/")
        for suffix in ("/streams", "/videos", "/shorts", "/featured", "/live"):
            if channel_url.endswith(suffix):
                channel_url = channel_url[:-len(suffix)]
                break

        path = urlparse(channel_url).path.strip("/")
        parts = [p for p in path.split("/") if p]

        if not parts:
            channel_dir = "channel"
        elif parts[0].startswith("@"):
            channel_dir = parts[0][1:]
        elif parts[0] in {"channel", "c", "user"} and len(parts) >= 2:
            channel_dir = parts[1]
        else:
            channel_dir = parts[-1]
    else:
        handle = raw if raw.startswith("@") else f"@{raw}"
        channel_url = f"https://www.youtube.com/{handle}"
        channel_dir = handle[1:]

    channel_dir = "".join(
        ch.lower() for ch in channel_dir
        if ch.isalnum() or ch in "_-"
    ) or "channel"

    return channel_url, channel_dir


def main() -> None:
    channel_input = os.environ["CHANNEL_INPUT"]
    github_env = os.environ["GITHUB_ENV"]

    channel_url, channel_dir = normalize_channel(channel_input)

    with open(github_env, "a", encoding="utf-8") as f:
        f.write(f"CHANNEL_URL={channel_url}\n")
        f.write(f"CHANNEL_DIR={channel_dir}\n")


if __name__ == "__main__":
    main()
