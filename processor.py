import csv
import math
import os
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps, ImageDraw

SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp'}


@dataclass
class ProcessSettings:
    input_dir: str
    workspace_dir: str
    threshold: int = 36
    choke_px: int = 1
    feather_px: float = 1.25
    canvas_size: int = 1024
    trim: bool = True
    copy_originals_to_review: bool = True
    overwrite: bool = True
    padding_ratio: float = 0.92


@dataclass
class ProcessResult:
    file_name: str
    status: str
    note: str
    fg_ratio: float
    border_touch: bool
    output_path: str = ''
    preview_path: str = ''
    review_copy_path: str = ''


class ProcessingCancelled(Exception):
    pass


def ensure_dirs(base_dir: str) -> Dict[str, str]:
    base = Path(base_dir)
    dirs = {
        'output': str(base / 'output_png'),
        'previews': str(base / 'qa_previews'),
        'review': str(base / 'review_needed'),
        'failed': str(base / 'failed'),
        'logs': str(base / 'logs'),
    }
    for d in dirs.values():
        Path(d).mkdir(parents=True, exist_ok=True)
    return dirs


def iter_input_files(input_dir: str):
    for root, _, files in os.walk(input_dir):
        for name in files:
            ext = Path(name).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                yield os.path.join(root, name)


def border_pixels(rgb: np.ndarray) -> np.ndarray:
    top = rgb[0, :, :]
    bottom = rgb[-1, :, :]
    left = rgb[:, 0, :]
    right = rgb[:, -1, :]
    return np.concatenate([top, bottom, left, right], axis=0)


def estimate_bg_color(rgb: np.ndarray) -> np.ndarray:
    bp = border_pixels(rgb).astype(np.float32)
    median = np.median(bp, axis=0)
    bright = bp.mean(axis=1) > np.clip(median.mean() - 18, 170, 255)
    low_sat = (bp.max(axis=1) - bp.min(axis=1)) < 55
    filt = bp[bright & low_sat]
    if len(filt) >= 16:
        return np.median(filt, axis=0)
    return median


def build_background_mask(rgb: np.ndarray, threshold: int) -> Tuple[np.ndarray, np.ndarray]:
    h, w, _ = rgb.shape
    bg_color = estimate_bg_color(rgb)
    rgbf = rgb.astype(np.float32)
    dist = np.linalg.norm(rgbf - bg_color.reshape(1, 1, 3), axis=2)
    brightness = rgbf.mean(axis=2)
    saturation = rgbf.max(axis=2) - rgbf.min(axis=2)
    bg_brightness = float(bg_color.mean())

    # Candidate background includes pixels near the estimated border color,
    # or very light low-saturation pixels likely to be white/gray backdrop.
    candidate = (
        (dist <= threshold * 1.85)
        | ((brightness >= max(165.0, bg_brightness - 22.0)) & (saturation <= max(30, threshold * 1.1)))
    )

    # Connected components so only border-connected background is removed.
    num_labels, labels = cv2.connectedComponents(candidate.astype(np.uint8), connectivity=8)
    border_labels = set(np.unique(np.concatenate([
        labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]
    ])))
    bg_mask = np.isin(labels, list(border_labels))

    # Smooth/clean the foreground and recover tiny edge details better.
    fg_mask = (~bg_mask).astype(np.uint8) * 255
    kernel = np.ones((3, 3), np.uint8)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    # Fill small holes inside the foreground silhouette.
    inv = 255 - fg_mask
    num2, labels2, stats2, _ = cv2.connectedComponentsWithStats(inv, connectivity=8)
    border_labels2 = set(np.unique(np.concatenate([
        labels2[0, :], labels2[-1, :], labels2[:, 0], labels2[:, -1]
    ])))
    for i in range(1, num2):
        area = stats2[i, cv2.CC_STAT_AREA]
        if i not in border_labels2 and area <= max(2500, (h * w) // 200):
            fg_mask[labels2 == i] = 255

    return fg_mask, bg_color


def decontaminate_edge_colors(rgba: np.ndarray, bg_color: np.ndarray) -> np.ndarray:
    out = rgba.astype(np.float32).copy()
    alpha = out[:, :, 3:4] / 255.0
    rgb = out[:, :, :3]
    bg = bg_color.reshape(1, 1, 3).astype(np.float32)
    edge = (alpha > 0.0) & (alpha < 1.0)
    if np.any(edge):
        safe_alpha = np.maximum(alpha, 1 / 255.0)
        corrected = (rgb - bg * (1.0 - alpha)) / safe_alpha
        corrected = np.clip(corrected, 0, 255)
        rgb = np.where(edge, corrected, rgb)
        out[:, :, :3] = rgb
    return out.astype(np.uint8)


def apply_alpha_pipeline(img: Image.Image, threshold: int, choke_px: int, feather_px: float) -> Tuple[Image.Image, Dict[str, float]]:
    rgba = img.convert('RGBA')
    arr = np.array(rgba)
    rgb = arr[:, :, :3]

    fg_mask, bg_color = build_background_mask(rgb, threshold)

    if choke_px > 0:
        kernel = np.ones((3, 3), np.uint8)
        fg_mask = cv2.erode(fg_mask, kernel, iterations=choke_px)

    if feather_px > 0:
        k = max(3, int(round(feather_px * 4)) | 1)
        alpha = cv2.GaussianBlur(fg_mask, (k, k), feather_px)
    else:
        alpha = fg_mask

    out = arr.copy()
    out[:, :, 3] = alpha
    out = decontaminate_edge_colors(out, bg_color)
    out_img = Image.fromarray(out, 'RGBA')

    alpha_np = np.array(out_img.getchannel('A'))
    fg_ratio = float((alpha_np > 10).sum()) / float(alpha_np.size)
    border_touch = bool(
        (alpha_np[0, :] > 10).any() or (alpha_np[-1, :] > 10).any() or
        (alpha_np[:, 0] > 10).any() or (alpha_np[:, -1] > 10).any()
    )
    semi_white_edge_ratio = 0.0
    edge_mask = (alpha_np > 0) & (alpha_np < 200)
    if edge_mask.any():
        rgb_out = np.array(out_img)[:, :, :3]
        semi_white_edge_ratio = float(((rgb_out.mean(axis=2) > 220) & edge_mask).sum()) / float(edge_mask.sum())

    metrics = {
        'fg_ratio': fg_ratio,
        'border_touch': border_touch,
        'semi_white_edge_ratio': semi_white_edge_ratio,
    }
    return out_img, metrics


def trim_and_center(img: Image.Image, canvas_size: int, padding_ratio: float = 0.92) -> Image.Image:
    alpha = np.array(img.getchannel('A'))
    ys, xs = np.where(alpha > 10)
    if len(xs) == 0 or len(ys) == 0:
        return Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))

    bbox = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    cropped = img.crop(bbox)

    if canvas_size <= 0:
        return cropped

    cw, ch = cropped.size
    target = int(canvas_size * padding_ratio)
    scale = min(target / max(cw, 1), target / max(ch, 1), 1.0 if max(cw, ch) <= target else 9999.0)
    new_size = (max(1, int(round(cw * scale))), max(1, int(round(ch * scale))))
    if new_size != cropped.size:
        cropped = cropped.resize(new_size, Image.LANCZOS)

    canvas = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    x = (canvas_size - cropped.width) // 2
    y = (canvas_size - cropped.height) // 2
    canvas.alpha_composite(cropped, (x, y))
    return canvas


def checkerboard(size: Tuple[int, int], block: int = 24) -> Image.Image:
    w, h = size
    img = Image.new('RGB', size, (235, 235, 235))
    draw = ImageDraw.Draw(img)
    c2 = (200, 200, 200)
    for y in range(0, h, block):
        for x in range(0, w, block):
            if ((x // block) + (y // block)) % 2 == 0:
                draw.rectangle([x, y, x + block - 1, y + block - 1], fill=c2)
    return img


def make_preview(original: Image.Image, transparent: Image.Image, label: str = '') -> Image.Image:
    left = ImageOps.contain(original.convert('RGB'), (700, 700))
    checker = checkerboard(transparent.size)
    comp = checker.convert('RGBA')
    comp.alpha_composite(transparent)
    right = ImageOps.contain(comp.convert('RGB'), (700, 700))

    pad = 30
    header_h = 80
    footer_h = 40 if label else 0
    w = left.width + right.width + pad * 3
    h = max(left.height, right.height) + header_h + footer_h + pad * 2
    canvas = Image.new('RGB', (w, h), (32, 34, 41))
    draw = ImageDraw.Draw(canvas)
    draw.text((pad, 18), 'Original', fill=(240, 240, 240))
    draw.text((left.width + pad * 2, 18), 'Transparent PNG Preview', fill=(240, 240, 240))
    if label:
        draw.text((pad, h - footer_h - 8), label, fill=(210, 210, 210))

    y1 = header_h
    canvas.paste(left, (pad, y1 + (max(left.height, right.height) - left.height) // 2))
    canvas.paste(right, (left.width + pad * 2, y1 + (max(left.height, right.height) - right.height) // 2))
    return canvas


def classify_result(metrics: Dict[str, float]) -> Tuple[str, str]:
    notes = []
    if metrics['fg_ratio'] < 0.01:
        notes.append('foreground too small')
    if metrics['fg_ratio'] > 0.90:
        notes.append('foreground unusually large')
    if metrics['border_touch']:
        notes.append('subject touches border')
    if metrics['semi_white_edge_ratio'] > 0.08:
        notes.append('possible white fringe')

    if notes:
        return 'review_needed', '; '.join(notes)
    return 'processed', 'ok'


def process_one(file_path: str, dirs: Dict[str, str], settings: ProcessSettings) -> ProcessResult:
    file_name = os.path.basename(file_path)
    base_name = Path(file_name).stem
    out_png = os.path.join(dirs['output'], base_name + '.png')
    preview_jpg = os.path.join(dirs['previews'], base_name + '_preview.jpg')

    img = Image.open(file_path)
    out_img, metrics = apply_alpha_pipeline(
        img,
        threshold=settings.threshold,
        choke_px=settings.choke_px,
        feather_px=settings.feather_px,
    )
    if settings.trim:
        out_img = trim_and_center(out_img, settings.canvas_size, settings.padding_ratio)
    elif settings.canvas_size > 0 and out_img.size != (settings.canvas_size, settings.canvas_size):
        out_img = ImageOps.contain(out_img, (settings.canvas_size, settings.canvas_size))

    status, note = classify_result(metrics)
    out_img.save(out_png, 'PNG')

    preview = make_preview(img, out_img, f'Status: {status} | Note: {note}')
    preview.save(preview_jpg, 'JPEG', quality=92)

    review_copy_path = ''
    if status == 'review_needed' and settings.copy_originals_to_review:
        review_copy_path = os.path.join(dirs['review'], file_name)
        Image.open(file_path).save(review_copy_path)

    return ProcessResult(
        file_name=file_name,
        status=status,
        note=note,
        fg_ratio=metrics['fg_ratio'],
        border_touch=metrics['border_touch'],
        output_path=out_png,
        preview_path=preview_jpg,
        review_copy_path=review_copy_path,
    )


def write_summary_csv(csv_path: str, results):
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()) if results else [
            'file_name', 'status', 'note', 'fg_ratio', 'border_touch', 'output_path', 'preview_path', 'review_copy_path'
        ])
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))


def process_batch(
    settings: ProcessSettings,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
):
    dirs = ensure_dirs(settings.workspace_dir)
    files = list(iter_input_files(settings.input_dir))
    total = len(files)
    results = []

    if log_callback:
        log_callback(f'Found {total} supported image file(s).')
        log_callback(f'Workspace: {settings.workspace_dir}')

    for idx, file_path in enumerate(files, start=1):
        if cancel_check and cancel_check():
            raise ProcessingCancelled('User cancelled the batch.')
        name = os.path.basename(file_path)
        if progress_callback:
            progress_callback(idx - 1, total, f'Processing {name}')
        try:
            res = process_one(file_path, dirs, settings)
            results.append(res)
            if log_callback:
                log_callback(f'[{idx}/{total}] {name} -> {res.status} ({res.note})')
        except Exception as e:
            failed_path = os.path.join(dirs['failed'], name)
            try:
                Image.open(file_path).save(failed_path)
            except Exception:
                pass
            res = ProcessResult(
                file_name=name,
                status='failed',
                note=f'{type(e).__name__}: {e}',
                fg_ratio=0.0,
                border_touch=False,
            )
            results.append(res)
            if log_callback:
                log_callback(f'[{idx}/{total}] {name} -> failed ({e})')
                log_callback(traceback.format_exc(limit=1).strip())

    if progress_callback:
        progress_callback(total, total, 'Writing summary log...')

    summary_path = os.path.join(dirs['logs'], 'processing_summary.csv')
    write_summary_csv(summary_path, results)

    counts = {'processed': 0, 'review_needed': 0, 'failed': 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    if log_callback:
        log_callback('')
        log_callback('Batch complete.')
        log_callback(f"Processed: {counts.get('processed', 0)}")
        log_callback(f"Review needed: {counts.get('review_needed', 0)}")
        log_callback(f"Failed: {counts.get('failed', 0)}")
        log_callback(f'Summary CSV: {summary_path}')

    return {
        'results': results,
        'summary_csv': summary_path,
        'counts': counts,
        'dirs': dirs,
        'total': total,
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Batch remove white/gray backgrounds and output transparent PNGs.')
    parser.add_argument('--input', required=True, help='Input folder with images')
    parser.add_argument('--workspace', required=True, help='Workspace/output folder')
    parser.add_argument('--threshold', type=int, default=36)
    parser.add_argument('--choke', type=int, default=1)
    parser.add_argument('--feather', type=float, default=1.25)
    parser.add_argument('--canvas', type=int, default=1024)
    parser.add_argument('--no-trim', action='store_true')
    args = parser.parse_args()

    settings = ProcessSettings(
        input_dir=args.input,
        workspace_dir=args.workspace,
        threshold=args.threshold,
        choke_px=args.choke,
        feather_px=args.feather,
        canvas_size=args.canvas,
        trim=not args.no_trim,
    )

    def cb(i, total, msg):
        print(f'[{i}/{total}] {msg}')

    def log(msg):
        print(msg)

    process_batch(settings, progress_callback=cb, log_callback=log)
