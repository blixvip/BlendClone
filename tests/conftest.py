import shutil

import pytest

requires_ffmpeg = pytest.mark.skipif(
    not (shutil.which('ffmpeg') and shutil.which('ffprobe')),
    reason='needs FFmpeg + ffprobe on PATH',
)
