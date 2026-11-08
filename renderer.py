import io
import urllib.request
import ctypes
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from config import WALLPAPER_PATH, set_windows_wallpaper

def get_font(size, bold=False):
    font_names = ["msyh.ttc", "arialuni.ttf", "segoeui.ttf", "arial.ttf"]
    if bold:
        font_names = ["msyhbd.ttc", "segoeuib.ttf", "arialbd.ttf"] + font_names
        
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except IOError:
            continue
    return ImageFont.load_default()

def create_ambient_background(width, height, cover_img, blur_radius):
    small_cover = cover_img.resize((32, 32), Image.Resampling.LANCZOS)
    bg = small_cover.resize((width, height), Image.Resampling.BICUBIC)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    dark_filter = Image.new("RGB", (width, height), (20, 20, 20))
    bg = Image.blend(bg, dark_filter, alpha=0.4)
    return bg

def generate_wallpaper(artist, title, track_data, lyrics_text, show_lyrics, blur_radius=80, is_closing_func=None):
    try:
        cover_url = track_data.cover_uri.replace("%%", "600x600")
        if cover_url.startswith("//"):
            cover_url = "https:" + cover_url
        elif not cover_url.startswith("http"):
            cover_url = "https://" + cover_url
            
        req = urllib.request.Request(cover_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            cover_data = response.read()
            
        cover_img = Image.open(io.BytesIO(cover_data)).convert("RGB")
        
        user32 = ctypes.windll.user32
        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)
        
        if blur_radius > 0:
            canvas = create_ambient_background(screen_width, screen_height, cover_img, blur_radius)
        else:
            canvas = Image.new("RGB", (screen_width, screen_height), (0, 0, 0))
        
        x_offset = (screen_width - cover_img.width) // 2
        y_offset = (screen_height - cover_img.height) // 2 - 50
        canvas.paste(cover_img, (x_offset, y_offset))
        
        draw = ImageDraw.Draw(canvas)
        
        duration_str = ""
        if hasattr(track_data, 'duration_ms') and track_data.duration_ms:
            m, s = divmod(int(track_data.duration_ms / 1000), 60)
            duration_str = f"{m:02d}:{s:02d}"
            
        album_name = track_data.albums[0].title if hasattr(track_data, 'albums') and track_data.albums else ""

        font_artist = get_font(28)
        font_album = get_font(20)
        font_time = get_font(20)

        text_main_color = "white"
        text_sec_color = "#E0E0E0"
        text_album_color = "#B0B0B0"

        if album_name and album_name.strip().lower() != title.strip().lower():
            draw.text((screen_width // 2, y_offset - 40), f"— {album_name.upper()} —", font=font_album, fill=text_album_color, anchor="ma")

        text_y = y_offset + cover_img.height + 25 
        
        title_size = 40
        while draw.textlength(title, font=get_font(title_size, bold=True)) > (cover_img.width + 200) and title_size > 16:
            title_size -= 2
        font_title = get_font(title_size, bold=True)

        draw.text((screen_width // 2, text_y), title, font=font_title, fill=text_main_color, anchor="ma")
        draw.text((screen_width // 2, text_y + 50), artist, font=font_artist, fill=text_sec_color, anchor="ma")
        
        if duration_str:
            draw.text((screen_width // 2, text_y + 100), duration_str, font=font_time, fill=text_album_color, anchor="ma")
        
        if show_lyrics and lyrics_text:
            canvas = draw_lyrics_columns(canvas, lyrics_text, text_y)
        
        # Блокируем сохранение только если программа закрывается прямо сейчас
        if is_closing_func and is_closing_func():
            return False
            
        canvas.save(WALLPAPER_PATH, "JPEG", quality=95)
        set_windows_wallpaper(WALLPAPER_PATH)
        return True
    except Exception as e:
        print(f"Wallpaper Error: {e}")
        return False

def draw_lyrics_columns(canvas, lyrics_text, text_y):
    canvas_rgba = canvas.convert("RGBA")
    overlay = Image.new("RGBA", canvas_rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    screen_w, screen_h = canvas.size
    cover_w = 600
    cover_x = (screen_w - cover_w) // 2
    
    margin_edge = 30      
    gap_to_cover = 30     
    
    left_max_w = cover_x - margin_edge - gap_to_cover
    right_max_w = screen_w - (cover_x + cover_w) - margin_edge - gap_to_cover
    
    box_width = min(left_max_w, right_max_w)
    left_x = margin_edge
    right_x = screen_w - margin_edge - box_width
    
    box_top = 30
    box_bottom = screen_h - 30 
    box_height = box_bottom - box_top
    
    pad_x = 25
    safe_max_width = box_width - (pad_x * 2)

    raw_lines = [line.strip() for line in lyrics_text.split('\n') if line.strip()]
    best_font = None
    best_line_height = 0
    left_lines = []
    right_lines = []
    wrapped_lines = []
    
    text_max_height = box_height - 120 
    
    for size in range(40, 9, -1):
        font = get_font(size)
        line_height = int(size * 1.25) 
        
        wrapped_lines = []
        for line in raw_lines:
            words = line.split()
            current_line = []
            for word in words:
                test_line = ' '.join(current_line + [word])
                if draw.textlength(test_line, font=font) <= safe_max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        wrapped_lines.append(' '.join(current_line))
                    current_line = [word]
            if current_line:
                wrapped_lines.append(' '.join(current_line))

        half_len = len(wrapped_lines) // 2
        temp_left = wrapped_lines[:half_len]
        temp_right = wrapped_lines[half_len:]
        current_text_height = max(len(temp_left), len(temp_right)) * line_height

        if current_text_height <= text_max_height:
            best_font = font
            best_line_height = line_height
            left_lines = temp_left
            right_lines = temp_right
            break 

    if not best_font:
        size = 10
        best_font = get_font(size)
        best_line_height = int(size * 1.25)
        max_lines = text_max_height // best_line_height
        left_lines = wrapped_lines[:max_lines]
        right_lines = wrapped_lines[max_lines:max_lines*2]

    text_block_height = max(len(left_lines), len(right_lines)) * best_line_height
    text_start_y = box_top + (box_height - text_block_height) // 2
    
    text_color = (255, 255, 255, 220) 
    box_bg_color = (20, 20, 20, 140)  
    box_outline_color = (255, 255, 255, 30)

    if left_lines:
        box_left = [left_x, box_top, left_x + box_width, box_bottom]
        draw.rounded_rectangle(box_left, radius=15, fill=box_bg_color, outline=box_outline_color, width=2)
        current_y = text_start_y
        for line in left_lines:
            draw.text((left_x + pad_x, current_y), line, font=best_font, fill=text_color, anchor="la")
            current_y += best_line_height

    if right_lines:
        box_right = [right_x, box_top, right_x + box_width, box_bottom]
        draw.rounded_rectangle(box_right, radius=15, fill=box_bg_color, outline=box_outline_color, width=2)
        current_y = text_start_y
        for line in right_lines:
            draw.text((right_x + pad_x, current_y), line, font=best_font, fill=text_color, anchor="la")
            current_y += best_line_height

    return Image.alpha_composite(canvas_rgba, overlay).convert("RGB")