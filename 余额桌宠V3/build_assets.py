# -*- coding: utf-8 -*-
"""
把原始立绘加工成桌宠能直接用的素材。
=====================================

原始图片是白底的（947×1113），Tkinter 的 -transparentcolor 只认「颜色正好等于
色键」的像素，所以这里必须一次性做好三件事：

    1. 抠底：从画面四边往里灌水，把与边缘相连的近白像素判为背景 ——
       这样碗里的白、蕾丝的白不会被误伤（它们跟边缘不连通）。
    2. 收边：贴着背景的近白像素直接透明，再对 alpha 做轻微羽化，
       并按「白底合成」模型把边缘反解回原色，去掉白边。
    3. 合成：把带 alpha 的图按 alpha 混到品红色键 #ff00ff 上，
       边缘像素因此变成不透明混色，不会再出现粉色噪点。

产物（输出到 assets/）：七个尺寸的立绘，运行时按「屏幕缩放 × 桌宠大小」自动挑最合适的一张
    pet_060.png    144 宽（60%）
    pet_080.png    192 宽（80%）
    pet.png        240 宽（100%，基准）
    pet_125.png    300 宽（125%）
    pet_150.png    360 宽（150%）
    pet_200.png    480 宽（200%）
    pet_250.png    600 宽（250%）
    pet_300.png    720 宽（300%，高分屏上调到最大时用）
    pet_alpha.png  480 宽、带 alpha 的干净立绘（换渲染方式时用）
    pet_preview.png 棋盘格预览（肉眼看抠图边缘）
    pet_icon.png / pet.ico  图标

需要 Pillow + numpy（只在「重新生成素材」时需要，桌宠运行不需要）：
    "C:\\Users\\<你>\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" build_assets.py
或：
    pip install pillow numpy && python build_assets.py

用法：
    python build_assets.py [源图片] [输出目录]
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    print("需要 Pillow 和 numpy：pip install pillow numpy", file=sys.stderr)
    raise SystemExit(1)

# 色键必须与 balance_pet.py 里的 KEY_COLOR 一致（#ff00ff）
KEY = (255, 0, 255)
MARK = (255, 0, 255)          # 灌水时给背景打的标记色（立绘里没有品红）
MARK_ARR = np.array(MARK, dtype=np.uint8)

FLOOD_THRESH = 70             # 灌水容差（曼哈顿距离），白底 JPEG 噪点够用
BASE_WIDTH = 240              # 100% 大小下的立绘宽度
# 必须与 balance_pet.py 里的 PET_ASSETS / SIZE_CHOICES 保持一致
SIZES = (
    ("pet_060.png", 0.60),
    ("pet_080.png", 0.80),
    ("pet.png", 1.00),
    ("pet_125.png", 1.25),
    ("pet_150.png", 1.50),
    ("pet_200.png", 2.00),
    ("pet_250.png", 2.50),
    ("pet_300.png", 3.00),
)
ICON_SIZE = 256               # 图标边长


# ------------------------------------------------------------------ 抠底


def flood_background(img: Image.Image) -> np.ndarray:
    """从四边灌水，返回「是背景」的布尔矩阵。"""
    rgb = img.convert("RGB")
    work = rgb.copy()
    w, h = work.size
    seeds = [
        (0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
        (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2),
        (w // 4, 0), (3 * w // 4, 0), (w // 4, h - 1), (3 * w // 4, h - 1),
    ]
    for seed in seeds:
        if work.getpixel(seed) == MARK:         # 已经被上一次灌水覆盖
            continue
        try:
            ImageDraw.floodfill(work, seed, MARK, thresh=FLOOD_THRESH)
        except Exception as exc:                # 单个种子失败不影响整体
            print(f"  [warn] 种子 {seed} 灌水失败：{exc}")
    arr = np.asarray(work)
    return np.all(arr == MARK_ARR, axis=2)


def cut_out(img: Image.Image) -> Image.Image:
    """白底 -> alpha，并处理白边。"""
    src = img.convert("RGB")
    w, h = src.size
    mask_bg = flood_background(src)
    print(f"  背景像素占比 {mask_bg.mean() * 100:.1f}%")

    alpha = np.where(mask_bg, 0, 255).astype(np.uint8)

    # 收边：距离背景 2 像素以内、且本身接近白色的像素直接挖掉
    mask_img = Image.fromarray((mask_bg * 255).astype(np.uint8))
    near_bg = np.asarray(mask_img.filter(ImageFilter.MaxFilter(5))) > 0
    band = near_bg & ~mask_bg
    rgb = np.asarray(src).astype(np.int16)
    mn = rgb.min(axis=2)
    mx = rgb.max(axis=2)
    whitish = (mn >= 195) & ((mx - mn) <= 45)
    removed = int((band & whitish).sum())
    alpha[band & whitish] = 0
    print(f"  收掉贴边白像素 {removed} 个")

    # 轻微羽化，边缘不至于像刀切
    alpha = np.asarray(
        Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(0.7))
    ).astype(np.float32)

    # 白底反解：observed = true * a + white * (1 - a)
    a = (alpha / 255.0)[..., None]
    safe = np.maximum(a, 0.2)
    true_rgb = (rgb.astype(np.float32) - 255.0 * (1.0 - a)) / safe
    true_rgb = np.clip(true_rgb, 0, 255)

    out = np.dstack([true_rgb, alpha]).astype(np.uint8)
    rgba = Image.fromarray(out, "RGBA")
    return autocrop(rgba)


def autocrop(img: Image.Image, pad: int = 3, thresh: int = 8) -> Image.Image:
    """按 alpha 裁掉四周空白。"""
    a = np.asarray(img.getchannel("A"))
    ys, xs = np.where(a > thresh)
    if len(xs) == 0:
        return img
    x0, x1 = max(0, xs.min() - pad), min(img.width, xs.max() + 1 + pad)
    y0, y1 = max(0, ys.min() - pad), min(img.height, ys.max() + 1 + pad)
    return img.crop((int(x0), int(y0), int(x1), int(y1)))


# ------------------------------------------------------------------ 缩放与合成


def resize_rgba(img: Image.Image, width: int) -> Image.Image:
    """预乘 alpha 后缩放，避免半透明边缘出现黑/白描边。"""
    if img.width == width:
        return img
    ratio = width / img.width
    size = (max(1, int(width)), max(1, int(round(img.height * ratio))))
    arr = np.asarray(img).astype(np.float32)
    a = arr[..., 3:4] / 255.0
    pre = np.dstack([arr[..., :3] * a, arr[..., 3:4]])
    small = np.asarray(
        Image.fromarray(pre.astype(np.uint8), "RGBA").resize(size, Image.LANCZOS)
    ).astype(np.float32)
    sa = np.maximum(small[..., 3:4] / 255.0, 1e-4)
    rgb = np.clip(small[..., :3] / sa, 0, 255)
    return Image.fromarray(np.dstack([rgb, small[..., 3:4]]).astype(np.uint8), "RGBA")


def on_key(img: Image.Image, cutoff: int = 125) -> Image.Image:
    """把 alpha 立绘「二值化」后贴到色键上。

    为什么不做渐变混合？Tk 的 -transparentcolor 只认「颜色正好等于色键」的像素。
    半透明边缘像素混到品红上会变成紫色，它们既不是精确色键（不会被抠掉），
    又不是立绘颜色，于是屏幕上就出现一圈紫边 —— 之前就是这么来的。
    所以这里按 alpha 一刀切：

        alpha >= cutoff -> 完全不透明，用反解过的立绘颜色
        alpha <  cutoff -> 直接刷成精确色键

    这样边缘一个混合像素都不剩，紫边自然消失。代价是轮廓少了一点抗锯齿，
    但原本那点抗锯齿也是被品红污染的，切掉反而更干净。

    cutoff 取 125 是按「实心像素总数」对齐 alpha 覆盖率挑出来的（误差 +0.2%），
    所以轮廓不会明显变胖或变瘦。
    """
    arr = np.asarray(img.convert("RGBA")).astype(np.float32)
    key = np.array(KEY, dtype=np.float32)
    out = np.empty(arr.shape[:2] + (3,), dtype=np.float32)
    solid = arr[..., 3] >= cutoff
    out[solid] = arr[..., :3][solid]
    out[~solid] = key
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def checkerboard(size, cell: int = 8) -> Image.Image:
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    tiles = ((xx // cell) + (yy // cell)) % 2
    board = np.where(tiles[..., None] == 0, np.array([236, 238, 243]),
                     np.array([206, 211, 221])).astype(np.uint8)
    return Image.fromarray(board, "RGB")


# ------------------------------------------------------------------ 主流程


def main() -> int:
    root = Path(__file__).resolve().parent
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else root.parent / "Segment_20260929_212949373.png"
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "assets"
    if not src.is_absolute():
        src = (root / src).resolve()
    if not out_dir.is_absolute():
        out_dir = (root / out_dir).resolve()
    if not src.exists():
        print(f"找不到源图片：{src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"源图片：{src}")
    img = Image.open(src)
    print(f"  原始尺寸 {img.size} 模式 {img.mode}")

    cut = cut_out(img)
    print(f"  抠底裁剪后 {cut.size}")

    biggest = resize_rgba(cut, int(BASE_WIDTH * 2))
    biggest.save(out_dir / "pet_alpha.png")

    for name, factor in SIZES:
        art = resize_rgba(cut, int(round(BASE_WIDTH * factor)))
        on_key(art).save(out_dir / name)
        print(f"  {name}  {art.size[0]}x{art.size[1]}")

    base = resize_rgba(cut, BASE_WIDTH)
    preview = checkerboard(base.size)
    preview.paste(base, (0, 0), base)
    preview.save(out_dir / "pet_preview.png")

    icon_src = resize_rgba(cut, ICON_SIZE)
    canvas = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    canvas.paste(icon_src, ((ICON_SIZE - icon_src.width) // 2,
                            (ICON_SIZE - icon_src.height) // 2), icon_src)
    canvas.save(out_dir / "pet_icon.png")
    try:
        canvas.save(out_dir / "pet.ico",
                    sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    except Exception as exc:
        print(f"  [warn] 生成 ico 失败：{exc}")

    print("\n写出文件：")
    total = 0
    for f in sorted(out_dir.iterdir()):
        total += f.stat().st_size
        print(f"  {f.name:<16} {f.stat().st_size:>8} 字节")
    print(f"  合计 {total / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
