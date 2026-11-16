import os
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple
import cv2
import numpy as np
import matcher

Match = Tuple[int, int, float]


def load_template(path: str) -> Optional[np.ndarray]:
    if not os.path.isfile(path):
        return
    else:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img


@dataclass
class Plate:
    pass
    image: np.ndarray
    mask: np.ndarray
    roi: Tuple[float, float, float, float]
    threshold: float


def load_template_auto(path: str, plate: Optional[dict] = None):
    if not os.path.isfile(path):
        return
    else:
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None:
            return
        else:
            if img.ndim == 3 and img.shape[2] == 4:
                if plate is not None:
                    return Plate(
                        np.ascontiguousarray(img[:, :, :3]),
                        np.ascontiguousarray(img[:, :, 3]),
                        tuple(plate["roi"]),
                        plate["threshold"],
                    )
                else:
                    return np.ascontiguousarray(img[:, :, :3])
            else:
                if img.ndim == 2:
                    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                else:
                    return img


def capture_screen(monitor_index: int = 1, region: Optional[dict] = None) -> Tuple[np.ndarray, int, int]:
    import mss

    with mss.mss() as sct:
        mon = region or sct.monitors[min(monitor_index, len(sct.monitors) - 1)]
        shot = np.array(sct.grab(mon))
    return (cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR), mon["left"], mon["top"])


def capture_for_matching(monitor_index: int = 1, window_capture=None) -> Tuple[np.ndarray, int, int, str]:
    if window_capture is not None:
        try:
            cap = window_capture.grab()
        except Exception:
            cap = None
        if cap is not None and cap.frame is not None:
            return (cap.frame, cap.origin[0], cap.origin[1], "window")
        else:
            frame, ox, oy = capture_screen(monitor_index)
            return (frame, ox, oy, cap.status if cap is not None else "error")
    else:
        frame, ox, oy = capture_screen(monitor_index)
        return (frame, ox, oy, "screen")


def capture_game_window(
    monitor_index: int = 1, background_mode: bool = False, window_capture=None
) -> Tuple[np.ndarray, int, int]:
    if background_mode:
        if window_capture is None:
            try:
                from window_capture import WindowCapture

                window_capture = WindowCapture()
            except Exception:
                window_capture = None
        frame, ox, oy, _src = capture_for_matching(monitor_index, window_capture)
        return (frame, ox, oy)
    else:
        return capture_screen(monitor_index)


def find_template(
    frame: np.ndarray,
    template: np.ndarray,
    threshold: float = 0.82,
    scales: Sequence[float] = (0.9, 0.95, 1.0, 1.05, 1.1),
    full: bool = False,
) -> Tuple[Optional[Match], float]:
    scales = tuple(scales)
    return matcher.remember(
        frame,
        ("ft", id(template), float(threshold), scales, full),
        lambda: (template, _find_template(frame, template, threshold, scales, full)),
    )[1]


def _find_template(
    frame: np.ndarray, template: np.ndarray, threshold: float, scales: Sequence[float], full: bool
) -> Tuple[Optional[Match], float]:
    fg = matcher.frame_gray(frame)
    tg = matcher.template_gray(template)
    tag = ("t", frame.shape[:2], scales)
    hint = matcher.HINTS.get(template, tag)
    if hint is not None:
        quick = _fast_template(fg, tg, hint, threshold)
        if quick is not None:
            matcher.HINTS.put(template, tag, (hint[0], quick[0][0], quick[0][1], hint[3]))
            return quick
    half_f = matcher.frame_half_gray(frame, fg)
    half_t = matcher.template_half(template, tg)
    coarse = [(_match(half_f, half_t, s)[0], s) for s in scales]
    coarse = [c for c in coarse if c[0] > (-1)]
    if not coarse:
        return (None, 0.0)
    else:
        best_coarse, best_scale = max(coarse)
        if (not full) and matcher.hopeless(best_coarse, threshold):
            matcher.HINTS.drop(template, tag)
            return (None, max(best_coarse, 0.0))
        else:
            best = ((-1.0), 0, 0)
            for s in matcher.fine_scales(best_scale):
                score, x, y = _match(fg, tg, s)
                if score > best[0]:
                    best = (score, x, y)
            score, x, y = best
            if score >= threshold:
                matcher.HINTS.put(template, tag, (best_scale, x, y, score))
                return ((x, y, score), score)
            else:
                matcher.HINTS.drop(template, tag)
                return (None, max(score, 0.0))


def _fast_template(fg: np.ndarray, tg: np.ndarray, hint, threshold: float):
    best_scale, cx, cy, anchor = hint
    fh, fw = fg.shape[:2]
    best = ((-1.0), 0, 0)
    for s in matcher.fine_scales(best_scale):
        t = matcher.resized(tg, s, _interp)
        th, tw = t.shape[:2]
        if th > fh or tw > fw or th < 4 or tw < 4:
            continue
        x0, y0, x1, y1 = matcher.window(cx, cy, tw, th, fw, fh)
        sub = fg[y0:y1, x0:x1]
        if th > sub.shape[0] or tw > sub.shape[1]:
            continue
        _, val, _, loc = cv2.minMaxLoc(cv2.matchTemplate(sub, t, cv2.TM_CCOEFF_NORMED))
        if not float(val) > best[0]:
            continue
        best = (float(val), x0 + loc[0] + tw // 2, y0 + loc[1] + th // 2)
    score, x, y = best
    if score >= max(threshold, anchor - matcher.SLACK):
        return ((x, y, score), score)
    return None


def _interp(scale: float) -> int:
    return cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR


def warm_templates(templates, scales: Sequence[float]) -> int:
    try:
        n = 0
        if not matcher.ENABLED:
            return 0
        scales = tuple(scales)
        fine = sorted({round(f, 4) for s in scales for f in matcher.fine_scales(s)})
        for tpl in (templates or {}).values():
            try:
                if tpl is None:
                    continue
                if isinstance(tpl, Plate):
                    matcher.mask_is_full(tpl.mask)
                    for f in [(0.5 * s) for s in scales] + fine:
                        t = matcher.resized(tpl.image, f, _interp, "pi")
                        matcher.resized_to(tpl.mask, t.shape[:2], f)
                        n += 2
                else:
                    tg = matcher.template_gray(tpl)
                    ht = matcher.template_half(tpl, tg)
                    for s in scales:
                        matcher.resized(ht, s, _interp)
                        n += 1
                    for f in fine:
                        matcher.resized(tg, f, _interp)
                        n += 1
            except Exception:
                continue
    except Exception:
        return n
    return n


def _gray(img: np.ndarray):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def _match(frame: np.ndarray, template: np.ndarray, scale: float) -> Tuple[float, int, int]:
    t = matcher.resized(template, scale, _interp)
    th, tw = t.shape[:2]
    if th > frame.shape[0] or tw > frame.shape[1] or th < 4 or tw < 4:
        return ((-2.0), 0, 0)
    _, max_val, _, max_loc = cv2.minMaxLoc(cv2.matchTemplate(frame, t, cv2.TM_CCOEFF_NORMED))
    return (float(max_val), max_loc[0] + tw // 2, max_loc[1] + th // 2)


def find_plate(
    frame: np.ndarray, plate: Plate, scales: Sequence[float] = (0.9, 0.95, 1.0, 1.05, 1.1), full: bool = False
) -> Tuple[Optional[Match], float]:
    scales = tuple(scales)
    key = ("fp", id(plate.image), id(plate.mask), tuple(plate.roi), float(plate.threshold), scales, full)
    return matcher.remember(frame, key, lambda: (plate, _find_plate(frame, plate, scales, full)))[1]


def _find_plate(frame: np.ndarray, plate: Plate, scales: Sequence[float], full: bool) -> Tuple[Optional[Match], float]:
    fh, fw = frame.shape[:2]
    x0, y0 = (int(plate.roi[0] * fw), int(plate.roi[1] * fh))
    x1, y1 = (int(plate.roi[2] * fw), int(plate.roi[3] * fh))
    region = frame[y0:y1, x0:x1]
    if region.size == 0:
        return (None, 0.0)
    plain = matcher.mask_is_full(plate.mask)

    def match(img: np.ndarray, base: float, scale: float, ox: int, oy: int) -> Tuple[float, int, int]:
        f = base * scale
        t = matcher.resized(plate.image, f, _interp, "pi")
        m = matcher.resized_to(plate.mask, t.shape[:2], f)
        if t.shape[0] >= img.shape[0] or t.shape[1] >= img.shape[1] or min(t.shape[:2]) < 6 or (not m.any()):
            return ((-2.0), 0, 0)
        else:
            raw = (
                cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
                if plain
                else cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED, mask=m)
            )
            res = np.nan_to_num(raw, nan=(-1.0), posinf=(-1.0), neginf=(-1.0))
            _, val, _, loc = cv2.minMaxLoc(res)
            return (float(val), ox + loc[0] + t.shape[1] // 2, oy + loc[1] + t.shape[0] // 2)

    tag = ("p", tuple(plate.roi), frame.shape[:2], scales)
    hint = matcher.HINTS.get(plate.image, tag)
    if hint is not None:
        best_scale, cx, cy, anchor = hint
        quick = ((-1.0), 0, 0)
        for s in matcher.fine_scales(best_scale):
            t = matcher.resized(plate.image, s, _interp, "pi")
            wx0, wy0, wx1, wy1 = matcher.window(cx, cy, t.shape[1], t.shape[0], fw, fh)
            wx0, wy0, wx1, wy1 = (max(wx0, x0), max(wy0, y0), min(wx1, x1), min(wy1, y1))
            if wx1 <= wx0 or wy1 <= wy0:
                continue
            cand = match(frame[wy0:wy1, wx0:wx1], 1.0, s, wx0, wy0)
            if not cand[0] > quick[0]:
                continue
            quick = cand
        score, x, y = quick
        score = min(score, 1.0)
        if score >= max(plate.threshold, anchor - matcher.SLACK):
            matcher.HINTS.put(plate.image, tag, (best_scale, x, y, anchor))
            return ((x, y, score), score)
    _region, half = matcher.region_half(frame, (x0, y0, x1, y1))
    coarse = [(match(half, 0.5, s, 0, 0)[0], s) for s in scales]
    coarse = [c for c in coarse if c[0] > (-2)]
    if not coarse:
        return (None, 0.0)
    else:
        best_coarse, best_scale = max(coarse)
        if (not full) and matcher.hopeless(min(best_coarse, 1.0), plate.threshold):
            matcher.HINTS.drop(plate.image, tag)
            return (None, max(min(best_coarse, 1.0), 0.0))
        else:
            best = ((-1.0), 0, 0)
            for s in matcher.fine_scales(best_scale):
                cand = match(region, 1.0, s, x0, y0)
                if cand[0] > best[0]:
                    best = cand
            score, x, y = best
            score = min(score, 1.0)
            if score >= plate.threshold:
                matcher.HINTS.put(plate.image, tag, (best_scale, x, y, score))
                return ((x, y, score), score)
            else:
                matcher.HINTS.drop(plate.image, tag)
                return (None, max(score, 0.0))


COLOUR_CHECKED = ("play", "storefront_play")
PLAY_AIM_DOWN = 0.15
COLOUR_TOL = 70.0


def _median_colour(img: np.ndarray, mask: Optional[np.ndarray] = None) -> Optional[np.ndarray]:
    px = img.reshape((-1), img.shape[2] if img.ndim == 3 else 1)
    if mask is not None:
        px = px[mask.reshape((-1)) > 0]
    if len(px) < 16:
        return
    else:
        return np.median(px.astype(np.float32), axis=0)


def yellowish(c) -> bool:
    b, g, r = (float(c[0]), float(c[1]), float(c[2]))
    return min(g, r) >= 150 and b <= 0.65 * min(g, r) and abs(g - r) <= 45


def colour_matches(frame: np.ndarray, tpl, centre, tol: float = COLOUR_TOL) -> bool:
    if tpl is None:
        return True
    img = tpl.image if isinstance(tpl, Plate) else tpl
    mask = tpl.mask if isinstance(tpl, Plate) else None
    if img.ndim != 3:
        return True
    th, tw = img.shape[:2]
    fh, fw = frame.shape[:2]
    try:
        x0, y0 = (int(centre[0]) - tw // 2, int(centre[1]) - th // 2)
        x1, y1 = (x0 + tw, y0 + th)
        if x0 < 0 or y0 < 0 or x1 > fw or (y1 > fh):
            return True
        want = _median_colour(img, mask)
        got = _median_colour(frame[y0:y1, x0:x1], mask)
        if want is None or got is None:
            return True
        if yellowish(want):
            return yellowish(got)
        return float(np.linalg.norm(want - got)) <= tol
    except Exception:
        return True


def aim_point(key: str, tpl, m) -> Tuple[int, int]:
    x, y = (int(m[0]), int(m[1]))
    if key == "play" and tpl is not None:
        try:
            h = (tpl.image if isinstance(tpl, Plate) else tpl).shape[0]
            y += int(round(PLAY_AIM_DOWN * h))
        except Exception:
            pass
        return (x, y)
    return (x, y)


def find_checked(frame: np.ndarray, key: str, tpl, find):
    m, score = find(frame)
    if not m or key not in COLOUR_CHECKED:
        return (m, score)
    else:
        img = tpl.image if isinstance(tpl, Plate) else tpl
        th, tw = img.shape[:2] if getattr(img, "ndim", 0) >= 2 else (40, 120)
        work = frame
        for _ in range(3):
            if colour_matches(frame, tpl, m):
                return (m, score)
            else:
                if work is frame:
                    work = frame.copy()
                x, y = (int(m[0]), int(m[1]))
                work[max(0, y - th // 2 - 2) : y + th // 2 + 2, max(0, x - tw // 2 - 2) : x + tw // 2 + 2] = 0
                m, score = find(work)
                if not m:
                    return (None, score)
        return (None, score)
