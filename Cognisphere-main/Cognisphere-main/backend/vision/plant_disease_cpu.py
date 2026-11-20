"""
Plant Disease Detector - CPU only, NO training, free models.

Pipeline:
  1. PHOTO QUALITY CHECK   - refuses blurry / dark / bright / tiny photos (numpy + Pillow, no OpenCV)
  2. AUTO CROP             - finds the leaf / sick patch and zooms into it
  3. YOLO DISEASE MODEL    - 116 diseases across many crops (whole-India coverage)
  4. SECOND OPINION        - EfficientNet classifier (apple, tomato, corn only);
                             used ONLY when the YOLO result is one of those crops
  5. VOTING                - answers only if the models agree, else "UNCERTAIN"
  6. TTA                   - every model sees 6 flipped/rotated views

Install (CPU only):
    pip install ultralytics huggingface_hub pillow transformers

Run:
    python plant_disease_cpu.py leaf.jpg
    python plant_disease_cpu.py leaf.jpg --force        # skip the quality check
    python plant_disease_cpu.py leaf.jpg --yolo my.pt   # use your own YOLO weights

Change from the original: this file no longer imports cv2 itself, so it always loads.
(ultralytics still needs OpenCV internally; if that is blocked, load_yolo() returns []
and LAST_YOLO_ERROR says why, instead of the whole file failing to import.)

No AI is 100% accurate. Confirm serious cases with a local KVK / agriculture officer.
"""

import argparse
import collections
import os
import re
import sys

os.environ["CUDA_VISIBLE_DEVICES"] = ""  # force CPU

import numpy as np
from PIL import Image, ImageOps

# ------------------------------------------------------------------ settings
# 116 classes, many crops. If you put the downloaded weights next to this script as best.pt,
# that local file is used and nothing is downloaded.
_LOCAL_WEIGHTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "best.pt")
YOLO_MODELS = ([_LOCAL_WEIGHTS] if os.path.exists(_LOCAL_WEIGHTS)
               else ["Ananthakrishnanmzen/PlantDiseaseDetection"])
CLASSIFIER_REPO = "Abuzaid01/plant-disease-classifier"        # apple, tomato, corn only
CLASSIFIER_CROPS = {"apple", "tomato", "corn"}

# photo quality limits
MIN_SIDE = 224          # px, shortest side
MIN_SHARPNESS = 60.0    # Laplacian variance (on a 640px-wide copy)
MIN_BRIGHTNESS = 55     # mean gray level 0-255
MAX_BRIGHTNESS = 215
MIN_CONTRAST = 25       # std of gray level

# decision limits
MIN_CONFIDENCE = 0.50
MIN_AGREEMENT = 0.50
MIN_MARGIN = 0.10
CLASSIFIER_MIN_PROB = 0.50

GENERIC_WORDS = {"leaf", "leaves", "disease", "plant", "the", "of", "and"}

LAST_YOLO_ERROR = ""    # filled by load_yolo() when no model could be loaded


# ------------------------------------------------------------- 1. quality
def check_quality(img):
    """Return a list of problems (empty list = photo is good enough)."""
    problems = []
    w, h = img.size
    if min(w, h) < MIN_SIDE:
        problems.append(f"too small ({w}x{h}px) - use at least {MIN_SIDE}px on the short side")

    gray_img = img.convert("L")
    scale = 640.0 / max(gray_img.size)
    if scale < 1:
        gray_img = gray_img.resize((max(1, int(gray_img.width * scale)),
                                    max(1, int(gray_img.height * scale))), Image.BOX)
    g = np.asarray(gray_img, dtype=np.float64)
    # Laplacian (same 3x3 kernel OpenCV uses): up + down + left + right - 4*centre
    lap = g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4 * g[1:-1, 1:-1]

    sharp = float(lap.var())
    bright = float(g.mean())
    contrast = float(g.std())

    if sharp < MIN_SHARPNESS:
        problems.append(f"too blurry (sharpness {sharp:.0f}, need {MIN_SHARPNESS:.0f}+) - hold steady, tap to focus")
    if bright < MIN_BRIGHTNESS:
        problems.append(f"too dark (brightness {bright:.0f}) - use daylight, avoid shadow")
    elif bright > MAX_BRIGHTNESS:
        problems.append(f"too bright / overexposed (brightness {bright:.0f}) - avoid direct glare")
    if contrast < MIN_CONTRAST:
        problems.append(f"flat / washed out (contrast {contrast:.0f}) - move closer to the leaf")
    return problems


# ------------------------------------------------------------- helpers
def views(img):
    img = img.convert("RGB")
    return [
        img,
        ImageOps.mirror(img),
        ImageOps.flip(img),
        img.rotate(90, expand=True),
        img.rotate(180, expand=True),
        img.rotate(270, expand=True),
    ]


def pretty(label):
    return label.replace("___", " - ").replace("_", " ")


def norm_tokens(label):
    t = set(re.findall(r"[a-z]+", label.lower()))
    if "maize" in t:
        t.discard("maize")
        t.add("corn")
    return t


def crop_of(label):
    t = norm_tokens(label)
    for c in CLASSIFIER_CROPS:
        if c in t:
            return c
    return None


def same_diagnosis(a, b):
    """True if two label strings from different models mean the same thing."""
    ta, tb = norm_tokens(a), norm_tokens(b)
    if not (crop_of(a) and crop_of(a) == crop_of(b)):
        return False
    if ("healthy" in ta) or ("healthy" in tb):
        return ("healthy" in ta) and ("healthy" in tb)
    da = ta - GENERIC_WORDS - CLASSIFIER_CROPS
    db = tb - GENERIC_WORDS - CLASSIFIER_CROPS
    # one description must contain the other, e.g. {blight} fits {northern, blight},
    # but {late, blight} and {early, blight} do not match
    if not da or not db:
        return False
    return da <= db or db <= da


# ------------------------------------------------------------- loading
def load_yolo(specs):
    """Load YOLO models. Returns [] (and sets LAST_YOLO_ERROR) instead of raising."""
    global LAST_YOLO_ERROR
    LAST_YOLO_ERROR = ""
    try:
        from huggingface_hub import hf_hub_download, list_repo_files
        from ultralytics import YOLO
    except Exception as e:               # e.g. OpenCV DLL blocked by Windows policy
        LAST_YOLO_ERROR = f"ultralytics could not be imported: {type(e).__name__}: {e}"
        print(f"[skip] {LAST_YOLO_ERROR}")
        return []

    models, errors = [], []
    for spec in specs:
        try:
            if os.path.exists(spec):
                path = spec
            else:
                repo, _, fname = spec.partition(":")
                if not fname:
                    pts = [f for f in list_repo_files(repo) if f.endswith(".pt")]
                    if not pts:
                        raise FileNotFoundError("no .pt weights file found in this repo")
                    fname = next((f for f in pts if f.split("/")[-1] == "best.pt"), pts[0])
                    print(f"[info] {repo}: using weights file {fname}")
                path = hf_hub_download(repo, fname)
            m = YOLO(path)
            m.to("cpu")
            models.append(m)
            print(f"[ok] YOLO model loaded: {spec}")
        except Exception as e:
            errors.append(f"{spec}: {type(e).__name__}: {e}")
            print(f"[skip] YOLO {spec}: {type(e).__name__}: {e}")
    if not models:
        LAST_YOLO_ERROR = "; ".join(errors) or "no YOLO model specified"
    return models


def load_classifier(repo):
    try:
        import torch
        import torchvision.transforms as T
        from transformers import AutoModelForImageClassification

        try:
            model = AutoModelForImageClassification.from_pretrained(repo)
        except Exception:
            model = AutoModelForImageClassification.from_pretrained(repo, trust_remote_code=True)
        model.eval()
        tf = T.Compose([
            T.Resize(256), T.CenterCrop(224), T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        print(f"[ok] second-opinion classifier loaded: {repo}")
        return model, tf, torch
    except Exception as e:
        print(f"[skip] classifier {repo}: {type(e).__name__}: {e}")
        return None


# ------------------------------------------------------------- inference
def yolo_scores(model, image, imgsz):
    """Return ({label: confidence}, result, [(conf, xyxy), ...])."""
    r = model.predict(image, imgsz=imgsz, conf=0.15, device="cpu", verbose=False)[0]
    names, scores, boxes = r.names, {}, []
    if r.probs is not None:
        for i, v in enumerate(r.probs.data.cpu().tolist()):
            scores[names[i]] = v
    elif r.boxes is not None and len(r.boxes):
        for c, s, xy in zip(r.boxes.cls.cpu().tolist(), r.boxes.conf.cpu().tolist(),
                            r.boxes.xyxy.cpu().tolist()):
            n = names[int(c)]
            scores[n] = max(scores.get(n, 0.0), s)
            boxes.append((s, xy))
    return scores, r, boxes


def auto_crop(model, img, imgsz):
    """Zoom into the most confident detection. Returns (image, was_cropped, annotated_result)."""
    _, res, boxes = yolo_scores(model, img, imgsz)
    if not boxes:
        return img, False, res
    conf, (x1, y1, x2, y2) = max(boxes, key=lambda b: b[0])
    w, h = img.size
    if conf < 0.25 or ((x2 - x1) * (y2 - y1)) > 0.85 * w * h:
        return img, False, res  # already close-up, or detection too weak
    pad_x, pad_y = 0.15 * (x2 - x1), 0.15 * (y2 - y1)
    box = (max(0, x1 - pad_x), max(0, y1 - pad_y), min(w, x2 + pad_x), min(h, y2 + pad_y))
    crop = img.crop(tuple(int(v) for v in box))
    if min(crop.size) < 64:
        return img, False, res
    return crop, True, res


def yolo_vote(models, img, imgsz):
    total = collections.defaultdict(float)
    votes = collections.Counter()
    runs = 0
    for m in models:
        for v in views(img):
            scores, _, _ = yolo_scores(m, v, imgsz)
            runs += 1
            for k, s in scores.items():
                total[k] += s
            if scores:
                votes[max(scores, key=scores.get)] += 1
    ranked = sorted(((k, s / runs) for k, s in total.items()), key=lambda x: -x[1])[:3]
    return ranked, votes, runs


def classifier_vote(clf, img):
    model, tf, torch = clf
    total, n = None, 0
    with torch.no_grad():
        for v in views(img):
            logits = model(tf(v).unsqueeze(0)).logits
            p = torch.softmax(logits, dim=1)[0]
            total = p if total is None else total + p
            n += 1
    probs = total / n
    i = int(torch.argmax(probs))
    return model.config.id2label[i], float(probs[i])


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--yolo", nargs="*", default=YOLO_MODELS, help="repo ids or local .pt files")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--force", action="store_true", help="analyse even if photo quality is poor")
    ap.add_argument("--out", default="result.jpg")
    a = ap.parse_args()

    img = ImageOps.exif_transpose(Image.open(a.image)).convert("RGB")

    # 1. quality gate
    problems = check_quality(img)
    if problems:
        print("\nPHOTO QUALITY PROBLEM:")
        for p in problems:
            print("  -", p)
        if not a.force:
            print("\nNot analysed, because a poor photo gives wrong answers. Retake it, or use --force.")
            return 1
        print("  (continuing because of --force; treat the result with extra caution)")
    else:
        print("[ok] photo quality is good")

    # 2. load models
    yolos = load_yolo(a.yolo)
    if not yolos:
        sys.exit(f"No YOLO model could be loaded: {LAST_YOLO_ERROR}")

    # 3. auto-crop
    work, cropped, res = auto_crop(yolos[0], img, a.imgsz)
    if cropped:
        work.save("crop.jpg")
        print("[ok] zoomed into the detected leaf/patch (saved crop.jpg)")
    else:
        print("[info] no clear region to crop; using the whole photo")

    # 4. YOLO ensemble
    ranked, votes, runs = yolo_vote(yolos, work, a.imgsz)
    print("\n=== RESULT ===")
    if not ranked:
        print("No plant disease or plant detected. Take a closer, clear photo of the leaf.")
        return 0

    best, score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    agreement = votes[best] / runs
    sure = score >= MIN_CONFIDENCE and agreement >= MIN_AGREEMENT and (score - second) >= MIN_MARGIN

    # 5. second opinion (only where that model has knowledge)
    second_line = None
    if crop_of(best):
        clf = load_classifier(CLASSIFIER_REPO)
        if clf:
            label, prob = classifier_vote(clf, work)
            second_line = f"Second model says: {pretty(label)} ({prob*100:.0f}%)"
            if prob < CLASSIFIER_MIN_PROB or not same_diagnosis(best, label):
                sure = False
                second_line += "  <-- DISAGREES with the main model"
            else:
                second_line += "  <-- agrees"
    else:
        print("[info] second-opinion model only knows apple, tomato and corn; skipped for this crop")

    if not sure:
        print("UNCERTAIN - the models are not sure or do not agree.")
        print("Retake a close, sharp, daylight photo of the affected part, or ask an expert.")
    elif "healthy" in best.lower():
        print(f"HEALTHY: {pretty(best)}")
    else:
        print(f"DISEASE DETECTED: {pretty(best)}")

    print(f"Agreement across views: {agreement*100:.0f}% of {runs} checks")
    print("Top candidates:")
    for k, s in ranked:
        print(f"  {pretty(k)}: {s*100:.1f}%")
    if second_line:
        print(second_line)

    try:
        Image.fromarray(res.plot()[:, :, ::-1]).save(a.out)      # BGR -> RGB
        print(f"Annotated image saved to {a.out}")
    except Exception:
        pass

    print("\nNote: no AI is 100% accurate. Confirm with a local KVK / agriculture officer before spraying.")
    return 0


if __name__ == "__main__":
    sys.exit(main())