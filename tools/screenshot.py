import cv2
import os
from datetime import datetime
from modules.controller import Controller

controller = Controller()

save_dir = 'screenshots'
if not os.path.exists(save_dir):
    os.makedirs(save_dir)

def save_screenshot(frame):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = os.path.join(save_dir, f'capture_{timestamp}.png')
    cv2.imwrite(filename, frame)

for frame in controller.loop(interval=1):
    if frame is not None:
        save_screenshot(frame)