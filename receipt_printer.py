"""Renders a checkout receipt in the Inspire brand fonts and sends it to the
thermal receipt printer over a raw CUPS queue (see README for setup: the
printer has no Linux driver, so it's registered as a driver-less "raw" queue
and we send it ESC/POS bytes directly).

Printing is always best-effort: a printer being off/unplugged/not configured
must never block a checkout. print_receipt() never raises.
"""
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from escpos.printer import Dummy

BASE_DIR = Path(__file__).parent
FONT_DIR = BASE_DIR / "static" / "fonts"
LOGO_SOURCE = BASE_DIR / "photos" / "image.png"
ICON_BBOX = (292, 179, 554, 383)  # cup+book icon only — the source PNG also
                                  # bakes the wordmark into the bitmap, which
                                  # we re-render ourselves below in crisp vector fonts

WIDTH = 576  # 80mm paper @ 203dpi
MARGIN = 28
PRINTER_QUEUE = "POS80"

STATUS_LABELS = {"not_subscribed": "Not subscribed", "weekly": "Weekly", "monthly": "Monthly"}

_title_font = ImageFont.truetype(str(FONT_DIR / "PlayfairDisplay-SemiBold.ttf"), 70)
_subtitle_font = ImageFont.truetype(str(FONT_DIR / "Montserrat-Regular.ttf"), 20)
_body_font = ImageFont.truetype(str(FONT_DIR / "Montserrat-Regular.ttf"), 24)
_small_font = ImageFont.truetype(str(FONT_DIR / "Montserrat-Regular.ttf"), 18)
_measure = ImageDraw.Draw(Image.new("L", (1, 1)))


def _text_extent(text, font):
    """Exact (top, bottom) glyph extent for THIS string in THIS font — a generic
    sample string estimate can clip glyphs that extend further than the sample did."""
    bbox = _measure.textbbox((0, 0), text, font=font)
    return bbox[1], bbox[3]


class _ReceiptCanvas:
    def __init__(self):
        self.segments = []

    def _new(self, h):
        return Image.new("L", (WIDTH, max(1, h)), 255)

    def add_gap(self, h):
        self.segments.append(self._new(h))

    def add_centered_text(self, text, font, tracking=0, pad_top=6, pad_bottom=6):
        if tracking:
            widths = [_measure.textlength(c, font=font) for c in text]
            total_w = sum(widths) + tracking * (len(text) - 1)
        else:
            total_w = _measure.textlength(text, font=font)
        top, bottom = _text_extent(text, font)
        img = self._new((bottom - top) + pad_top + pad_bottom)
        d = ImageDraw.Draw(img)
        x = (WIDTH - total_w) / 2
        y = pad_top - top
        if tracking:
            cx = x
            for c, w in zip(text, widths):
                d.text((cx, y), c, font=font, fill=0)
                cx += w + tracking
        else:
            d.text((x, y), text, font=font, fill=0)
        self.segments.append(img)

    def add_left_text(self, text, font, pad_top=3, pad_bottom=3):
        top, bottom = _text_extent(text, font)
        img = self._new((bottom - top) + pad_top + pad_bottom)
        d = ImageDraw.Draw(img)
        d.text((MARGIN, pad_top - top), text, font=font, fill=0)
        self.segments.append(img)

    def add_row(self, label, value, font=_body_font, pad_top=6, pad_bottom=6):
        ltop, lbottom = _text_extent(label, font)
        vtop, vbottom = _text_extent(value, font)
        top, bottom = min(ltop, vtop), max(lbottom, vbottom)
        img = self._new((bottom - top) + pad_top + pad_bottom)
        d = ImageDraw.Draw(img)
        y = pad_top - top
        d.text((MARGIN, y), label, font=font, fill=0)
        vw = d.textlength(value, font=font)
        d.text((WIDTH - MARGIN - vw, y), value, font=font, fill=0)
        self.segments.append(img)

    def add_separator(self, pad_top=10, pad_bottom=10, thickness=2):
        img = self._new(thickness + pad_top + pad_bottom)
        d = ImageDraw.Draw(img)
        d.line([(0, pad_top), (WIDTH, pad_top)], fill=0, width=thickness)
        self.segments.append(img)

    def compose(self):
        total_h = sum(s.height for s in self.segments)
        img = self._new(total_h)
        y = 0
        for s in self.segments:
            img.paste(s, (0, y))
            y += s.height
        return img


def _logo_icon():
    logo = Image.open(LOGO_SOURCE).convert("L")
    pad = 20
    l, t, r, b = ICON_BBOX
    icon = logo.crop((l - pad, t - pad, r + pad, b + pad))
    icon.thumbnail((320, 320))
    return icon.point(lambda px: 0 if px < 160 else 255)


def build_receipt_image(receipt: dict) -> Image.Image:
    c = _ReceiptCanvas()

    try:
        icon = _logo_icon()
        canvas = Image.new("L", (WIDTH, icon.height), 255)
        canvas.paste(icon, ((WIDTH - icon.width) // 2, 0))
        c.segments.append(canvas)
        c.add_gap(4)
    except Exception:
        pass  # logo is decorative — never let it block a print

    c.add_centered_text("INSPIRE", _title_font, pad_top=0, pad_bottom=4)
    c.add_centered_text("WORKSPACE & CAFE", _subtitle_font, tracking=6, pad_top=0, pad_bottom=10)
    c.add_separator()

    customer = receipt["customer"]
    c.add_left_text(f"{customer['first_name']} {customer['last_name']}", _body_font)
    c.add_left_text(customer["phone"], _small_font)
    c.add_left_text(f"Status: {STATUS_LABELS.get(customer['status'], customer['status'])}", _small_font, pad_bottom=8)
    c.add_separator()

    c.add_row(f"Time charge ({receipt['billed_hours']}h billed)", f"{receipt['time_cost']} LE")
    c.add_separator()

    for item in receipt["items"]:
        c.add_row(f"{item['qty']} x {item['name']}", f"{item['line_total']} LE")
        c.add_separator()

    c.add_row("TOTAL", f"{receipt['total_cost']} LE")
    c.add_separator()

    c.add_gap(4)
    c.add_centered_text(receipt.get("check_out", ""), _small_font, pad_top=0, pad_bottom=4)
    c.add_centered_text("Thank you!", _body_font, pad_top=0, pad_bottom=10)

    return c.compose()


def print_receipt(receipt: dict) -> tuple[bool, str]:
    """Best-effort print — builds the receipt image and sends it to the CUPS
    'POS80' raw queue. Never raises; always returns (success, message)."""
    try:
        img = build_receipt_image(receipt)
        p = Dummy()
        p.image(img)
        p.text("\n\n\n")
        p.cut()

        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(p.output)
            tmp_path = f.name

        try:
            result = subprocess.run(
                ["lp", "-d", PRINTER_QUEUE, "-o", "raw", tmp_path],
                capture_output=True, text=True, timeout=15,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "Print job was rejected").strip()
        return True, "Sent to printer"
    except FileNotFoundError:
        return False, "Printing is not set up on this machine (CUPS 'lp' command not found)"
    except Exception as e:
        return False, str(e)
