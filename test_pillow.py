try:
    from PIL import Image, ImageDraw, ImageFont
    print("Pillow is installed.")
except ImportError:
    print("Pillow is NOT installed.")
