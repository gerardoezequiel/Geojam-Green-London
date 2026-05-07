import os, imageio
from PIL import Image

# Paths
MAPS_DIR = "annual_verification_maps"
OUTPUT_GIF = "london_greenness_10year_timelapse.gif"

def create_animation():
    print("Gathering annual maps...")
    files = sorted([f for f in os.listdir(MAPS_DIR) if f.startswith("map_") and f.endswith(".png")])
    
    if not files:
        print("No maps found to animate!")
        return

    frames = []
    print(f"Processing {len(files)} frames for a Discord-friendly GIF...")
    
    for filename in files:
        path = os.path.join(MAPS_DIR, filename)
        img = Image.open(path)
        
        # Resize for small file size (Discord friendly)
        # 800px width is usually a good balance of detail and size
        base_width = 800
        w_percent = (base_width / float(img.size[0]))
        h_size = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((base_width, h_size), Image.Resampling.LANCZOS)
        
        frames.append(img)
        print(f"  Resized and added {filename}")

    print(f"Saving optimized animation to {OUTPUT_GIF}...")
    # Reduce duration and use optimize flag
    imageio.mimsave(OUTPUT_GIF, frames, fps=1.5, loop=0)
    print("Done!")

if __name__ == "__main__":
    create_animation()
