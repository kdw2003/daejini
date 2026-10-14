"""대지니 앱 아이콘 만들기: 청록색 바탕에 흰색 상승 그래프와 화살표.

실행: python tools/make_icons.py  (Pillow 필요, streamlit을 설치하면 함께 설치됨)
결과: docs/icons/ 아래 PNG 파일들 (홈 화면 아이콘, 파비콘)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[1] / "docs" / "icons"
SIZE = 1024  # 크게 그린 뒤 줄여서 가장자리를 부드럽게
TOP, BOTTOM = (36, 139, 168), (17, 84, 108)  # 앱 강조색(#1f6f8b) 계열 그라데이션
WHITE = (255, 255, 255)

# 상승 그래프 꺾은선 (1024 기준 좌표). 마지막 점에서 오른쪽 위로 화살표
LINE = [(170, 720), (345, 545), (480, 640), (660, 420), (790, 300)]
ARROW_TIP = (870, 220)


def background(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        draw.line([(0, y), (size, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    return img


def artwork(scale: float = 1.0) -> Image.Image:
    """투명 바탕 위 그래프. scale<1이면 가운데로 모아 그린다 (안드로이드 마스크 아이콘의 안전 영역용)."""
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    def fit(p):
        c = SIZE / 2
        return (c + (p[0] - c) * scale, c + (p[1] - c) * scale)

    pts = [fit(p) for p in LINE]
    tip = fit(ARROW_TIP)
    width = round(64 * scale)

    # 은은한 가로 눈금선
    for y in (360, 560, 760):
        _, yy = fit((0, y))
        x0, _ = fit((150, 0))
        x1, _ = fit((874, 0))
        draw.line([(x0, yy), (x1, yy)], fill=(255, 255, 255, 38), width=max(2, round(8 * scale)))

    # 그래프 아래 반투명 영역
    base_y = fit((0, 860))[1]
    area = pts + [(pts[-1][0], base_y), (pts[0][0], base_y)]
    draw.polygon(area, fill=(255, 255, 255, 46))

    # 꺾은선 (둥근 이음새)
    draw.line(pts + [tip], fill=WHITE, width=width, joint="curve")
    r = width / 2
    draw.ellipse([pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r], fill=WHITE)

    # 화살표 머리: 마지막 구간 방향으로 삼각형
    (x0, y0), (x1, y1) = pts[-1], tip
    dx, dy = x1 - x0, y1 - y0
    length = (dx * dx + dy * dy) ** 0.5
    ux, uy = dx / length, dy / length
    head, half = 150 * scale, 105 * scale
    point = (x1 + ux * head * 0.55, y1 + uy * head * 0.55)
    back = (x1 - ux * head * 0.45, y1 - uy * head * 0.45)
    left = (back[0] - uy * half, back[1] + ux * half)
    right = (back[0] + uy * half, back[1] - ux * half)
    draw.polygon([point, left, right], fill=WHITE)
    return layer


def compose(scale: float, rounded: bool) -> Image.Image:
    img = background(SIZE).convert("RGBA")
    shadow = artwork(scale).filter(ImageFilter.GaussianBlur(14))
    shadow_tint = Image.new("RGBA", (SIZE, SIZE), (0, 40, 55, 0))
    shadow_tint.putalpha(shadow.getchannel("A").point(lambda a: a * 0.35))
    img.alpha_composite(shadow_tint, (0, 10))
    img.alpha_composite(artwork(scale))
    if rounded:
        mask = Image.new("L", (SIZE, SIZE), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=round(SIZE * 0.22), fill=255)
        img.putalpha(mask)
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    full = compose(scale=1.0, rounded=False)  # 아이폰: 정사각형을 주면 기기가 모서리를 둥글게 깎음
    rounded = compose(scale=1.0, rounded=True)  # 일반 아이콘·파비콘: 둥근 모서리, 바깥은 투명
    maskable = compose(scale=0.78, rounded=False)  # 안드로이드: 가장자리가 잘려도 그래프가 남도록 안쪽에
    outputs = {
        "apple-touch-icon.png": (full, 180),
        "icon-192.png": (rounded, 192),
        "icon-512.png": (rounded, 512),
        "icon-maskable-512.png": (maskable, 512),
        "favicon-32.png": (rounded, 32),
    }
    for name, (img, px) in outputs.items():
        out = img.resize((px, px), Image.LANCZOS)
        if name == "apple-touch-icon.png":
            out = out.convert("RGB")
        out.save(OUT / name, optimize=True)
        print(f"{name}: {px}x{px}")
    full.convert("RGB").resize((512, 512), Image.LANCZOS).save(OUT / "preview.png")


if __name__ == "__main__":
    main()
