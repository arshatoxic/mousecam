import cv2
import mediapipe as mp
import pyautogui
import time
import numpy as np
import tkinter as tk
from functools import partial
import threading
import webbrowser
import json
import os
import math
import ctypes
import pyperclip
import keyboard

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.001

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
hands = mp_hands.Hands(
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

screen_width, screen_height = pyautogui.size()

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
ret, frame = cap.read()
frame_height, frame_width = frame.shape[:2] if ret else (720, 1280)

click_delay = 0.2
last_click_time = 0
smooth_x, smooth_y = 0, 0

# فیلتر پیشرفته‌تر برای حذف لرزش (Jitter)
alpha_base = 0.15 

THRESHOLD_CLICK = 0.55  

is_mouse_down = False
finger_closed_start_time = 0
DRAG_THRESHOLD_TIME = 0.4  

keyboard_active = False
radial_window = None
canvas = None
current_hover_char = None

typed_buffer = ""
is_persian = False 

# متغیرهای تنظیم شده برای اسکرول نرم و پویا
scroll_speed_factor = 180  
last_scroll_time = 0
scroll_delay = 0.02        

chars_en = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 
            'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 
            'Space', 'Bksp', 'Fa/En', 'Type', 'Close']

chars_fa = [
    ['آ', 'ا', 'ب', 'پ', 'ت', 'ث', 'ج'],
    ['چ', 'ح', 'خ', 'د', 'ذ', 'ر', 'ز'],
    ['ژ', 'س', 'ش', 'ص', 'ض', 'ط', 'ظ'],
    ['ع', 'غ', 'ف', 'ق', 'ک', 'گ', 'ل'],
    ['م', 'ن', 'و', 'ه', 'ی', 'Space', 'Bksp'],
    ['Fa/En', 'Type', 'Close', '', '', '', '']
]

SETTINGS_FILE = "gesture_settings.json"
gesture_actions = ["none", "none", "none", "none", "none"]
current_status_text = ""
status_text_expiry = 0

if os.path.exists(SETTINGS_FILE):
    try:
        with open(SETTINGS_FILE, "r") as f:
            gesture_actions = json.load(f)
            if len(gesture_actions) < 5:
                gesture_actions += ["none"] * (5 - len(gesture_actions))
    except:
        gesture_actions = ["none", "none", "none", "none", "none"]

def save_settings():
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(gesture_actions, f)
    except:
        pass

def handle_buffer_typing(char):
    global typed_buffer, keyboard_active, is_persian
    if not char: return
    try:
        if char == 'Space':
            typed_buffer += " "
        elif char == 'Bksp':
            typed_buffer = typed_buffer[:-1]
        elif char == 'Fa/En':
            is_persian = not is_persian
        elif char == 'Type':
            pyperclip.copy(typed_buffer)
            typed_buffer = ""
            keyboard_active = False
            radial_window.withdraw() 
            time.sleep(0.08)
            keyboard.press_and_release('ctrl+v')
        elif char == 'Close':
            keyboard_active = False
            radial_window.withdraw()
        else:
            typed_buffer += char.lower() if (char.isalpha() and not is_persian) else char
    except Exception as e:
        print(f"Typing error: {e}")

def init_keyboard_window():
    global radial_window, canvas, win_w, win_h, pos_x, pos_y
    try:
        radial_window = tk.Tk()
        radial_window.title("Virtual Keypad Overlay")
        radial_window.overrideredirect(True)
        radial_window.attributes('-topmost', True)
        radial_window.attributes('-transparentcolor', '#222222') 
        
        win_w, win_h = 500, 520 
        pos_x = (screen_width - win_w) // 2
        pos_y = (screen_height - win_h) // 2
        radial_window.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        hwnd = ctypes.windll.user32.GetParent(radial_window.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)
        
        canvas = tk.Canvas(radial_window, width=win_w, height=win_h, bg='#222222', highlightthickness=0)
        canvas.pack()
        
        radial_window.withdraw() 
        
        def loop_overlay():
            global keyboard_active, current_hover_char, typed_buffer, is_persian
            if keyboard_active:
                try:
                    canvas.delete("all")
                    canvas.create_rectangle(20, 10, win_w - 20, 55, fill="#393E46", outline="#00ADB5", width=2)
                    display_text = typed_buffer if typed_buffer != "" else "...شروع به تایپ کنید"
                    text_color = "#EEEEEE" if typed_buffer != "" else "#888888"
                    canvas.create_text(win_w // 2, 32, text=display_text, fill=text_color, font=("Arial", 12, "bold"), anchor="center")
                    
                    mx, my = pyautogui.position()
                    rx = mx - pos_x
                    ry = my - pos_y
                    detected_hover = None
                    
                    if is_persian:
                        start_y = 80
                        cell_w, cell_h = 60, 55
                        pad_x, pad_y = 7, 7
                        for row_idx, row in enumerate(chars_fa):
                            for col_idx, char in enumerate(row):
                                if not char: continue
                                bx1 = 30 + col_idx * (cell_w + pad_x)
                                by1 = start_y + row_idx * (cell_h + pad_y)
                                bx2 = bx1 + cell_w
                                by2 = by1 + cell_h
                                if (bx1 <= rx <= bx2) and (by1 <= ry <= by2):
                                    detected_hover = char
                                if char == 'Type': btn_fill = "#FFD369" if (bx1 <= rx <= bx2) and (by1 <= ry <= by2) else "#d4a373"
                                elif char == 'Fa/En': btn_fill = "#a2d2ff" if (bx1 <= rx <= bx2) and (by1 <= ry <= by2) else "#57cc99"
                                elif char == 'Close': btn_fill = "#ff4d4d" if (bx1 <= rx <= bx2) and (by1 <= ry <= by2) else "#b33939"
                                else: btn_fill = "#00ADB5" if (bx1 <= rx <= bx2) and (by1 <= ry <= by2) else "#393E46"
                                txt_color = "#000000" if (char in ['Type', 'Fa/En', 'Close'] and (bx1 <= rx <= bx2) and (by1 <= ry <= by2)) else "#FFFFFF"
                                canvas.create_rectangle(bx1, by1, bx2, by2, fill=btn_fill, outline="", width=0)
                                canvas.create_text((bx1+bx2)//2, (by1+by2)//2, text=char, fill=txt_color, font=("Arial", 10, "bold"))
                    else:
                        cx, cy = win_w // 2, (win_h // 2) + 30
                        r_circle = 150
                        canvas.create_oval(cx - r_circle, cy - r_circle, cx + r_circle, cy + r_circle, outline="#00ADB5", width=3)
                        dist = math.hypot(rx - cx, ry - cy)
                        num_chars = len(chars_en)
                        for idx, char in enumerate(chars_en):
                            angle = (2 * math.pi / num_chars) * idx
                            bx = int(cx + r_circle * math.cos(angle))
                            by = int(cy + r_circle * math.sin(angle))
                            is_selected = False
                            if dist > 35:
                                mouse_angle = math.atan2(ry - cy, rx - cx)
                                if mouse_angle < 0: mouse_angle += 2 * math.pi
                                diff = abs(mouse_angle - angle)
                                if diff > math.pi: diff = 2 * math.pi - diff
                                if diff < (math.pi / num_chars):
                                    is_selected = True
                                    detected_hover = char
                            if char == 'Type': btn_fill = "#FFD369" if is_selected else "#d4a373"
                            elif char == 'Fa/En': btn_fill = "#a2d2ff" if is_selected else "#57cc99"
                            elif char == 'Close': btn_fill = "#ff4d4d" if is_selected else "#b33939"
                            else: btn_fill = "#00ADB5" if is_selected else "#393E46"
                            txt_color = "#000000" if (char in ['Type', 'Fa/En', 'Close'] and is_selected) else "#FFFFFF"
                            canvas.create_oval(bx - 16, by - 16, bx + 16, by + 16, fill=btn_fill, outline="")
                            canvas.create_text(bx, by, text=char, fill=txt_color, font=("Arial", 8, "bold"))
                    
                    current_hover_char = detected_hover
                    canvas.create_oval(rx - 5, ry - 5, rx + 5, ry + 5, fill="#FFD369", outline="")
                except Exception as e:
                    print(f"Overlay loop error: {e}")
            radial_window.after(20, loop_overlay) 
            
        radial_window.after(20, loop_overlay)
        radial_window.mainloop()
    except Exception as e:
        print(f"Failed init window: {e}")

threading.Thread(target=init_keyboard_window, daemon=True).start()

def toggle_keyboard():
    global keyboard_active, typed_buffer, radial_window
    if not keyboard_active:
        typed_buffer = ""
        keyboard_active = True
        if radial_window: radial_window.deiconify() 
    else:
        keyboard_active = False
        if radial_window: radial_window.withdraw() 

def _async_execute(action):
    try:
        if action == "open_keyboard": toggle_keyboard()
        elif action == "paste_text":
            time.sleep(0.05); keyboard.press_and_release('ctrl+v')
        elif action == "press_enter":
            time.sleep(0.05); keyboard.press_and_release('enter')
        elif action == "volumeup": pyautogui.press("volumeup")
        elif action == "volumedown": pyautogui.press("volumedown")
        elif action == "close": pyautogui.hotkey("alt", "f4")
        elif action == "minimize": pyautogui.hotkey("win", "down")
        elif action == "open_google": webbrowser.open("https://www.google.com")
        elif action == "open_youtube": webbrowser.open("https://www.youtube.com")
    except Exception as e:
        print(f"Async action error: {e}")

def execute_action(action):
    global current_status_text, status_text_expiry
    if action == "none": return
    current_status_text = f"Action: {action.upper()}"
    status_text_expiry = time.time() + 1.5
    threading.Thread(target=_async_execute, args=(action,), daemon=True).start()

def show_settings_window():
    try:
        def set_action(index, action):
            gesture_actions[index] = action
            save_settings()
            
        root = tk.Tk()
        root.title("تنظیمات حرکات دست")
        root.geometry("340x260")
        root.resizable(False, False)
        root.configure(bg="#F5F5F7")
        root.attributes('-topmost', True)
        
        options = ["none", "open_keyboard", "paste_text", "press_enter", "volumeup", "volumedown", "close", "minimize", "open_google", "open_youtube"]
        fingers = ["شست - اشاره", "شست - وسط", "شست - حلقه", "شست - کوچک", "شست - مچ"]
        
        for i in range(5):
            lbl = tk.Label(root, text=fingers[i], font=("Tahoma", 10), bg="#F5F5F7", fg="#333333")
            lbl.grid(row=i+1, column=0, padx=15, pady=8, sticky="w")
            
            var = tk.StringVar(value=gesture_actions[i])
            
            dropdown = tk.OptionMenu(root, var, *options, command=partial(set_action, i))
            dropdown.config(
                width=16, 
                font=("Arial", 9, "bold"), 
                bg="#FFFFFF", 
                fg="#000000",          
                activebackground="#00ADB5", 
                activeforeground="#FFFFFF",
                highlightthickness=1,
                highlightbackground="#CCCCCC"
            )
            dropdown["menu"].config(bg="#FFFFFF", fg="#000000", activebackground="#00ADB5", activeforeground="#FFFFFF")
            dropdown.grid(row=i+1, column=1, padx=15, pady=8)
            
        root.mainloop()
    except Exception as e: 
        print(f"Settings UI Error: {e}")

threading.Thread(target=show_settings_window, daemon=True).start()

active_area = {
    'x_start': int(frame_width * 0.15),
    'x_end': int(frame_width * 0.85),
    'y_start': int(frame_height * 0.15),
    'y_end': int(frame_height * 0.85)
}

def draw_distance_line(img, pt1, pt2, rel_dist, threshold):
    color = (0, 255, 0) if rel_dist < threshold else (0, 0, 255)
    cv2.line(img, pt1, pt2, color, 2)

while cap.isOpened():
    try:
        ret, frame = cap.read()
        if not ret: continue
        frame = cv2.flip(frame, 1)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(frame_rgb)

        cv2.rectangle(frame, (active_area['x_start'], active_area['y_start']), 
                      (active_area['x_end'], active_area['y_end']), (0, 255, 255), 1)

        if results.multi_hand_landmarks:
            for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                label = handedness.classification[0].label
                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                wrist = hand_landmarks.landmark[0]
                index_base = hand_landmarks.landmark[5] 
                thumb_tip = hand_landmarks.landmark[4]
                index_tip = hand_landmarks.landmark[8]
                middle_tip = hand_landmarks.landmark[12]
                ring_tip = hand_landmarks.landmark[16]
                pinky_tip = hand_landmarks.landmark[20]

                p_thumb = (int(thumb_tip.x * frame_width), int(thumb_tip.y * frame_height))
                p_index = (int(index_tip.x * frame_width), int(index_tip.y * frame_height))
                p_middle = (int(middle_tip.x * frame_width), int(middle_tip.y * frame_height))
                p_ring = (int(ring_tip.x * frame_width), int(ring_tip.y * frame_height))
                p_pinky = (int(pinky_tip.x * frame_width), int(pinky_tip.y * frame_height))

                hand_scale = np.hypot(index_base.x - wrist.x, index_base.y - wrist.y)
                if hand_scale == 0: hand_scale = 0.1

                rel_index = np.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y) / hand_scale
                rel_middle = np.hypot(thumb_tip.x - middle_tip.x, thumb_tip.y - middle_tip.y) / hand_scale
                rel_ring = np.hypot(thumb_tip.x - ring_tip.x, thumb_tip.y - ring_tip.y) / hand_scale
                rel_pinky = np.hypot(thumb_tip.x - pinky_tip.x, thumb_tip.y - pinky_tip.y) / hand_scale

                draw_distance_line(frame, p_thumb, p_index, rel_index, THRESHOLD_CLICK)
                draw_distance_line(frame, p_thumb, p_middle, rel_middle, THRESHOLD_CLICK)
                draw_distance_line(frame, p_thumb, p_ring, rel_ring, THRESHOLD_CLICK)
                draw_distance_line(frame, p_thumb, p_pinky, rel_pinky, THRESHOLD_CLICK)

                if label == "Right":
                    x = int(wrist.x * frame_width)
                    y = int(wrist.y * frame_height)
                    
                    if keyboard_active:
                        target_x = np.interp(x, [active_area['x_start'], active_area['x_end']], [(screen_width // 2) - 220, (screen_width // 2) + 220])
                        target_y = np.interp(y, [active_area['y_start'], active_area['y_end']], [(screen_height // 2) - 200, (screen_height // 2) + 220])
                    else:
                        target_x = np.interp(x, [active_area['x_start'], active_area['x_end']], [0, screen_width])
                        target_y = np.interp(y, [active_area['y_start'], active_area['y_end']], [0, screen_height])
                    
                    # فیلتر حذف لرزش (Jitter) پویا
                    distance = np.hypot(target_x - smooth_x, target_y - smooth_y)
                    dynamic_alpha = alpha_base + (0.25 * (distance / 200.0))
                    dynamic_alpha = np.clip(dynamic_alpha, alpha_base, 0.6)
                    
                    if smooth_x == 0 and smooth_y == 0:
                        smooth_x, smooth_y = target_x, target_y
                    else:
                        smooth_x = smooth_x + dynamic_alpha * (target_x - smooth_x)
                        smooth_y = smooth_y + dynamic_alpha * (target_y - smooth_y)
                    
                    pyautogui.moveTo(np.clip(smooth_x, 0, screen_width), np.clip(smooth_y, 0, screen_height))

                    if rel_index < THRESHOLD_CLICK:
                        if finger_closed_start_time == 0:
                            finger_closed_start_time = time.time()
                        
                        if not keyboard_active and not is_mouse_down and (time.time() - finger_closed_start_time > DRAG_THRESHOLD_TIME):
                            pyautogui.mouseDown()
                            is_mouse_down = True
                    else:
                        if is_mouse_down:
                            pyautogui.mouseUp()
                            is_mouse_down = False
                        elif finger_closed_start_time > 0 and (time.time() - finger_closed_start_time <= DRAG_THRESHOLD_TIME):
                            if time.time() - last_click_time > click_delay:
                                last_click_time = time.time()
                                if keyboard_active and current_hover_char:
                                    handle_buffer_typing(current_hover_char)
                                elif not keyboard_active:
                                    pyautogui.click()
                        
                        finger_closed_start_time = 0

                    # 🟢 بخش اسکرول نرم و هوشمند سازی شده بر اساس میزان فاصله انگشتان
                    if not keyboard_active:
                        current_time = time.time()
                        if current_time - last_scroll_time > scroll_delay:
                            # اسکرول به بالا (هرچه انگشت شست و حلقه بهم نزدیک‌تر شوند، سرعت بیشتر می‌شود)
                            if rel_ring < THRESHOLD_CLICK:
                                scroll_amount = int((THRESHOLD_CLICK - rel_ring) * scroll_speed_factor)
                                pyautogui.scroll(max(1, scroll_amount))
                                last_scroll_time = current_time
                                
                            # اسکرول به پایین (هرچه انگشت شست و کوچک بهم نزدیک‌تر شوند، سرعت بیشتر می‌شود)
                            elif rel_pinky < THRESHOLD_CLICK:
                                scroll_amount = int((THRESHOLD_CLICK - rel_pinky) * scroll_speed_factor)
                                pyautogui.scroll(-max(1, scroll_amount))
                                last_scroll_time = current_time

                            # کلیک راست (با انگشت وسط)
                            if rel_middle < THRESHOLD_CLICK and current_time - last_click_time > click_delay:
                                pyautogui.click(button='right')
                                last_click_time = current_time

                elif label == "Left":
                    gesture_detected = None
                    if rel_index < THRESHOLD_CLICK: gesture_detected = 0
                    elif rel_middle < THRESHOLD_CLICK: gesture_detected = 1
                    elif rel_ring < THRESHOLD_CLICK: gesture_detected = 2
                    elif rel_pinky < THRESHOLD_CLICK: gesture_detected = 3

                    if gesture_detected is not None and gesture_detected < len(gesture_actions):
                        action_to_run = gesture_actions[gesture_detected]
                        if action_to_run != "none" and time.time() - last_click_time > 0.8:
                            execute_action(action_to_run)
                            last_click_time = time.time()

        if time.time() < status_text_expiry:
            cv2.putText(frame, current_status_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

        cv2.imshow("Hand Control System", frame)
        if cv2.waitKey(1) & 0xFF == 27: break
        
        # کنترل فریم ریت ناچیز جهت بهینه‌سازی پردازنده و پایداری اسکرول
        time.sleep(0.005)
        
    except Exception as main_err:
        time.sleep(0.01) 
        continue

cap.release()
cv2.destroyAllWindows()
hands.close()