# Groove Candy Slide Maker — Configuration

# Discogs API token (get yours at https://www.discogs.com/settings/developers)
DISCOGS_TOKEN = "XvbJrfbtCsGlSRipdODoCZEpmDHwoxBLVbYhrprE"

# User-Agent required by Discogs API
DISCOGS_USER_AGENT = "GrooveCandySlideMaker/1.0"

# Canvas settings (Instagram square post format 1:1)
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1080
BACKGROUND_COLOR = (0, 0, 0)  # Black

# Vinyl label circle size (diameter in pixels)
VINYL_SIZE = 800

# Slide settings
SLIDE_DURATION = 50  # seconds per slide
SLIDE_COUNT = 3

# FFmpeg encoding settings
VIDEO_FPS = 30
AUDIO_BITRATE = "256k"
VIDEO_CODEC = "libx264"
PIXEL_FORMAT = "yuv420p"
