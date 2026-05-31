import os

# Use Qt's offscreen platform so tests run without a display server
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
