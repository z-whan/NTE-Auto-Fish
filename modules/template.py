import cv2
import os
import numpy as np
from modules.logger import logger
from modules.settings import APP_DIR

class Template:
    def __init__(self, filename: str, masked=False, search_rect=None):
        self.name = os.path.basename(filename).split('.')[0]
        self.masked = masked
        self.search_rect = search_rect
        img = cv2.imread(filename, cv2.IMREAD_UNCHANGED)
        if img is None:
            logger.error(f"Failed to load template: {filename}")
            raise FileNotFoundError(f"Template file not found: {filename}")
        alpha = img[:, :, 3]
        coords = cv2.findNonZero(alpha)
        x, y, w, h = cv2.boundingRect(coords)
        self.rect = (x, y, w, h)
        cropped_img = img[y:y+h, x:x+w, :3]
        cropped_alpha = alpha[y:y+h, x:x+w]
        gray_img = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2GRAY)
        _, self.image = cv2.threshold(gray_img, 200, 255, cv2.THRESH_BINARY)
        # Match only the bright visible strokes, not the changing background.
        self.mask = np.where((cropped_alpha > 0) & (self.image > 0), 255, 0).astype("uint8")
        if cv2.countNonZero(self.mask) == 0:
            self.mask = np.where(cropped_alpha > 0, 255, 0).astype("uint8")
        logger.debug(f"Loaded template '{self.name}' with rect {self.rect}.")

    def __str__(self):
        return self.name
    
    def match(self, screenshot, offset=10, similarity=0.85):
        if screenshot is None or self.image is None:
            return False
            
        x, y, w, h = self.rect
        
        h_img, w_img = screenshot.shape[:2]
        if self.search_rect:
            sx, sy, sw, sh = self.search_rect
            x1 = max(0, sx)
            y1 = max(0, sy)
            x2 = min(w_img, sx + sw)
            y2 = min(h_img, sy + sh)
        else:
            x1 = max(0, x - offset)
            y1 = max(0, y - offset)
            x2 = min(w_img, x + w + offset)
            y2 = min(h_img, y + h + offset)
        
        roi = screenshot[y1:y2, x1:x2]
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, roi_bin = cv2.threshold(roi_gray, 200, 255, cv2.THRESH_BINARY)
            
        if self.masked:
            res = cv2.matchTemplate(roi_bin, self.image, cv2.TM_CCORR_NORMED, mask=self.mask)
        else:
            res = cv2.matchTemplate(roi_bin, self.image, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if not np.isnan(max_val) and max_val >= similarity:
            logger.debug(f"Matched {self.name}: similarity={max_val:.3f}, pos=({x1 + max_loc[0]}, {y1 + max_loc[1]})")
        
        return not np.isnan(max_val) and max_val >= similarity



TEMPLATE_DIR = os.path.join(APP_DIR, "assets", "templates")

TAKE_BAIT = Template(os.path.join(TEMPLATE_DIR, "TAKE_BAIT.png"), search_rect=(360, 175, 580, 90))
HOOK = Template(os.path.join(TEMPLATE_DIR, "HOOK.png"), masked=True)
CLICK_BLANK = Template(os.path.join(TEMPLATE_DIR, "CLICK_BLANK.png"))
