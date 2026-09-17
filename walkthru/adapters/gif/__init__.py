"""GIF render target — a recorded screencast plus the camera track, as an animated GIF.

The second :class:`~walkthru.ports.RenderTarget` (after reelee's Ken Burns mp4), and the
one for documentation: a GIF plays inline in a README on GitHub and PyPI, where a video
does not. It needs **ffmpeg on PATH** and no Python dependency at all, so there is no
extra to install -- :func:`check_ffmpeg` reports its absence with something actionable.

>>> from walkthru.adapters.gif import CameraSegment, gif_filtergraph
>>> "paletteuse" in gif_filtergraph([CameraSegment(0, 2000)], frame_w=640, frame_h=480,
...                                 out_width=640, out_height=480)
True
"""

from walkthru.adapters.gif.geometry import (
    CameraSegment,
    camera_segments,
    crop_box,
    gif_filtergraph,
)
from walkthru.adapters.gif.render_target import (
    FfmpegMissingError,
    GifRenderError,
    GifRenderTarget,
    VideoInfo,
    check_ffmpeg,
    probe_video,
    video_to_gif,
)

__all__ = [
    "CameraSegment",
    "camera_segments",
    "crop_box",
    "gif_filtergraph",
    "GifRenderTarget",
    "GifRenderError",
    "FfmpegMissingError",
    "VideoInfo",
    "check_ffmpeg",
    "probe_video",
    "video_to_gif",
]
