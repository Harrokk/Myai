"""Safe hosted-only fetch of SHA256-pinned PUBLIC STT model bytes.

Never used by the MyAI voice factory or VENTUNO. No credentials, arbitrary
URLs, lazy trust-on-first-use, caches, extracted archives or executable
remote code. Only two exact model/revision/size/digest combinations exist.
"""
import hashlib
import os
from pathlib import Path
import stat
import sys
import time
from urllib.request import Request, urlopen

from core.voice_candidate_hosted_releases import hosted_model_release


_DOWNLOAD_DEADLINE = 720.0
_BLOCK = 1024 * 1024


def download_hosted_model(profile, runner_temp):
    model = hosted_model_release(profile)
    if type(runner_temp) is not str or not runner_temp.startswith("/"):
        raise ValueError("Invalid hosted model destination")
    base = Path(runner_temp).resolve(strict=True)
    directory = base / "myai-pinned-model-files" / profile
    if directory.exists():
        raise ValueError("Refuse to reuse a pre-existing model directory")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    path = directory / model.filename
    fd = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        request = Request(
            model.url,
            headers={
                "Accept-Encoding": "identity",
                "User-Agent": "MyAI-reviewed-hosted-model-smoke/1",
            },
        )
        digest = hashlib.sha256()
        received = 0
        start = time.monotonic()
        with urlopen(request, timeout=70) as response:
            # 200 only; an unreviewed redirect cannot appoint a new hash.
            if response.status != 200:
                raise ValueError("Hosted model response was not successful")
            while True:
                if time.monotonic() - start > _DOWNLOAD_DEADLINE:
                    raise TimeoutError("Hosted model download deadline")
                data = response.read(_BLOCK)
                if not data:
                    break
                received += len(data)
                if received > model.bytes:
                    raise ValueError("Oversized pinned model download")
                digest.update(data)
                view = memoryview(data)
                while view:
                    count = os.write(fd, view)
                    if count <= 0:
                        raise OSError("Hosted model short write")
                    view = view[count:]
        if received != model.bytes or digest.hexdigest() != model.sha256:
            raise ValueError("Published model byte count or SHA256 mismatch")
        if os.fstat(fd).st_size != model.bytes:
            raise ValueError("Pinned model file size mismatch")
        os.fchmod(fd, 0o444)
        os.close(fd)
        fd = None
        directory.chmod(0o555)
        return directory.resolve(strict=True), model
    except Exception:
        if fd is not None:
            os.close(fd)
        try:
            path.unlink(missing_ok=True)
            directory.rmdir()
        except OSError:
            pass
        raise


def main(argv):
    if (len(argv) != 2
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.uname().machine != "aarch64"):
        return 2
    try:
        directory, model = download_hosted_model(
            argv[1], os.environ["RUNNER_TEMP"],
        )
        if directory.name != model.profile:
            return 3
        print("PINNED_PUBLIC_STT_MODEL_HASH: PASS " + model.profile)
        return 0
    except Exception:
        # Never log redirected URL, filesystem path, private environment or
        # raw model bytes.
        print("PINNED_PUBLIC_STT_MODEL_HASH: DENIED", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv))
