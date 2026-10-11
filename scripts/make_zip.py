"""
make_zip.py - zip images/pizza and images/sushi into my_images.zip (top-level class folders).
Run after you have eyeballed the folders and deleted any wrong images.
"""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "images")
ZIP_PATH = os.path.join(ROOT, "my_images.zip")

with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_STORED) as zf:  # jpgs are already compressed
    for cls in sorted(os.listdir(SRC)):
        folder = os.path.join(SRC, cls)
        if not os.path.isdir(folder):
            continue
        files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".jpg"))
        for f in files:
            zf.write(os.path.join(folder, f), arcname=f"{cls}/{f}")  # pizza/xxx.jpg
        print(f"{cls:8s} {len(files)} images")

print(f"\nWrote {ZIP_PATH} ({os.path.getsize(ZIP_PATH) / 1e6:.1f} MB)")
