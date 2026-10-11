# OPIM 5509 · Assignment 4 · Pizza vs. Sushi

`my_images.zip` holds the image dataset for my binary ConvNet classifier: 242 pizza and 232 sushi photos,
RGB JPEGs with the longest side ≤ 400 px, in top-level `pizza/` and `sushi/` folders.

- `scripts/get_images.py` collects the images from Wikimedia Commons, filters them by keyword, removes
  small, corrupt and duplicate files, and resizes them.
- `scripts/make_zip.py` builds `my_images.zip`.

The Colab notebook downloads the zip directly:
`https://raw.githubusercontent.com/UdayAnalyst/OPIM5509-A4/main/my_images.zip`
