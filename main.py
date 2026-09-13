import json
import os
import random
import time
import math
import hashlib
import threading
import urllib.request
import urllib.error

# ================================================================
# ПРИНУДИТЕЛЬНАЯ АППАРАТНАЯ ВЕРТИКАЛЬНАЯ СИНХРОНИЗАЦИЯ (VSYNC)
# ================================================================
os.environ['KIVY_GRAPHICS_VSYNC'] = '1'

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle, Ellipse, Line, InstructionGroup
from kivy.metrics import dp
from kivy.animation import Animation
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.widget import Widget
from kivy.uix.accordion import Accordion, AccordionItem
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform as kivy_platform

Window.softinput_mode = "below_target"

try:
    import psutil
    HAS_PSUTIL = True
except Exception:
    HAS_PSUTIL = False


ADMIN_HASH = "963d7fc8d5260a77ec08ef89fda5d170eadbfa67391b79ff352feeffb77c7701"

def verify_admin_code(code: str) -> bool:
    return hashlib.sha256(code.strip().encode('utf-8')).hexdigest() == ADMIN_HASH


# ================================================================
# ДЕТЕКЦИЯ ГЕРЦОВКИ И УСТРОЙСТВА
# ================================================================

_CACHED_HZ = None

def get_screen_refresh_rate():
    global _CACHED_HZ
    if _CACHED_HZ:
        return _CACHED_HZ
    try:
        if kivy_platform == "android":
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            windowManager = activity.getWindowManager()
            display = windowManager.getDefaultDisplay()
            rate = int(display.getRefreshRate())
            _CACHED_HZ = rate if rate > 0 else 60
        else:
            _CACHED_HZ = 60
    except Exception:
        _CACHED_HZ = 60
    return _CACHED_HZ


# ================================================================
# УРОВЕНЬ КАЧЕСТВА ЭФФЕКТОВ (ЧТОБЫ НЕ САДИТЬ ФПС НА СЛАБЫХ ЭКРАНАХ)
# ================================================================

_FX_TIER = None

def get_fx_tier():
    """
    'high'   — экраны 90Hz+ или ПК: полный набор доп. свечений/искр.
    'medium' — обычные 60Hz экраны: свечения есть, но легче.
    'low'    — псутил показывает сильную нагрузку CPU или <60Hz: только база.
    Считается один раз и кэшируется, чтобы не бить по FPS самим замером.
    """
    global _FX_TIER
    if _FX_TIER:
        return _FX_TIER
    hz = get_screen_refresh_rate()
    if hz >= 90:
        _FX_TIER = "high"
    elif hz >= 60:
        _FX_TIER = "medium"
    else:
        _FX_TIER = "low"
    return _FX_TIER

def get_device_name():
    try:
        if kivy_platform == "android":
            from jnius import autoclass
            Build = autoclass("android.os.Build")
            man = str(Build.MANUFACTURER).strip().title()
            model = str(Build.MODEL).strip()
            if man.lower() in model.lower():
                return model
            return f"{man} {model}"
        else:
            import platform as pyplat
            return f"{pyplat.system()} • {pyplat.node() or 'PC'}"
    except Exception:
        return "Неизвестное устройство"


# ================================================================
# МЕНЕДЖЕР СОХРАНЕНИЙ И ПОЛНОГО СБРОСА
# ================================================================

class SaveManager:
    SAVE_FILE = "blocks_stafn_save.json"
    _cache = None

    @classmethod
    def get_default_data(cls):
        hz = get_screen_refresh_rate()
        return {
            "best_score": 0,
            "bg_theme": "Сакура",
            "max_fps": hz,
            "block_palette": "Неон",
            "block_style": "Стеклянный Взрыв",
            "blocksy": 0,
            "owned_sticks": 10,
            "unlocked_themes": ["Сакура", "Зима", "Горы & Ветер", "Тёмная"],
            "unlocked_styles": ["Стеклянный Взрыв", "Классика 3D", "Глянец", "Киберпанк"],
            "god_mode": False,
            "player_name": "",
            "leaderboard": [],
            "leaderboard_url": ""
        }

    @classmethod
    def load_data(cls):
        if cls._cache is not None:
            return cls._cache
        default = cls.get_default_data()
        if not os.path.exists(cls.SAVE_FILE):
            cls._cache = default
            return cls._cache
        try:
            with open(cls.SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cls._cache = {**default, **data}
            cls._migrate_styles(cls._cache)
        except Exception:
            cls._cache = default
        return cls._cache

    @classmethod
    def _migrate_styles(cls, data):
        old = "iOS Glass 26"
        new = "Стеклянный Взрыв"
        if data.get("block_style") == old:
            data["block_style"] = new
        styles = list(data.get("unlocked_styles", []))
        styles = [new if s == old else s for s in styles]
        if new not in styles:
            styles.insert(0, new)
        data["unlocked_styles"] = styles

    @classmethod
    def save_data(cls, data):
        cls._cache = data
        try:
            with open(cls.SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @classmethod
    def reset_progress(cls):
        default = cls.get_default_data()
        cls.save_data(default)
        return default

    @classmethod
    def set_player_name(cls, name: str):
        name = (name or "").strip()[:16]
        if not name:
            name = "Игрок"
        data = cls.load_data()
        data["player_name"] = name
        cls.save_data(data)
        return name

    @classmethod
    def get_player_name(cls):
        data = cls.load_data()
        return (data.get("player_name") or "").strip()

    @classmethod
    def add_leaderboard_score(cls, name: str, score: int):
        name = (name or "Игрок").strip()[:16] or "Игрок"
        score = int(max(0, score))
        data = cls.load_data()
        board = list(data.get("leaderboard") or [])
        board.append({"name": name, "score": score})
        board.sort(key=lambda e: int(e.get("score", 0)), reverse=True)
        data["leaderboard"] = board[:15]
        cls.save_data(data)
        # Параллельно отправляем на общий сервер (если URL задан)
        OnlineLeaderboard.submit_async(name, score)
        return data["leaderboard"]

    @classmethod
    def get_leaderboard(cls):
        data = cls.load_data()
        board = list(data.get("leaderboard") or [])
        board.sort(key=lambda e: int(e.get("score", 0)), reverse=True)
        return board[:15]

    @classmethod
    def get_leaderboard_url(cls):
        return (cls.load_data().get("leaderboard_url") or "").strip().rstrip("/")

    @classmethod
    def set_leaderboard_url(cls, url: str):
        data = cls.load_data()
        data["leaderboard_url"] = (url or "").strip().rstrip("/")
        cls.save_data(data)
        return data["leaderboard_url"]


# ================================================================
# ОБЩАЯ (ОНЛАЙН) ТАБЛИЦА ЛИДЕРОВ
# ================================================================

class OnlineLeaderboard:
    TIMEOUT = 6

    @classmethod
    def _url(cls):
        return SaveManager.get_leaderboard_url()

    @classmethod
    def fetch(cls):
        base = cls._url()
        if not base:
            return None, "URL сервера не задан"
        try:
            req = urllib.request.Request(
                base + "/leaders",
                headers={"Accept": "application/json", "User-Agent": "BlocksStafn/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=cls.TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
            board = data.get("leaders") if isinstance(data, dict) else data
            if not isinstance(board, list):
                return None, "Неверный ответ сервера"
            clean = []
            for e in board:
                if not isinstance(e, dict):
                    continue
                clean.append({
                    "name": str(e.get("name", "Игрок"))[:16],
                    "score": int(e.get("score", 0)),
                })
            clean.sort(key=lambda x: x["score"], reverse=True)
            return clean[:30], None
        except Exception as e:
            return None, str(e)[:80]

    @classmethod
    def submit(cls, name, score):
        base = cls._url()
        if not base:
            return False, "URL сервера не задан"
        try:
            payload = json.dumps({"name": name, "score": int(score)}).encode("utf-8")
            req = urllib.request.Request(
                base + "/score",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "BlocksStafn/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=cls.TIMEOUT) as resp:
                resp.read()
            return True, None
        except Exception as e:
            return False, str(e)[:80]

    @classmethod
    def submit_async(cls, name, score):
        if not cls._url():
            return
        threading.Thread(target=cls.submit, args=(name, score), daemon=True).start()

    @classmethod
    def fetch_async(cls, callback):
        def worker():
            board, err = cls.fetch()
            Clock.schedule_once(lambda dt: callback(board, err), 0)

        threading.Thread(target=worker, daemon=True).start()


# ================================================================
# МЕНЕДЖЕР СЧЁТА И БЛОКСОВ
# ================================================================

class ScoreManager:
    def __init__(self):
        data = SaveManager.load_data()
        self.score = 0
        self.best_score = int(data.get("best_score", 0))
        self.combo = 0
        self.last_milestone = 0

    def add_piece_score(self, blocks_count):
        self.score += blocks_count * 2
        self.check_blocksy()
        self.update_best()

    def add_lines(self, lines):
        if lines <= 0:
            self.combo = 0
            return 0
        self.combo += 1
        points_map = {1: 100, 2: 300, 3: 600, 4: 1000, 5: 1500, 6: 2200, 7: 3000, 8: 4000}
        base_points = points_map.get(lines, lines * 500)
        total = base_points + max(0, self.combo - 1) * 120
        self.score += total
        self.check_blocksy()
        self.update_best()
        return total

    def check_blocksy(self):
        current_milestone = self.score // 1000
        if current_milestone > self.last_milestone:
            gained = (current_milestone - self.last_milestone) * 10
            self.last_milestone = current_milestone
            data = SaveManager.load_data()
            data["blocksy"] = data.get("blocksy", 0) + gained
            SaveManager.save_data(data)

    def update_best(self):
        if self.score > self.best_score:
            self.best_score = self.score
            data = SaveManager.load_data()
            data["best_score"] = self.best_score
            SaveManager.save_data(data)

    def reset(self):
        self.score = 0
        self.combo = 0
        self.last_milestone = 0
        data = SaveManager.load_data()
        self.best_score = int(data.get("best_score", 0))


# ================================================================
# ПАЛИТРЫ И ТЕМЫ
# ================================================================

BLOCK_PALETTES = {
    "Неон": [
        (1.00, 0.05, 0.55, 1), (0.00, 0.95, 0.65, 1), (0.15, 0.75, 1.00, 1),
        (1.00, 0.90, 0.00, 1), (0.85, 0.20, 1.00, 1), (0.00, 0.90, 1.00, 1), (1.00, 0.35, 0.05, 1)
    ],
    "Классика": [
        (0.95, 0.25, 0.30, 1), (0.15, 0.82, 0.45, 1), (0.20, 0.58, 1.00, 1),
        (1.00, 0.70, 0.12, 1), (0.72, 0.28, 0.98, 1), (0.00, 0.85, 0.90, 1), (1.00, 0.40, 0.72, 1)
    ],
    "Пастель": [
        (1.00, 0.60, 0.70, 1), (0.60, 0.92, 0.75, 1), (0.60, 0.80, 1.00, 1),
        (1.00, 0.88, 0.60, 1), (0.85, 0.65, 1.00, 1), (0.60, 0.95, 0.95, 1), (1.00, 0.75, 0.88, 1)
    ],
    "Огонь": [
        (1.00, 0.20, 0.05, 1), (1.00, 0.45, 0.00, 1), (1.00, 0.65, 0.05, 1),
        (0.90, 0.15, 0.15, 1), (1.00, 0.35, 0.00, 1), (1.00, 0.80, 0.10, 1), (0.85, 0.10, 0.20, 1)
    ],
    "Лёд": [
        (0.50, 0.85, 1.00, 1), (0.30, 0.75, 1.00, 1), (0.75, 0.95, 1.00, 1),
        (0.40, 0.90, 0.95, 1), (0.20, 0.60, 1.00, 1), (0.60, 0.80, 1.00, 1), (0.45, 0.95, 0.90, 1)
    ],
}

SHOP_THEMES = {
    "Советский": {"price_sticks": 5, "desc": "Ретро стиль с прожекторами"},
    "Космос": {"price_sticks": 8, "desc": "Планета с кольцами и звезды"},
    "Ретро-Волна": {"price_sticks": 7, "desc": "Неоновая 3D-сетка 80-х"},
    "Лес": {"price_sticks": 6, "desc": "Туманный лес и светлячки"},
}

SHOP_STYLES = {
    "Стеклянный Неон": {"price_sticks": 15, "desc": "Премиальное прозрачное стекло с неоном"}
}

_PALETTE_CACHE = None
_STYLE_CACHE = None

def get_current_palette():
    global _PALETTE_CACHE
    if _PALETTE_CACHE is None:
        data = SaveManager.load_data()
        _PALETTE_CACHE = BLOCK_PALETTES.get(data.get("block_palette", "Неон"), BLOCK_PALETTES["Неон"])
    return _PALETTE_CACHE

def get_current_style():
    global _STYLE_CACHE
    if _STYLE_CACHE is None:
        data = SaveManager.load_data()
        _STYLE_CACHE = data.get("block_style", "Стеклянный Взрыв")
    return _STYLE_CACHE

def invalidate_visual_cache():
    global _PALETTE_CACHE, _STYLE_CACHE
    _PALETTE_CACHE = None
    _STYLE_CACHE = None

def _clamp(v, lo=0.0, hi=1.0):
    try:
        return max(lo, min(hi, float(v)))
    except Exception:
        return lo

def _safe_size(s, minimum=1.0):
    try:
        return max(minimum, float(s))
    except Exception:
        return minimum


# ================================================================
# ФИГУРЫ
# ================================================================

SHAPES = {
    "dot": [(0,0)],
    "h2": [(0,0),(0,1)], "v2": [(0,0),(1,0)],
    "h3": [(0,0),(0,1),(0,2)], "v3": [(0,0),(1,0),(2,0)],
    "h4": [(0,0),(0,1),(0,2),(0,3)], "v4": [(0,0),(1,0),(2,0),(3,0)],
    "sq2": [(0,0),(0,1),(1,0),(1,1)],
    "L3": [(0,0),(1,0),(1,1)], "J3": [(0,1),(1,0),(1,1)],
    "L4": [(0,0),(1,0),(2,0),(2,1)], "J4": [(0,1),(1,1),(2,0),(2,1)],
    "T4": [(0,0),(0,1),(0,2),(1,1)], "Z4": [(0,0),(0,1),(1,1),(1,2)],
    "S4": [(0,1),(0,2),(1,0),(1,1)],
    "corner5": [(0,0),(1,0),(2,0),(2,1),(2,2)],
}


# ================================================================
# КЛИМАТИЧЕСКИЙ АРТ-ФОН С УНИКАЛЬНОЙ АНИМАЦИЕЙ ЧАСТИЦ (ОПТИМИЗИРОВАН)
# ================================================================

class DynamicBackground(Widget):
    def __init__(self, theme="Сакура", **kwargs):
        super().__init__(**kwargs)
        self.theme = theme
        self.particles = []
        self.active = False
        self.particle_group = InstructionGroup()
        self._ev = None
        self.bind(pos=self.redraw, size=self.on_resize)
        Clock.schedule_once(lambda dt: self.create_particles(), 0.05)

    def set_active(self, active):
        self.active = active
        if active:
            if self._ev is None:
                self._ev = Clock.schedule_interval(self.update_particles, 1.0 / 30.0)
        else:
            if self._ev is not None:
                self._ev.cancel()
                self._ev = None

    def on_resize(self, *a):
        self.redraw()

    def create_particles(self):
        self.particles.clear()
        w = max(self.width, Window.width, 1)
        h = max(self.height, Window.height, 1)

        count = 28
        if self.theme in ("Сакура", "Зима", "Космос", "Ретро-Волна"):
            count = 36
        elif self.theme in ("Горы & Ветер", "Лес"):
            count = 24

        for _ in range(count):
            self.particles.append({
                "x": random.uniform(0, w),
                "y": random.uniform(0, h),
                "size": random.uniform(dp(3.5), dp(11)),
                "speed": random.uniform(0.4, 2.4),
                "phase": random.uniform(0, math.pi * 2),
                "rot": random.uniform(0, 360),
                "rot_speed": random.uniform(-2.5, 2.5),
                "alpha": random.uniform(0.25, 0.95)
            })

    def set_theme(self, theme):
        self.theme = theme
        self.create_particles()
        self.redraw()

    def update_particles(self, dt):
        if not self.active or not self.particles:
            return
        if self.width <= 0 or self.height <= 0:
            return
        w = max(self.width, Window.width, 1)
        h = max(self.height, Window.height, 1)
        t = time.time()
        self._t = t  # запоминаем для пульсации луны/планеты в redraw_particles

        for p in self.particles:
            p["rot"] += p["rot_speed"]
            
            if self.theme == "Сакура":
                p["y"] -= p["speed"] * 1.2
                p["x"] += math.sin(t * 1.5 + p["phase"]) * 1.1
                if p["y"] < -20:
                    p["y"] = h + 20
                    p["x"] = random.uniform(0, w)

            elif self.theme == "Зима":
                p["y"] -= p["speed"] * 1.4
                p["x"] += math.sin(t * 1.1 + p["phase"]) * 0.6
                if p["y"] < -20:
                    p["y"] = h + 20
                    p["x"] = random.uniform(0, w)

            elif self.theme in ("Горы & Ветер", "Лес"):
                p["x"] += p["speed"] * 2.6
                p["y"] += math.sin(t * 2.2 + p["phase"]) * 0.8
                if p["x"] > w + 30:
                    p["x"] = -30
                    p["y"] = random.uniform(0, h)

            elif self.theme == "Космос":
                p["alpha"] = 0.4 + 0.55 * math.sin(t * 3.0 + p["phase"])

            elif self.theme == "Ретро-Волна":
                p["y"] += p["speed"] * 1.1
                if p["y"] > h + 20:
                    p["y"] = -20
                    p["x"] = random.uniform(0, w)

            else:
                p["y"] += math.sin(t * 0.8 + p["phase"]) * 0.4
                p["x"] += math.cos(t * 0.8 + p["phase"]) * 0.4

        self.redraw_particles()

    def redraw_particles(self):
        g = self.particle_group
        g.clear()
        theme = self.theme
        w, h = self.width, self.height
        t = getattr(self, "_t", time.time())
        tier = get_fx_tier()

        # Пульсирующее свечение луны/планеты/солнца — переиспользует уже работающий
        # таймер частиц (30 fps), отдельный Clock под это НЕ создаём, чтобы не грузить FPS.
        if tier != "low" and w > 0 and h > 0:
            pulse = 0.5 + 0.5 * math.sin(t * 1.4)
            if theme == "Сакура":
                moon_s = min(w, h) * 0.36
                cx, cy = w * 0.57 + moon_s * 0.41, h * 0.63 + moon_s * 0.41
                rad = moon_s * (0.9 + 0.18 * pulse)
                g.add(Color(1.0, 0.92, 0.85, 0.10 + 0.06 * pulse))
                g.add(Ellipse(pos=(cx - rad, cy - rad), size=(rad * 2, rad * 2)))
            elif theme == "Космос":
                p_size = min(w, h) * 0.38
                cx, cy = w * 0.54 + p_size / 2, h * 0.54 + p_size / 2
                rad = p_size * (0.65 + 0.15 * pulse)
                g.add(Color(0.3, 0.6, 1.0, 0.08 + 0.05 * pulse))
                g.add(Ellipse(pos=(cx - rad, cy - rad), size=(rad * 2, rad * 2)))
            elif theme == "Ретро-Волна":
                sun_s = min(w, h) * 0.34
                cx, cy = w * 0.5, h * 0.33 + sun_s / 2
                rad = sun_s * (0.7 + 0.2 * pulse)
                g.add(Color(1.0, 0.4, 0.35, 0.10 + 0.07 * pulse))
                g.add(Ellipse(pos=(cx - rad, cy - rad), size=(rad * 2, rad * 2)))

        for p in self.particles:
            if theme == "Сакура":
                px, py, ps = p["x"], p["y"], p["size"]
                if tier == "high":
                    g.add(Color(1.0, 0.45, 0.7, p["alpha"] * 0.18))
                    g.add(Ellipse(pos=(px - ps * 0.3, py - ps * 0.2), size=(ps * 2.2, ps * 1.2)))
                g.add(Color(1.0, 0.48, 0.72, p["alpha"] * 0.95))
                g.add(Ellipse(pos=(px, py), size=(ps * 1.55, ps * 0.72)))
                g.add(Color(1.0, 0.78, 0.9, p["alpha"] * 0.55))
                g.add(Ellipse(pos=(px + ps * 0.2, py + ps * 0.15), size=(ps * 0.72, ps * 0.36)))
            elif theme == "Зима":
                px, py, ps = p["x"], p["y"], p["size"]
                g.add(Color(0.9, 0.96, 1.0, p["alpha"] * 0.35))
                g.add(Ellipse(pos=(px - ps * 0.6, py - ps * 0.6), size=(ps * 1.2, ps * 1.2)))
                g.add(Color(0.95, 0.98, 1.0, p["alpha"]))
                g.add(Ellipse(pos=(px - ps * 0.35, py - ps * 0.35), size=(ps * 0.7, ps * 0.7)))
            elif theme == "Горы & Ветер":
                g.add(Color(0.45, 0.8, 1.0, p["alpha"] * 0.3))
                g.add(Line(points=[p["x"], p["y"], p["x"] + dp(38), p["y"] + dp(2)], width=dp(1.15)))
                g.add(Color(0.85, 0.65, 0.35, p["alpha"]))
                g.add(Ellipse(pos=(p["x"] + dp(12), p["y"]), size=(p["size"] * 0.95, p["size"] * 0.45)))
            elif theme == "Лес":
                g.add(Color(0.35, 1.0, 0.35, p["alpha"] * 0.22))
                g.add(Ellipse(pos=(p["x"] - p["size"], p["y"] - p["size"]), size=(p["size"] * 3, p["size"] * 3)))
                g.add(Color(0.95, 1.0, 0.55, p["alpha"]))
                g.add(Ellipse(pos=(p["x"], p["y"]), size=(p["size"] * 0.85, p["size"] * 0.85)))
            elif theme == "Космос":
                px, py, ps = p["x"], p["y"], p["size"] * 0.55
                g.add(Color(0.7, 0.85, 1.0, p["alpha"] * 0.35))
                g.add(Ellipse(pos=(px - ps, py - ps), size=(ps * 2, ps * 2)))
                g.add(Color(1.0, 1.0, 1.0, p["alpha"]))
                g.add(Ellipse(pos=(px - ps * 0.35, py - ps * 0.35), size=(ps * 0.7, ps * 0.7)))
            elif theme == "Ретро-Волна":
                px, py, ps = p["x"], p["y"], p["size"]
                g.add(Color(0.0, 0.95, 1.0, p["alpha"] * 0.85))
                g.add(Line(points=[px, py + ps, px + ps * 0.7, py, px, py - ps, px - ps * 0.7, py], close=True, width=1.15))
            else:
                g.add(Color(1.0, 0.9, 0.55, p["alpha"] * 0.75))
                g.add(Ellipse(pos=(p["x"], p["y"]), size=(p["size"] * 0.65, p["size"] * 0.65)))

    def redraw(self, *a):
        self.canvas.clear()
        w, h = self.width, self.height
        if w <= 0 or h <= 0: return
        self.particle_group = InstructionGroup()

        with self.canvas:
            if self.theme == "Сакура":
                Color(0.04, 0.015, 0.08, 1)
                Rectangle(pos=self.pos, size=self.size)
                Color(0.22, 0.05, 0.18, 0.4)
                Ellipse(pos=(w * 0.15, h * 0.35), size=(w * 0.75, h * 0.6))
                Color(0.35, 0.08, 0.22, 0.18)
                Ellipse(pos=(w * 0.4, h * 0.55), size=(w * 0.45, h * 0.35))
                moon_s = min(w, h) * 0.38
                Color(1.0, 0.75, 0.88, 0.1)
                Ellipse(pos=(w * 0.5, h * 0.55), size=(moon_s * 1.5, moon_s * 1.5))
                Color(1.0, 0.85, 0.92, 0.18)
                Ellipse(pos=(w * 0.53, h * 0.58), size=(moon_s * 1.2, moon_s * 1.2))
                Color(1.0, 0.93, 0.97, 0.95)
                Ellipse(pos=(w * 0.56, h * 0.62), size=(moon_s * 0.85, moon_s * 0.85))
                Color(1.0, 0.98, 1.0, 0.55)
                Ellipse(pos=(w * 0.59, h * 0.655), size=(moon_s * 0.5, moon_s * 0.5))
                Color(0.09, 0.04, 0.12, 0.95)
                Line(points=[0, h * 0.16, w * 0.3, h * 0.34, w * 0.6, h * 0.14, w, h * 0.28, w, 0, 0, 0], width=1, close=True)
                Color(0.06, 0.025, 0.09, 0.92)
                Line(points=[0, h * 0.1, w * 0.42, h * 0.26, w * 0.78, h * 0.09, w, h * 0.2, w, 0, 0, 0], width=1, close=True)
                Color(0.03, 0.012, 0.05, 1)
                Line(points=[w * 0.03, 0, w * 0.1, h * 0.28, w * 0.2, h * 0.48], width=dp(7))
                Line(points=[w * 0.1, h * 0.28, w * 0.34, h * 0.38], width=dp(4))
                Line(points=[w * 0.16, h * 0.4, w * 0.28, h * 0.55], width=dp(2.8))
                Line(points=[w * 0.2, h * 0.48, w * 0.42, h * 0.5], width=dp(2.2))
                Color(0.95, 0.28, 0.55, 0.42)
                Ellipse(pos=(w * 0.05, h * 0.28), size=(dp(140), dp(85)))
                Ellipse(pos=(w * 0.18, h * 0.38), size=(dp(155), dp(95)))
                Color(1.0, 0.55, 0.78, 0.5)
                Ellipse(pos=(w * 0.12, h * 0.34), size=(dp(105), dp(62)))
                Color(1.0, 0.72, 0.88, 0.32)
                Ellipse(pos=(w * 0.24, h * 0.44), size=(dp(85), dp(52)))

            elif self.theme == "Зима":
                Color(0.015, 0.04, 0.1, 1)
                Rectangle(pos=self.pos, size=self.size)
                Color(0.15, 0.25, 0.4, 0.28)
                Ellipse(pos=(w * 0.1, h * 0.4), size=(w * 0.8, h * 0.5))
                Color(0.07, 0.12, 0.22, 0.92)
                Ellipse(pos=(w * -0.3, h * -0.1), size=(w * 0.9, h * 0.35))
                Color(0.14, 0.24, 0.38, 0.95)
                Ellipse(pos=(w * 0.25, h * -0.14), size=(w * 0.95, h * 0.38))
                Color(0.2, 0.32, 0.48, 0.55)
                Ellipse(pos=(w * 0.55, h * -0.05), size=(w * 0.55, h * 0.22))
                Color(0.75, 0.88, 1.0, 0.14)
                Ellipse(pos=(w * 0.6, h * 0.66), size=(min(w, h) * 0.32, min(w, h) * 0.32))
                Color(0.92, 0.96, 1.0, 0.78)
                Ellipse(pos=(w * 0.65, h * 0.71), size=(min(w, h) * 0.2, min(w, h) * 0.2))
                Color(1, 1, 1, 0.35)
                Ellipse(pos=(w * 0.68, h * 0.74), size=(min(w, h) * 0.08, min(w, h) * 0.08))

            elif self.theme == "Горы & Ветер":
                Color(0.025, 0.04, 0.08, 1)
                Rectangle(pos=self.pos, size=self.size)
                Color(0.2, 0.35, 0.55, 0.18)
                Ellipse(pos=(w * 0.15, h * 0.5), size=(w * 0.7, h * 0.4))
                Color(0.08, 0.12, 0.2, 0.96)
                Line(points=[0, h * 0.1, w * 0.2, h * 0.5, w * 0.48, h * 0.18, w * 0.8, h * 0.58, w, h * 0.24, w, 0, 0, 0], close=True)
                Color(0.14, 0.18, 0.28, 0.75)
                Line(points=[0, h * 0.06, w * 0.32, h * 0.28, w * 0.68, h * 0.08, w, h * 0.2, w, 0, 0, 0], close=True)
                Color(0.9, 0.95, 1.0, 0.8)
                Line(points=[w * 0.16, h * 0.42, w * 0.2, h * 0.5, w * 0.26, h * 0.43], width=dp(1.8))
                Line(points=[w * 0.74, h * 0.48, w * 0.8, h * 0.58, w * 0.88, h * 0.49], width=dp(1.8))
                Color(0.4, 0.7, 1.0, 0.08)
                Ellipse(pos=(w * 0.3, h * 0.65), size=(w * 0.4, h * 0.2))

            elif self.theme == "Лес":
                Color(0.01, 0.04, 0.025, 1)
                Rectangle(pos=self.pos, size=self.size)
                Color(0.05, 0.14, 0.08, 0.45)
                Ellipse(pos=(w * 0.05, h * 0.15), size=(w * 0.9, h * 0.55))
                Color(0.03, 0.1, 0.06, 0.97)
                for i in range(8):
                    tree_x = i * (w / 7.0)
                    Line(points=[tree_x - dp(30), h * 0.06, tree_x, h * 0.4, tree_x + dp(30), h * 0.06], close=True)
                Color(0.05, 0.15, 0.09, 0.75)
                for i in range(6):
                    tree_x = i * (w / 5.0) + w * 0.08
                    Line(points=[tree_x - dp(20), h * 0.1, tree_x, h * 0.32, tree_x + dp(20), h * 0.1], close=True)
                Color(0.07, 0.16, 0.1, 0.45)
                Rectangle(pos=(0, 0), size=(w, h * 0.2))
                Color(0.3, 0.9, 0.4, 0.06)
                Ellipse(pos=(w * 0.2, h * 0.5), size=(w * 0.6, h * 0.3))

            elif self.theme == "Космос":
                Color(0.008, 0.008, 0.04, 1)
                Rectangle(pos=self.pos, size=self.size)
                Color(0.4, 0.05, 0.6, 0.14)
                Ellipse(pos=(w * 0.0, h * 0.15), size=(w * 1.0, h * 0.55))
                Color(0.1, 0.2, 0.45, 0.12)
                Ellipse(pos=(w * 0.2, h * 0.6), size=(w * 0.5, h * 0.3))
                p_size = min(w, h) * 0.4
                Color(0.1, 0.28, 0.58, 0.95)
                Ellipse(pos=(w * 0.52, h * 0.52), size=(p_size, p_size))
                Color(0.18, 0.42, 0.72, 0.4)
                Ellipse(pos=(w * 0.57, h * 0.57), size=(p_size * 0.72, p_size * 0.72))
                Color(0.35, 0.55, 0.8, 0.25)
                Ellipse(pos=(w * 0.62, h * 0.62), size=(p_size * 0.4, p_size * 0.4))
                Color(0.8, 0.9, 1.0, 0.5)
                Line(ellipse=(w * 0.44, h * 0.62, p_size * 1.45, p_size * 0.32), width=dp(2.8))
                Color(0.95, 0.98, 1.0, 0.2)
                Line(ellipse=(w * 0.4, h * 0.64, p_size * 1.6, p_size * 0.24), width=dp(1.2))

            elif self.theme == "Ретро-Волна":
                Color(0.06, 0.01, 0.11, 1)
                Rectangle(pos=self.pos, size=self.size)
                Color(1.0, 0.2, 0.5, 0.16)
                Ellipse(pos=(w * 0.1, h * 0.22), size=(w * 0.8, h * 0.5))
                sun_s = min(w, h) * 0.36
                Color(1.0, 0.2, 0.45, 0.2)
                Ellipse(pos=(w * 0.5 - sun_s * 0.7, h * 0.28), size=(sun_s * 1.4, sun_s * 1.4))
                Color(1.0, 0.3, 0.5, 0.88)
                Ellipse(pos=(w * 0.5 - sun_s / 2, h * 0.32), size=(sun_s, sun_s))
                Color(1.0, 0.55, 0.25, 0.4)
                Ellipse(pos=(w * 0.5 - sun_s * 0.28, h * 0.38), size=(sun_s * 0.56, sun_s * 0.56))
                Color(0.0, 0.95, 1.0, 0.32)
                horizon_y = h * 0.32
                for step in range(0, max(1, int(horizon_y)), 20):
                    Line(points=[0, step, w, step], width=1.0)

            else:
                Color(0.4, 0.06, 0.06, 1)
                Rectangle(pos=self.pos, size=self.size)
                Color(0.92, 0.86, 0.72, 1)
                Rectangle(pos=(0, h * 0.56), size=(w, h * 0.44))
                Color(0.7, 0.1, 0.1, 1)
                Rectangle(pos=(0, h * 0.53), size=(w, h * 0.045))
                Color(1.0, 0.95, 0.7, 0.12)
                Line(points=[w * 0.1, 0, w * 0.36, h], width=dp(38))
                Line(points=[w * 0.9, 0, w * 0.64, h], width=dp(38))
                Color(1.0, 0.85, 0.4, 0.14)
                Ellipse(pos=(w * 0.32, h * 0.6), size=(w * 0.36, h * 0.22))

        self.canvas.add(self.particle_group)
        self.redraw_particles()


# ================================================================
# КРИСТАЛЛИЧЕСКИЙ 3D РЕНДЕР БЛОКОВ С КАСТОМИЗАЦИЕЙ (iOS 26 GLASS)
# ================================================================

def draw_block_glow(x, y, size, color, tier=None):
    """Мягкий ореол. low = 0 слоёв, medium = 1, high = 2 — чтобы FPS не проседал на полном поле."""
    tier = tier or get_fx_tier()
    if tier == "low":
        return
    r = _clamp(color[0] if color else 1)
    g = _clamp(color[1] if color and len(color) > 1 else 1)
    b = _clamp(color[2] if color and len(color) > 2 else 1)
    size = _safe_size(size, 4.0)
    layers = 2 if tier == "high" else 1
    base_spread = size * (0.38 if tier == "high" else 0.26)
    for i in range(layers, 0, -1):
        spread = base_spread * (i / layers)
        glow_alpha = 0.14 * (i / layers)
        Color(_clamp(r * 1.15), _clamp(g * 1.15), _clamp(b * 1.15), glow_alpha)
        Ellipse(
            pos=(x - spread * 0.5, y - spread * 0.5),
            size=(_safe_size(size + spread), _safe_size(size + spread)),
        )


def draw_3d_block(canvas, x, y, size, color, alpha=1.0, style="Стеклянный Взрыв"):
    size = _safe_size(size, 4.0)
    radius = max(dp(4), min(size * 0.26, dp(11)))
    r = _clamp(color[0] if color else 1)
    g = _clamp(color[1] if color and len(color) > 1 else 1)
    b = _clamp(color[2] if color and len(color) > 2 else 1)
    a = _clamp(alpha)
    pad = min(dp(2.2), size * 0.13)
    inner_w = _safe_size(size - pad * 2)
    inner_h = _safe_size(size - pad * 2.4)
    tier = get_fx_tier()

    draw_block_glow(x, y, size, (r, g, b), tier)

    if style == "Стеклянный Неон":
        # Премиум-стекло: тёмный каркас, цветной tint, отражение, неон-кромка
        Color(0, 0, 0, 0.28 * a)
        RoundedRectangle(pos=(x + dp(1.5), y - dp(2.8)), size=(size, size), radius=[radius])
        Color(0.05, 0.06, 0.1, 0.72 * a)
        RoundedRectangle(pos=(x, y), size=(size, size), radius=[radius])
        Color(_clamp(r * 0.35 + 0.12), _clamp(g * 0.4 + 0.14), _clamp(b * 0.55 + 0.22), 0.28 * a)
        RoundedRectangle(pos=(x + pad * 0.35, y + pad * 0.4), size=(inner_w, inner_h), radius=[radius * 0.92])
        Color(_clamp(r * 0.7 + 0.15), _clamp(g * 0.7 + 0.18), _clamp(b * 0.85 + 0.2), 0.22 * a)
        RoundedRectangle(
            pos=(x + pad * 0.8, y + size * 0.42),
            size=(_safe_size(size - pad * 1.6), _safe_size(size * 0.42)),
            radius=[radius * 0.55],
        )
        Color(1, 1, 1, 0.38 * a)
        RoundedRectangle(
            pos=(x + pad, y + size * 0.62),
            size=(_safe_size(size - pad * 2), _safe_size(size * 0.22)),
            radius=[radius * 0.45],
        )
        Color(1, 1, 1, 0.55 * a)
        RoundedRectangle(
            pos=(x + pad * 1.3, y + size * 0.78),
            size=(_safe_size(size - pad * 2.6), _safe_size(size * 0.07)),
            radius=[dp(2)],
        )
        spec = _safe_size(size * 0.15)
        Color(1, 1, 1, 0.65 * a)
        Ellipse(pos=(x + size * 0.64, y + size * 0.7), size=(spec, spec * 0.65))
        # Цветная «неоновая» кромка без Line — только тонкий rect-слой
        Color(r, g, b, 0.35 * a)
        RoundedRectangle(pos=(x + 1, y + 1), size=(_safe_size(size - 2), _safe_size(size - 2)), radius=[radius])
        Color(0.05, 0.06, 0.1, 0.55 * a)
        RoundedRectangle(pos=(x + 2.2, y + 2.2), size=(_safe_size(size - 4.4), _safe_size(size - 4.4)), radius=[radius * 0.85])

    elif style == "Стеклянный Взрыв" or style == "iOS Glass 26":
        # Кристалл / вспышка — плотный цвет, ядро, блик
        Color(0, 0, 0, 0.36 * a)
        RoundedRectangle(pos=(x + dp(1.6), y - dp(3.0)), size=(size, size), radius=[radius])
        Color(_clamp(r * 0.28), _clamp(g * 0.28), _clamp(b * 0.28), 0.98 * a)
        RoundedRectangle(pos=(x, y), size=(size, size), radius=[radius])
        Color(_clamp(r * 0.92), _clamp(g * 0.92), _clamp(b * 0.92), 0.95 * a)
        RoundedRectangle(pos=(x + pad * 0.4, y + pad * 0.5), size=(inner_w, inner_h), radius=[radius * 0.88])
        Color(_clamp(r * 1.2), _clamp(g * 1.2), _clamp(b * 1.2), 0.48 * a)
        RoundedRectangle(
            pos=(x + pad, y + size * 0.36),
            size=(_safe_size(size - pad * 2), _safe_size(size * 0.48)),
            radius=[radius * 0.5],
        )
        Color(1, 1, 1, 0.55 * a)
        RoundedRectangle(
            pos=(x + pad * 1.1, y + size * 0.68),
            size=(_safe_size(size - pad * 2.2), _safe_size(size * 0.14)),
            radius=[dp(3)],
        )
        core = _safe_size(size * 0.24)
        Color(1, 1, 1, 0.7 * a)
        Ellipse(pos=(x + size * 0.36, y + size * 0.36), size=(core, core))
        if tier != "low":
            spark = _safe_size(size * 0.14)
            sx, sy = x + size * 0.74, y + size * 0.76
            Color(1, 1, 1, 0.8 * a)
            Ellipse(pos=(sx - spark * 0.35, sy - spark * 0.35), size=(spark * 0.7, spark * 0.7))

    elif style == "Глянец":
        Color(0, 0, 0, 0.42 * a)
        RoundedRectangle(pos=(x + dp(1.8), y - dp(3.2)), size=(size, size), radius=[radius])
        Color(r * 0.32, g * 0.32, b * 0.32, a)
        RoundedRectangle(pos=(x, y), size=(size, size), radius=[radius])
        Color(r, g, b, a)
        RoundedRectangle(pos=(x + pad * 0.45, y + pad * 0.45), size=(inner_w, inner_h), radius=[radius * 0.9])
        Color(_clamp(r * 1.15), _clamp(g * 1.15), _clamp(b * 1.15), 0.35 * a)
        RoundedRectangle(
            pos=(x + pad, y + size * 0.4),
            size=(_safe_size(size - pad * 2), _safe_size(size * 0.4)),
            radius=[radius * 0.5],
        )
        Color(1, 1, 1, 0.7 * a)
        Ellipse(pos=(x + pad * 0.8, y + size * 0.52), size=(_safe_size(size * 0.4), _safe_size(size * 0.28)))

    elif style == "Киберпанк":
        inset1 = min(dp(3.0), size * 0.16)
        inset2 = min(dp(5.5), size * 0.28)
        if tier != "low":
            Color(r, g, b, 0.18 * a)
            Ellipse(pos=(x - size * 0.08, y - size * 0.08), size=(_safe_size(size * 1.16), _safe_size(size * 1.16)))
        Color(0, 0, 0, 0.55 * a)
        Rectangle(pos=(x + dp(1.6), y - dp(1.8)), size=(size, size))
        Color(r, g, b, 0.95 * a)
        Rectangle(pos=(x, y), size=(size, size))
        Color(0.02, 0.02, 0.06, 0.82 * a)
        Rectangle(pos=(x + inset1, y + inset1), size=(_safe_size(size - inset1 * 2), _safe_size(size - inset1 * 2)))
        Color(_clamp(r * 1.3), _clamp(g * 1.3), _clamp(b * 1.3), a)
        Rectangle(pos=(x + inset2, y + inset2), size=(_safe_size(size - inset2 * 2), _safe_size(size - inset2 * 2)))
        Color(r, g, b, 0.9 * a)
        y1 = y + size * 0.3
        y2 = y + size * 0.7
        Line(points=[x + 1, y1, x + size - 1, y1], width=1.2)
        Line(points=[x + 1, y2, x + size - 1, y2], width=1.2)

    else:  # Классика 3D
        Color(0, 0, 0, 0.5 * a)
        RoundedRectangle(pos=(x + dp(1.7), y - dp(3.2)), size=(size, size), radius=[radius])
        Color(r * 0.32, g * 0.32, b * 0.32, a)
        RoundedRectangle(pos=(x, y), size=(size, size), radius=[radius])
        Color(r, g, b, a)
        RoundedRectangle(pos=(x + pad * 0.5, y + pad * 0.7), size=(inner_w, inner_h), radius=[radius * 0.9])
        Color(_clamp(r * 1.3), _clamp(g * 1.3), _clamp(b * 1.3), 0.45 * a)
        RoundedRectangle(
            pos=(x + pad, y + size * 0.34),
            size=(_safe_size(size - pad * 2), _safe_size(size * 0.42)),
            radius=[dp(3)],
        )
        Color(1, 1, 1, 0.42 * a)
        RoundedRectangle(
            pos=(x + pad, y + size * 0.66),
            size=(_safe_size(size - pad * 2), _safe_size(size * 0.14)),
            radius=[dp(3)],
        )


class GhostPiece(Widget):
    def __init__(self, piece, **kwargs):
        super().__init__(**kwargs)
        self.piece = piece
        self.valid = True
        self.size_hint = (None, None)
        self.bind(pos=self.redraw, size=self.redraw)
        self.redraw()

    def set_valid(self, v):
        self.valid = v
        self.redraw()

    def redraw(self, *a):
        self.canvas.clear()
        if not self.piece: return
        bs = self.piece.cell_size
        pad = max(dp(1), bs * 0.05)
        col = (*self.piece.color[:3], 0.38) if self.valid else (1, 0.15, 0.2, 0.35)

        with self.canvas:
            for r, c in self.piece.blocks:
                x = self.x + c * bs + pad
                y = self.y + (self.piece.rows - 1 - r) * bs + pad
                size = bs - pad * 2
                Color(0, 0, 0, 0.15)
                RoundedRectangle(pos=(x + dp(1), y - dp(1.5)), size=(size, size), radius=[dp(8)])
                Color(*col)
                RoundedRectangle(pos=(x, y), size=(size, size), radius=[dp(8)])
                Color(1, 1, 1, 0.28 if self.valid else 0.08)
                Line(rounded_rectangle=(x, y, size, size, dp(8)), width=1.2)


class Piece(Widget):
    def __init__(self, shape_name=None, color=None, cell_size=dp(32), **kwargs):
        super().__init__(**kwargs)
        self.shape_name = shape_name or random.choice(list(SHAPES.keys()))
        self.blocks = SHAPES[self.shape_name]
        self.color = color or random.choice(get_current_palette())
        self.cell_size = cell_size
        self.rows = max(r for r, c in self.blocks) + 1
        self.cols = max(c for r, c in self.blocks) + 1
        self.scale_factor = 0.68
        self.original_pos = (0, 0)
        self.is_dragging = False
        self.size_hint = (None, None)
        self.update_size()
        self.bind(pos=self.redraw, size=self.redraw)
        self.redraw()

    def update_size(self):
        bs = self.cell_size * self.scale_factor
        self.width = self.cols * bs
        self.height = self.rows * bs

    def redraw(self, *a):
        self.canvas.clear()
        bs = self.cell_size * self.scale_factor
        pad = max(dp(1), bs * 0.05)
        style = get_current_style()
        with self.canvas:
            for r, c in self.blocks:
                x = self.x + c * bs + pad
                y = self.y + (self.rows - 1 - r) * bs + pad
                draw_3d_block(self.canvas, x, y, bs - pad * 2, self.color, style=style)

    def pick_up(self, touch):
        self.is_dragging = True
        self.scale_factor = 1.0
        self.update_size()
        self.center_x = touch.x
        self.center_y = touch.y + dp(72)
        self.redraw()

    def move_to(self, touch):
        self.center_x = touch.x
        self.center_y = touch.y + dp(72)
        self.redraw()

    def return_to_origin(self):
        self.scale_factor = 0.68
        self.update_size()
        Animation(pos=self.original_pos, duration=0.22, transition="out_cubic").start(self)
        self.redraw()


# ================================================================
# ЭФФЕКТЫ И ВСПЛЫВАЮЩИЙ ТЕКСТ
# ================================================================

class ParticleBurst(Widget):
    """Взрыв: вспышка ядра + цветные кольца + искры + осколки. intensity усиливает «вау»."""

    def __init__(self, x, y, color, count=10, intensity=1.0, **kwargs):
        super().__init__(**kwargs)
        self.particles = []
        self.shockwaves = []
        self.sparkles = []
        self.flash = {"x": x, "y": y, "r": dp(18) * intensity, "alpha": 0.95, "life": 1.0}
        self.size_hint = (None, None)
        self.size = (1, 1)
        self.intensity = max(0.7, min(float(intensity), 2.2))
        col = color or (1, 1, 1, 1)
        cr, cg, cb = _clamp(col[0]), _clamp(col[1] if len(col) > 1 else 1), _clamp(col[2] if len(col) > 2 else 1)
        self.base_color = (cr, cg, cb)

        tier = get_fx_tier()
        bonus = {"high": 10, "medium": 5, "low": 1}.get(tier, 1)
        n = max(6, min(int(count * self.intensity) + bonus, 28))

        for _ in range(n):
            ang = random.uniform(0, math.pi * 2)
            spd = random.uniform(140, 340) * self.intensity
            self.particles.append({
                "x": x, "y": y,
                "vx": math.cos(ang) * spd, "vy": math.sin(ang) * spd,
                "size": random.uniform(dp(3.5), dp(10)) * (0.85 + 0.25 * self.intensity),
                "life": 1.0,
                "color": (cr, cg, cb) if random.random() > 0.25 else (
                    _clamp(cr * 1.2 + 0.2), _clamp(cg * 1.1 + 0.15), _clamp(cb * 0.9 + 0.1)
                ),
            })

        # Главная ударная волна
        self.shockwaves.append({
            "x": x, "y": y, "radius": dp(6), "alpha": 0.9,
            "speed": dp(220) * self.intensity, "fade": 2.2, "tint": (1, 1, 1),
        })
        # Цветное кольцо
        self.shockwaves.append({
            "x": x, "y": y, "radius": dp(2), "alpha": 0.7,
            "speed": dp(160) * self.intensity, "fade": 2.0, "delay": 0.04,
            "tint": (cr, cg, cb),
        })
        if tier != "low":
            self.shockwaves.append({
                "x": x, "y": y, "radius": dp(1), "alpha": 0.5,
                "speed": dp(280) * self.intensity, "fade": 2.6, "delay": 0.1,
                "tint": (1, 0.95, 0.8),
            })
            spark_count = int((12 if tier == "high" else 7) * self.intensity)
            for _ in range(spark_count):
                ang = random.uniform(0, math.pi * 2)
                spd = random.uniform(220, 480) * self.intensity
                self.sparkles.append({
                    "x": x, "y": y,
                    "vx": math.cos(ang) * spd, "vy": math.sin(ang) * spd,
                    "size": random.uniform(dp(2), dp(5)),
                    "life": 1.0,
                })

        self._pev = Clock.schedule_interval(self.update, 1 / 45)
        Clock.schedule_once(self.die, 0.85)

    def update(self, dt):
        try:
            self.canvas.clear()
        except Exception:
            self.die()
            return
        alive = False
        try:
            with self.canvas:
                # Яркая вспышка в центре
                fl = self.flash
                if fl["life"] > 0:
                    alive = True
                    fl["life"] -= dt * 3.5
                    fl["r"] += dp(90) * dt * self.intensity
                    a = _clamp(fl["life"])
                    rad = _safe_size(fl["r"], 2)
                    cr, cg, cb = self.base_color
                    Color(1, 1, 1, a * 0.55)
                    Ellipse(pos=(fl["x"] - rad * 0.35, fl["y"] - rad * 0.35), size=(rad * 0.7, rad * 0.7))
                    Color(cr, cg, cb, a * 0.35)
                    Ellipse(pos=(fl["x"] - rad * 0.7, fl["y"] - rad * 0.7), size=(rad * 1.4, rad * 1.4))
                    Color(1, 0.95, 0.8, a * 0.22)
                    Ellipse(pos=(fl["x"] - rad, fl["y"] - rad), size=(rad * 2, rad * 2))

                for sw in self.shockwaves:
                    if sw.get("delay", 0) > 0:
                        sw["delay"] -= dt
                        alive = True
                        continue
                    if sw["alpha"] > 0:
                        alive = True
                        sw["radius"] += sw.get("speed", dp(160)) * dt
                        sw["alpha"] -= dt * sw.get("fade", 2.4)
                        a = _clamp(sw["alpha"])
                        rad = _safe_size(min(sw["radius"], dp(130) * self.intensity), 1.0)
                        tr, tg, tb = sw.get("tint", (1, 1, 1))
                        # Кольцо = большой полупрозрачный круг + чуть меньший «дырка» тем же цветом слабее
                        Color(tr, tg, tb, a * 0.22)
                        Ellipse(pos=(sw["x"] - rad, sw["y"] - rad), size=(rad * 2, rad * 2))
                        inner = rad * 0.72
                        Color(tr, tg, tb, a * 0.08)
                        Ellipse(pos=(sw["x"] - inner, sw["y"] - inner), size=(inner * 2, inner * 2))

                for p in self.particles:
                    if p["life"] <= 0:
                        continue
                    alive = True
                    p["x"] += p["vx"] * dt
                    p["y"] += p["vy"] * dt
                    p["vy"] -= 380 * dt
                    p["vx"] *= (1.0 - 0.85 * dt)
                    p["life"] -= dt * 1.55
                    a = _clamp(p["life"])
                    sz = _safe_size(p["size"] * (0.6 + 0.4 * a), 0.8)
                    Color(p["color"][0], p["color"][1], p["color"][2], a * 0.3)
                    Ellipse(pos=(p["x"] - sz * 1.2, p["y"] - sz * 1.2), size=(sz * 2.4, sz * 2.4))
                    Color(p["color"][0], p["color"][1], p["color"][2], a * 0.95)
                    Ellipse(pos=(p["x"] - sz * 0.5, p["y"] - sz * 0.5), size=(sz, sz))
                    Color(1, 1, 1, a * 0.45)
                    Ellipse(pos=(p["x"] - sz * 0.2, p["y"] - sz * 0.2), size=(sz * 0.4, sz * 0.4))

                for s in self.sparkles:
                    if s["life"] <= 0:
                        continue
                    alive = True
                    s["x"] += s["vx"] * dt
                    s["y"] += s["vy"] * dt
                    s["vx"] *= (1.0 - 1.1 * dt)
                    s["vy"] *= (1.0 - 1.1 * dt)
                    s["life"] -= dt * 2.0
                    a = _clamp(s["life"])
                    sz = _safe_size(s["size"] * a, 0.6)
                    Color(1, 1, 1, a * 0.9)
                    Ellipse(pos=(s["x"] - sz * 0.5, s["y"] - sz * 0.5), size=(sz, sz))
                    Color(1, 0.95, 0.7, a * 0.35)
                    Ellipse(pos=(s["x"] - sz, s["y"] - sz), size=(sz * 2, sz * 2))
        except Exception:
            self.die()
            return
        if not alive:
            self.die()

    def die(self, *a):
        if getattr(self, "_pev", None):
            try:
                self._pev.cancel()
            except Exception:
                pass
            self._pev = None
        if self.parent:
            self.parent.remove_widget(self)


class ScreenFlash(Widget):
    """Короткая вспышка всего экрана на большом комбо / старте."""

    def __init__(self, color=(1, 0.9, 0.5, 0.35), duration=0.28, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (1, 1)
        self.opacity = 0
        self._col = color
        self.bind(pos=self._draw, size=self._draw)
        Clock.schedule_once(self._draw, 0)
        anim = Animation(opacity=1, duration=0.05) + Animation(opacity=0, duration=max(0.12, duration - 0.05))
        anim.bind(on_complete=lambda *a: self.parent.remove_widget(self) if self.parent else None)
        anim.start(self)

    def _draw(self, *a):
        self.canvas.clear()
        with self.canvas:
            Color(*self._col)
            Rectangle(pos=self.pos, size=self.size)


class FloatingText(Label):
    PHRASES = {
        1: ["Отлично!", "Есть!", "Красиво!"],
        2: ["Круто!", "Замечательно!", "Супер!"],
        3: ["Молодец!", "Огонь!", "Бомба!"],
        4: ["ЛЕГЕНДА!", "ИМБА!", "МОЩНО!!!"],
        5: ["НЕВЕРОЯТНО!", "БОГ ИГРЫ!", "ФАНТАСТИКА!"]
    }

    def __init__(self, text, color=(1, 1, 1, 1), big=False, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.font_size = "34sp" if big else "28sp"
        self.bold = True
        self.color = color
        self.size_hint = (None, None)
        self.opacity = 0
        self._big = big
        self.bind(texture_size=lambda *a: setattr(self, "size", (self.texture_size[0] + dp(8), self.texture_size[1] + dp(4))))

    def play(self, parent, x, y):
        self.center = (x, y)
        parent.add_widget(self)
        rise = dp(120) if self._big else dp(90)
        anim = (Animation(opacity=1, duration=0.07) +
                Animation(y=y + rise, opacity=0, duration=0.85 if self._big else 0.7, transition="out_quad"))
        anim.bind(on_complete=lambda *a: parent.remove_widget(self) if self.parent else None)
        anim.start(self)

    @classmethod
    def show(cls, parent, lines, x, y, combo=0):
        if lines <= 0:
            return
        level = min(5, lines)
        phrase = random.choice(cls.PHRASES.get(level, ["Круто!"]))
        big = combo >= 3 or lines >= 3
        if combo >= 3:
            phrase = f"КОМБО x{combo}!"
        if lines >= 4:
            phrase = f"{phrase}  x{lines}"
        colors = [(0.35, 1, 0.55, 1), (0.25, 0.9, 1, 1), (1, 0.85, 0.15, 1), (1, 0.35, 0.7, 1), (1, 0.25, 0.3, 1)]
        cls(phrase, color=colors[min(level - 1, 4)], big=big).play(parent, x, y)


# ================================================================
# ИГРОВОЕ ПОЛЕ 8x8 (ОПТИМИЗИРОВАНО В 1-BATCH РЕНДЕР)
# ================================================================

class GameBoard(Widget):
    GRID_SIZE = 8

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.grid = [[None] * 8 for _ in range(8)]
        self.cell_size = dp(34)
        self.board_start_x = self.board_start_y = 0
        self.highlight_cells = []
        self.bind(pos=self.redraw, size=self.redraw)

    def calculate_geometry(self):
        side = min(self.width * 0.94, self.height * 0.94)
        self.cell_size = side / 8
        self.board_start_x = self.x + (self.width - side) / 2
        self.board_start_y = self.y + (self.height - side) / 2

    def redraw(self, *a):
        try:
            self.canvas.clear()
        except Exception:
            return
        if self.width <= 0 or self.height <= 0: return
        self.calculate_geometry()
        side = self.cell_size * 8
        sx, sy = self.board_start_x, self.board_start_y
        style = get_current_style()

        try:
          with self.canvas:
            Color(0, 0, 0, 0.55)
            RoundedRectangle(pos=(sx - dp(11), sy - dp(13)), size=(side + dp(22), side + dp(26)), radius=[dp(18)])
            Color(0.025, 0.03, 0.06, 0.98)
            RoundedRectangle(pos=(sx - dp(7), sy - dp(7)), size=(side + dp(14), side + dp(14)), radius=[dp(15)])
            Color(0.25, 0.55, 0.95, 0.18)
            Line(rounded_rectangle=(sx - dp(6), sy - dp(6), side + dp(12), side + dp(12), dp(14)), width=1.6)
            Color(0.6, 0.85, 1.0, 0.08)
            RoundedRectangle(pos=(sx - dp(4), sy + side * 0.55), size=(side + dp(8), side * 0.4), radius=[dp(10)])

            for r in range(8):
                for c in range(8):
                    x = sx + c * self.cell_size
                    y = sy + (7 - r) * self.cell_size
                    cs = _safe_size(self.cell_size - dp(3.2), 4.0)
                    val = self.grid[r][c]
                    if val is None:
                        Color(0.07, 0.09, 0.14, 0.92)
                        RoundedRectangle(pos=(x + dp(1.5), y + dp(1.5)), size=(cs, cs), radius=[dp(6)])
                        Color(0.14, 0.18, 0.26, 0.35)
                        RoundedRectangle(
                            pos=(x + dp(3), y + self.cell_size * 0.55),
                            size=(_safe_size(cs - dp(3), 2), _safe_size(cs * 0.28, 1)),
                            radius=[dp(3)],
                        )
                    else:
                        draw_3d_block(self.canvas, x + dp(1.2), y + dp(1.2), cs, val, style=style)

            for r, c, valid in self.highlight_cells:
                x = sx + c * self.cell_size
                y = sy + (7 - r) * self.cell_size
                hs = _safe_size(self.cell_size - dp(4), 3.0)
                if valid:
                    Color(0.2, 1, 0.6, 0.16)
                    RoundedRectangle(pos=(x + dp(1), y + dp(1)), size=(_safe_size(self.cell_size - dp(2), 3), _safe_size(self.cell_size - dp(2), 3)), radius=[dp(7)])
                    Color(0.25, 1, 0.65, 0.28)
                else:
                    Color(1, 0.15, 0.25, 0.28)
                RoundedRectangle(pos=(x + dp(2), y + dp(2)), size=(hs, hs), radius=[dp(6)])
        except Exception:
            pass

    def can_place_piece(self, piece, sr, sc):
        for dr, dc in piece.blocks:
            r, c = sr + dr, sc + dc
            if not (0 <= r < 8 and 0 <= c < 8) or self.grid[r][c] is not None:
                return False
        return True

    def place_piece(self, piece, sr, sc):
        for dr, dc in piece.blocks:
            self.grid[sr + dr][sc + dc] = piece.color
        self.redraw()

    def check_and_clear_lines(self):
        rows = [r for r in range(8) if all(self.grid[r][c] for c in range(8))]
        cols = [c for c in range(8) if all(self.grid[r][c] for r in range(8))]
        total = len(rows) + len(cols)
        cleared = []

        if total:
            for r in rows:
                for c in range(8):
                    if self.grid[r][c]: cleared.append((r, c, self.grid[r][c]))
                    self.grid[r][c] = None
            for c in cols:
                for r in range(8):
                    if self.grid[r][c]: cleared.append((r, c, self.grid[r][c]))
                    self.grid[r][c] = None
            self.redraw()
        return total, cleared

    def can_fit_anywhere(self, piece):
        for r in range(8):
            for c in range(8):
                if self.can_place_piece(piece, r, c): return True
        return False

    def clear(self):
        self.grid = [[None] * 8 for _ in range(8)]
        self.highlight_cells = []
        self.redraw()


# ================================================================
# КНОПКИ
# ================================================================

class GlassButton(Button):
    def __init__(self, bg=(0.12, 0.2, 0.32, 0.95), **kwargs):
        super().__init__(**kwargs)
        self.bg = bg
        self.background_normal = self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.bold = True
        self.bind(pos=self.redraw, size=self.redraw)
        self.redraw()

    def redraw(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            if get_fx_tier() != "low":
                # Мягкое цветное свечение позади кнопки — рисуется только при
                # изменении pos/size, а не каждый кадр, поэтому по FPS почти бесплатно
                glow_pad = dp(6)
                Color(_clamp(self.bg[0] * 1.3), _clamp(self.bg[1] * 1.3), _clamp(self.bg[2] * 1.3), 0.20)
                RoundedRectangle(
                    pos=(self.x - glow_pad, self.y - glow_pad),
                    size=(self.width + glow_pad * 2, self.height + glow_pad * 2),
                    radius=[dp(13) + glow_pad],
                )
            # Тень
            Color(0, 0, 0, 0.38)
            RoundedRectangle(pos=(self.x + dp(1), self.y - dp(3.5)), size=self.size, radius=[dp(13)])
            # Основной фон
            Color(*self.bg)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(13)])
            # Верхний блик
            Color(1, 1, 1, 0.14)
            RoundedRectangle(pos=(self.x + dp(2), self.y + self.height * 0.55), size=(self.width - dp(4), self.height * 0.38), radius=[dp(8)])
            # Обводка
            Color(1, 1, 1, 0.18)
            Line(rounded_rectangle=(self.x + dp(0.5), self.y + dp(0.5), self.width - dp(1), self.height - dp(1), dp(12.5)), width=1.2)


# ================================================================
# ИГРОВОЙ ЭКРАН
# ================================================================

class GameScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.score_manager = ScoreManager()
        self.active_pieces = []
        self.dragged_piece = None
        self.ghost_piece = None
        self.ghost_row = self.ghost_col = None
        self.game_over_shown = False
        
        self.frame_count = 0
        self.fps_timer = time.time()
        self.current_fps = 60
        self.last_frame_time = time.time()

        data = SaveManager.load_data()
        self.bg = DynamicBackground(theme=data.get("bg_theme", "Сакура"))
        self.add_widget(self.bg)
        self.build_ui()
        
        Clock.schedule_interval(self.update_stats_label, 1.0)

    def build_ui(self):
        root = FloatLayout()
        self.main_layout = BoxLayout(orientation="vertical", padding=[dp(10), dp(6), dp(10), dp(6)], spacing=dp(5))
        
        top = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6))
        
        score_box = BoxLayout(orientation="vertical")
        score_box.add_widget(Label(text="СЧЁТ", font_size="9sp", color=(0.6, 0.7, 0.85, 1)))
        self.score_label = Label(text="0", font_size="22sp", bold=True)
        score_box.add_widget(self.score_label)

        best_box = BoxLayout(orientation="vertical")
        best_box.add_widget(Label(text="РЕКОРД", font_size="9sp", color=(0.6, 0.7, 0.85, 1)))
        self.best_label = Label(text=str(self.score_manager.best_score), font_size="22sp", bold=True, color=(1, 0.8, 0.3, 1))
        best_box.add_widget(self.best_label)

        blocksy_box = BoxLayout(orientation="vertical", size_hint_x=0.75)
        blocksy_box.add_widget(Label(text="БЛОКСЫ", font_size="8sp", color=(1, 0.85, 0.3, 1)))
        self.blocksy_label = Label(text="0", font_size="17sp", bold=True, color=(1, 0.9, 0.4, 1))
        blocksy_box.add_widget(self.blocksy_label)

        pause = GlassButton(text="Ⅱ", size_hint_x=None, width=dp(48), bg=(0.14, 0.24, 0.38, 0.95))
        pause.bind(on_release=self.open_pause)

        top.add_widget(score_box)
        top.add_widget(best_box)
        top.add_widget(blocksy_box)
        top.add_widget(pause)

        self.stats_label = Label(text="FPS --  •  CPU --  •  RAM --", size_hint_y=None, height=dp(16), font_size="9sp", color=(0.45, 0.88, 0.68, 0.95))
        self.board = GameBoard(size_hint_y=0.66)
        self.spawn_panel = FloatLayout(size_hint_y=0.28)

        self.main_layout.add_widget(top)
        self.main_layout.add_widget(self.stats_label)
        self.main_layout.add_widget(self.board)
        self.main_layout.add_widget(self.spawn_panel)

        root.add_widget(self.main_layout)
        self.add_widget(root)

        self.effect_layer = FloatLayout()
        self.add_widget(self.effect_layer)

    def play_start_explosion(self):
        cx, cy = Window.width / 2, Window.height / 2
        colors = [(1, 0.25, 0.2, 1), (1, 0.75, 0.1, 1), (0.2, 0.85, 1, 1), (1, 0.3, 0.85, 1), (0.3, 1.0, 0.5, 1)]
        tier = get_fx_tier()
        try:
            self.effect_layer.add_widget(ScreenFlash(color=(1, 0.85, 0.4, 0.28), duration=0.32))
        except Exception:
            pass
        n = 5 if tier == "high" else (4 if tier == "medium" else 3)
        for i in range(n):
            px = cx + random.uniform(-dp(110), dp(110))
            py = cy + random.uniform(-dp(140), dp(140))
            self.effect_layer.add_widget(
                ParticleBurst(px, py, random.choice(colors), count=10, intensity=1.25)
            )
        # Центральный большой взрыв
        self.effect_layer.add_widget(
            ParticleBurst(cx, cy, (1, 0.9, 0.35, 1), count=14, intensity=1.6)
        )

        def shake(dt):
            self.main_layout.x = random.uniform(-dp(10), dp(10))
            self.main_layout.y = random.uniform(-dp(8), dp(8))

        for i in range(12):
            Clock.schedule_once(shake, i * 0.022)
        Clock.schedule_once(lambda dt: setattr(self.main_layout, "pos", (0, 0)), 0.32)

    def update_stats_label(self, dt):
        if self.manager and self.manager.current != "game":
            return
        screen_hz = get_screen_refresh_rate()
        data = SaveManager.load_data()
        target = min(int(data.get("max_fps", screen_hz)), screen_hz)
        fps = int(Clock.get_rfps() or Clock.get_fps() or 0)
        self.current_fps = min(fps, target) if fps else target
        cpu = ram = "--"
        if HAS_PSUTIL:
            try:
                cpu = f"{int(psutil.cpu_percent(interval=None))}%"
                ram = f"{int(psutil.virtual_memory().percent)}%"
            except Exception:
                pass
        self.stats_label.text = f"FPS {self.current_fps}/{target} (Экран: {screen_hz}Гц)  •  CPU {cpu}  •  RAM {ram}"
        self.blocksy_label.text = str(data.get("blocksy", 0))

    def _clear_game_over_overlay(self):
        ov = getattr(self, "_game_over_overlay", None)
        if ov is not None:
            try:
                if ov.parent:
                    self.remove_widget(ov)
            except Exception:
                pass
            self._game_over_overlay = None
        self.game_over_shown = False

    def on_pre_leave(self, *a):
        if hasattr(self, "bg"):
            self.bg.set_active(False)
        # Уходим с экрана — сбрасываем застрявшую партию
        self._clear_game_over_overlay()
        try:
            self.remove_ghost()
        except Exception:
            pass

    def on_enter(self):
        screen_hz = get_screen_refresh_rate()
        data = SaveManager.load_data()
        target_fps = min(int(data.get("max_fps", screen_hz)), screen_hz)
        Clock.max_fps = target_fps
        if hasattr(self, "bg"):
            self.bg.set_active(True)

        self.bg.set_theme(data.get("bg_theme", "Сакура"))
        self.blocksy_label.text = str(data.get("blocksy", 0))
        # Всегда новая партия при входе — иначе после поражения доска «залипает»
        Clock.schedule_once(lambda dt: self.restart_game(), 0.05)
        Clock.schedule_once(lambda dt: self.play_start_explosion(), 0.14)

    def restart_game(self, *a):
        self._clear_game_over_overlay()
        self.game_over_shown = False
        try:
            self.board.clear()
        except Exception:
            pass
        self.score_manager.reset()
        self.update_labels()
        self.spawn_panel.clear_widgets()
        self.active_pieces.clear()
        self.remove_ghost()
        try:
            self.effect_layer.clear_widgets()
        except Exception:
            pass
        Clock.schedule_once(lambda dt: self.spawn_new_pieces(), 0.06)

    def update_labels(self):
        self.score_label.text = str(self.score_manager.score)
        self.best_label.text = str(self.score_manager.best_score)

    def spawn_new_pieces(self, *a):
        self.spawn_panel.clear_widgets()
        self.active_pieces.clear()
        if self.board.cell_size <= 0:
            Clock.schedule_once(lambda dt: self.spawn_new_pieces(), 0.04)
            return

        panel_w = max(self.spawn_panel.width, 1)
        panel_h = max(self.spawn_panel.height, 1)
        slot_w = panel_w / 3

        for i in range(3):
            piece = Piece(cell_size=self.board.cell_size)
            px = self.spawn_panel.x + i * slot_w + (slot_w - piece.width) / 2
            py = self.spawn_panel.y + (panel_h - piece.height) / 2
            piece.pos = piece.original_pos = (px, py)
            piece.opacity = 0
            self.spawn_panel.add_widget(piece)
            self.active_pieces.append(piece)
            Animation(opacity=1, duration=0.22, transition="out_quad").start(piece)

        Clock.schedule_once(self.check_game_over, 0.1)

    def remove_ghost(self):
        if self.ghost_piece:
            try: self.remove_widget(self.ghost_piece)
            except Exception: pass
        self.ghost_piece = None
        self.ghost_row = self.ghost_col = None
        self.board.highlight_cells = []
        self.board.redraw()

    def create_ghost(self, piece):
        self.remove_ghost()
        self.ghost_piece = GhostPiece(piece)
        self.add_widget(self.ghost_piece)

    def update_drag_preview(self, piece, touch):
        if not self.ghost_piece: self.create_ghost(piece)
        finger_x, finger_y = touch.x, touch.y + dp(72)
        pw = piece.cols * self.board.cell_size
        ph = piece.rows * self.board.cell_size

        col = int(math.floor((finger_x - pw / 2 - self.board.board_start_x) / self.board.cell_size))
        visual_row = int(math.floor((finger_y + ph / 2 - self.board.board_start_y) / self.board.cell_size))
        row = 7 - visual_row

        valid = (0 <= row < 8 and 0 <= col < 8 and self.board.can_place_piece(piece, row, col))
        self.ghost_piece.size = (piece.cols * self.board.cell_size, piece.rows * self.board.cell_size)
        self.ghost_piece.pos = (self.board.board_start_x + col * self.board.cell_size,
                                self.board.board_start_y + (8 - (row + piece.rows)) * self.board.cell_size)
        self.ghost_piece.set_valid(valid)

        highlights = []
        for dr, dc in piece.blocks:
            rr, cc = row + dr, col + dc
            if 0 <= rr < 8 and 0 <= cc < 8:
                highlights.append((rr, cc, valid))
            else:
                highlights.append((max(0, min(7, rr)), max(0, min(7, cc)), False))
        self.board.highlight_cells = highlights
        self.ghost_row, self.ghost_col = row, col
        self.board.redraw()

    def on_touch_down(self, touch):
        for piece in reversed(self.active_pieces):
            if piece.collide_point(*touch.pos):
                self.dragged_piece = piece
                piece.pick_up(touch)
                self.spawn_panel.remove_widget(piece)
                self.add_widget(piece)
                self.create_ghost(piece)
                self.update_drag_preview(piece, touch)
                return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.dragged_piece:
            self.dragged_piece.move_to(touch)
            self.update_drag_preview(self.dragged_piece, touch)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if not self.dragged_piece: return super().on_touch_up(touch)
        piece = self.dragged_piece
        piece.is_dragging = False
        row, col = self.ghost_row, self.ghost_col
        placed = False

        if row is not None and col is not None and self.board.can_place_piece(piece, row, col):
            try:
                self.board.place_piece(piece, row, col)
            except Exception:
                pass
            self.score_manager.add_piece_score(len(piece.blocks))
            try:
                lines, cleared = self.board.check_and_clear_lines()
            except Exception:
                lines, cleared = 0, []

            if lines:
                self.score_manager.add_lines(lines)
                combo = self.score_manager.combo
                intensity = min(2.0, 1.0 + lines * 0.18 + max(0, combo - 1) * 0.15)
                cx = self.board.board_start_x + self.board.cell_size * 4
                cy = self.board.board_start_y + self.board.cell_size * 4
                try:
                    FloatingText.show(self.effect_layer, lines, cx, cy, combo)
                except Exception:
                    pass

                # Вспышка экрана на сильных очистках / комбо
                if lines >= 3 or combo >= 3:
                    try:
                        flash_col = (1, 0.55, 0.2, 0.22) if combo >= 3 else (0.4, 0.9, 1, 0.18)
                        self.effect_layer.add_widget(ScreenFlash(color=flash_col, duration=0.25))
                    except Exception:
                        pass

                def _safe_burst(dt, px=cx, py=cy, col=(1, 0.85, 0.3, 1), cnt=8, inten=1.0):
                    try:
                        if self.effect_layer:
                            self.effect_layer.add_widget(
                                ParticleBurst(px, py, col, count=cnt, intensity=inten)
                            )
                    except Exception:
                        pass

                # Центральный взрыв
                Clock.schedule_once(
                    lambda dt: _safe_burst(dt, cx, cy, (1, 0.9, 0.35, 1), 12, intensity), 0.02
                )

                # Взрывы по очищенным клеткам (не больше 5, чтобы не убить FPS)
                seen = set()
                burst_i = 0
                for r, c, color in cleared:
                    key = (r, c)
                    if key in seen:
                        continue
                    seen.add(key)
                    if burst_i >= 5:
                        break
                    px = self.board.board_start_x + c * self.board.cell_size + self.board.cell_size / 2
                    py = self.board.board_start_y + (7 - r) * self.board.cell_size + self.board.cell_size / 2
                    delay = 0.04 + burst_i * 0.03
                    Clock.schedule_once(
                        lambda dt, x=px, y=py, col=color, k=burst_i: _safe_burst(
                            dt, x, y, col, 8, intensity * 0.85
                        ),
                        delay,
                    )
                    burst_i += 1

                # Лёгкий тряс поля на комбо
                if combo >= 2 or lines >= 3:
                    def shake(dt, amp=dp(5 + min(combo, 4))):
                        self.main_layout.x = random.uniform(-amp, amp)
                        self.main_layout.y = random.uniform(-amp * 0.7, amp * 0.7)

                    for i in range(8):
                        Clock.schedule_once(shake, i * 0.02)
                    Clock.schedule_once(lambda dt: setattr(self.main_layout, "pos", (0, 0)), 0.22)

            self.update_labels()
            data = SaveManager.load_data()
            self.blocksy_label.text = str(data.get("blocksy", 0))

            if piece in self.active_pieces: self.active_pieces.remove(piece)
            self.remove_widget(piece)
            placed = True

        self.remove_ghost()

        if not placed:
            self.remove_widget(piece)
            self.spawn_panel.add_widget(piece)
            piece.return_to_origin()

        self.dragged_piece = None

        if placed:
            if not self.active_pieces:
                Clock.schedule_once(lambda dt: self.spawn_new_pieces(), 0.12)
            else:
                Clock.schedule_once(self.check_game_over, 0.05)
        return True

    def check_game_over(self, *a):
        if self.game_over_shown or not self.active_pieces: return
        data = SaveManager.load_data()
        if data.get("god_mode", False): return

        for p in self.active_pieces:
            if self.board.can_fit_anywhere(p): return
        self.game_over_shown = True
        self.show_game_over()

    def show_game_over(self):
        name = SaveManager.get_player_name() or "Игрок"
        score = self.score_manager.score
        if score > 0:
            try:
                SaveManager.add_leaderboard_score(name, score)
            except Exception:
                pass

        overlay = FloatLayout()
        with overlay.canvas.before:
            Color(0, 0, 0, 0.75)
            Rectangle(pos=(0, 0), size=Window.size)

        panel = BoxLayout(orientation="vertical", size_hint=(0.86, 0.46), pos_hint={"center_x": 0.5, "center_y": 0.5}, padding=dp(16), spacing=dp(8))
        with panel.canvas.before:
            Color(0.05, 0.07, 0.12, 0.98)
            RoundedRectangle(pos=panel.pos, size=panel.size, radius=[dp(16)])

        panel.add_widget(Label(text="ИГРА ОКОНЧЕНА", font_size="22sp", bold=True, color=(1, 0.35, 0.45, 1)))
        panel.add_widget(Label(text=f"Игрок: {name}", font_size="14sp", color=(0.7, 0.85, 1, 1)))
        panel.add_widget(Label(text=f"Счёт: {score}", font_size="16sp"))
        panel.add_widget(Label(text=f"Рекорд: {self.score_manager.best_score}", font_size="15sp", color=(1, 0.8, 0.3, 1)))
        panel.add_widget(Label(text="Результат сохранён в таблицу лидеров", font_size="11sp", color=(0.5, 0.7, 0.6, 1)))

        restart = GlassButton(text="ИГРАТЬ СНОВА", bg=(0.12, 0.65, 0.40, 1), size_hint_y=None, height=dp(46))
        leaders = GlassButton(text="ТАБЛИЦА ЛИДЕРОВ", bg=(0.45, 0.28, 0.12, 1), size_hint_y=None, height=dp(42))
        panel.add_widget(restart)
        panel.add_widget(leaders)

        overlay.add_widget(panel)
        self._game_over_overlay = overlay
        self.add_widget(overlay)
        restart.bind(on_release=lambda i: (self._clear_game_over_overlay(), self.restart_game()))
        leaders.bind(on_release=lambda i: (self._clear_game_over_overlay(), setattr(self.manager, "current", "leaders")))

    def open_pause(self, i):
        self._clear_game_over_overlay()
        self.manager.current = "menu"


# ================================================================
# МЕНЮ
# ================================================================

class MenuScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bg = DynamicBackground(theme="Сакура")
        self.add_widget(self.bg)

        root = FloatLayout()
        layout = BoxLayout(orientation="vertical", size_hint=(0.85, 0.74), pos_hint={"center_x": 0.5, "center_y": 0.52}, spacing=dp(12))

        title = BoxLayout(orientation="vertical", size_hint_y=0.36)
        title.add_widget(Label(text="БЛОКС", font_size="48sp", bold=True, color=(0.96, 0.98, 1, 1)))
        title.add_widget(Label(text="STAFN", font_size="34sp", bold=True, color=(1, 0.38, 0.65, 1)))
        title.add_widget(Label(text="PUZZLE EXPERIENCE", font_size="9sp", color=(0.6, 0.72, 0.88, 1)))
        layout.add_widget(title)

        play = GlassButton(text="▶   ИГРАТЬ", bg=(0.12, 0.65, 0.38, 1), font_size="16sp", size_hint_y=None, height=dp(54))
        play.bind(on_release=self.open_name_prompt)
        layout.add_widget(play)

        leaders = GlassButton(text="🏆   ТАБЛИЦА ЛИДЕРОВ", bg=(0.45, 0.28, 0.12, 1), font_size="14sp", size_hint_y=None, height=dp(48))
        leaders.bind(on_release=lambda x: setattr(self.manager, "current", "leaders"))
        layout.add_widget(leaders)

        shop = GlassButton(text="🏪   МАГАЗИН (ЗА ПАЛКИ)", bg=(0.58, 0.18, 0.18, 1), font_size="15sp", size_hint_y=None, height=dp(50))
        shop.bind(on_release=lambda x: setattr(self.manager, "current", "shop"))
        layout.add_widget(shop)

        settings = GlassButton(text="⚙   НАСТРОЙКИ", bg=(0.14, 0.26, 0.46, 1), font_size="14sp", size_hint_y=None, height=dp(48))
        settings.bind(on_release=lambda x: setattr(self.manager, "current", "settings"))
        layout.add_widget(settings)

        root.add_widget(layout)
        root.add_widget(Label(text="БЛОКС STAFN  •  MOBILE EDITION", font_size="8sp", size_hint=(1, None), height=dp(18), pos_hint={"center_x": 0.5, "y": 0.02}, color=(0.4, 0.5, 0.6, 1)))
        self.add_widget(root)

    def open_name_prompt(self, *a):
        overlay = FloatLayout()
        with overlay.canvas.before:
            Color(0, 0, 0, 0.88)
            Rectangle(pos=(0, 0), size=Window.size)

        box = BoxLayout(orientation="vertical", size_hint=(0.88, 0.36), pos_hint={"center_x": 0.5, "center_y": 0.52},
                        padding=dp(16), spacing=dp(10))
        with box.canvas.before:
            Color(0.06, 0.08, 0.14, 0.98)
            RoundedRectangle(pos=box.pos, size=box.size, radius=[dp(18)])
            Color(0.3, 0.85, 0.55, 0.35)
            Line(rounded_rectangle=(box.x, box.y, box.width, box.height, dp(18)), width=1.6)

        box.add_widget(Label(text="ВВЕДИТЕ ИМЯ", font_size="18sp", bold=True, color=(0.4, 1, 0.7, 1)))
        box.add_widget(Label(text="Имя попадёт в таблицу лидеров", font_size="11sp", color=(0.6, 0.72, 0.85, 1)))

        saved = SaveManager.get_player_name()
        inp = TextInput(
            text=saved or "",
            multiline=False,
            size_hint_y=None,
            height=dp(48),
            font_size="16sp",
            background_color=(0.12, 0.14, 0.2, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0.3, 1, 0.7, 1),
            padding=[dp(12), dp(12)],
            hint_text="Ваше имя"
        )
        box.add_widget(inp)

        btns = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(46))
        ok = GlassButton(text="ИГРАТЬ", bg=(0.12, 0.55, 0.35, 1), font_size="13sp")
        cancel = GlassButton(text="ОТМЕНА", bg=(0.4, 0.2, 0.22, 1), font_size="13sp")
        btns.add_widget(ok)
        btns.add_widget(cancel)
        box.add_widget(btns)
        overlay.add_widget(box)
        self.add_widget(overlay)

        def start_game(*_):
            SaveManager.set_player_name(inp.text)
            self.remove_widget(overlay)
            self.manager.current = "game"

        ok.bind(on_release=start_game)
        cancel.bind(on_release=lambda x: self.remove_widget(overlay))
        Clock.schedule_once(lambda dt: setattr(inp, "focus", True), 0.12)

    def on_pre_leave(self, *a):
        if hasattr(self, "bg"):
            self.bg.set_active(False)

    def on_enter(self):
        data = SaveManager.load_data()
        if hasattr(self, "bg"):
            self.bg.set_active(True)
        self.bg.set_theme(data.get("bg_theme", "Сакура"))


# ================================================================
# МАГАЗИН
# ================================================================

class ShopScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bg = DynamicBackground(theme="Советский")
        self.add_widget(self.bg)

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        header = Label(text="УНИВЕРМАГ «БЛОКСЫ ЗА ПАЛКИ»", font_size="20sp", bold=True, color=(1, 0.95, 0.8, 1), size_hint_y=None, height=dp(42))
        root.add_widget(header)

        self.money_label = Label(text="Палки: 0   |   Блоксы: 0", font_size="16sp", color=(1, 0.9, 0.3, 1), size_hint_y=None, height=dp(28))
        root.add_widget(self.money_label)

        scroll = ScrollView()
        self.content = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))

        scroll.add_widget(self.content)
        root.add_widget(scroll)

        back = GlassButton(text="←   НАЗАД В МЕНЮ", bg=(0.32, 0.1, 0.1, 1), size_hint_y=None, height=dp(48))
        back.bind(on_release=lambda x: setattr(self.manager, "current", "menu"))
        root.add_widget(back)
        self.add_widget(root)

    def on_pre_leave(self, *a):
        if hasattr(self, "bg"):
            self.bg.set_active(False)

    def on_enter(self):
        if hasattr(self, "bg"):
            self.bg.set_active(True)
        self.refresh_shop()

    def refresh_shop(self):
        data = SaveManager.load_data()
        self.money_label.text = f"🥢 Палки: {data.get('owned_sticks', 0)}   |   💎 Блоксы: {data.get('blocksy', 0)}"
        self.content.clear_widgets()

        self.content.add_widget(Label(text="ФОНЫ И ТЕМЫ (ЗА ПАЛКИ)", font_size="14sp", bold=True, color=(0.95, 0.85, 0.6, 1), size_hint_y=None, height=dp(28)))
        unlocked = data.get("unlocked_themes", [])

        for name, info in SHOP_THEMES.items():
            if name in unlocked:
                btn = GlassButton(text=f"{name}  —  КУПЛЕНО", bg=(0.2, 0.35, 0.2, 1), size_hint_y=None, height=dp(46), font_size="13sp")
            else:
                btn = GlassButton(text=f"{name}  —  {info['price_sticks']} Палок", bg=(0.48, 0.15, 0.15, 1), size_hint_y=None, height=dp(46), font_size="13sp")
                btn.bind(on_release=lambda inst, n=name, p=info["price_sticks"]: self.buy_theme(n, p))
            self.content.add_widget(btn)

        self.content.add_widget(Label(text="ПРЕМИУМ СТИЛИ БЛОКОВ", font_size="14sp", bold=True, color=(0.95, 0.85, 0.6, 1), size_hint_y=None, height=dp(28)))
        unlocked_st = data.get("unlocked_styles", [])
        for name, info in SHOP_STYLES.items():
            if name in unlocked_st:
                btn = GlassButton(text=f"{name}  —  КУПЛЕНО", bg=(0.2, 0.35, 0.2, 1), size_hint_y=None, height=dp(46), font_size="13sp")
            else:
                btn = GlassButton(text=f"{name}  —  {info['price_sticks']} Палок", bg=(0.28, 0.15, 0.48, 1), size_hint_y=None, height=dp(46), font_size="13sp")
                btn.bind(on_release=lambda inst, n=name, p=info["price_sticks"]: self.buy_style(n, p))
            self.content.add_widget(btn)

        self.content.add_widget(Label(text="ОБМЕН В УНИВЕРМАГЕ", font_size="14sp", bold=True, color=(0.95, 0.85, 0.6, 1), size_hint_y=None, height=dp(28)))
        stick_btn = GlassButton(text="Купить 5 Палок  —  30 Блоксов", bg=(0.38, 0.26, 0.12, 1), size_hint_y=None, height=dp(46), font_size="13sp")
        stick_btn.bind(on_release=self.buy_sticks)
        self.content.add_widget(stick_btn)

    def buy_theme(self, name, price):
        data = SaveManager.load_data()
        if data.get("owned_sticks", 0) < price: return
        if name in data.get("unlocked_themes", []): return

        data["owned_sticks"] -= price
        data.setdefault("unlocked_themes", []).append(name)
        SaveManager.save_data(data)
        self.refresh_shop()

    def buy_style(self, name, price):
        data = SaveManager.load_data()
        if data.get("owned_sticks", 0) < price: return
        if name in data.get("unlocked_styles", []): return

        data["owned_sticks"] -= price
        data.setdefault("unlocked_styles", []).append(name)
        SaveManager.save_data(data)
        self.refresh_shop()

    def buy_sticks(self, *a):
        data = SaveManager.load_data()
        if data.get("blocksy", 0) < 30: return
        data["blocksy"] -= 30
        data["owned_sticks"] = data.get("owned_sticks", 0) + 5
        SaveManager.save_data(data)
        self.refresh_shop()


# ================================================================
# НАСТРОЙКИ С СКРЫТОЙ АДМИН-ПАНЕЛЬЮ
# ================================================================

class AdminOverlay(FloatLayout):
    def __init__(self, close_callback, **kwargs):
        super().__init__(**kwargs)
        self.close_callback = close_callback

        with self.canvas.before:
            Color(0, 0, 0, 0.9)
            Rectangle(pos=(0, 0), size=Window.size)

        box = BoxLayout(orientation="vertical", size_hint=(0.9, 0.52), pos_hint={"center_x": 0.5, "center_y": 0.5}, padding=dp(18), spacing=dp(10))
        with box.canvas.before:
            Color(0.05, 0.07, 0.12, 0.98)
            RoundedRectangle(pos=box.pos, size=box.size, radius=[dp(20)])
            Color(0.15, 0.65, 1.0, 0.4)
            Line(rounded_rectangle=(box.x + dp(1), box.y + dp(1), box.width - dp(2), box.height - dp(2), dp(19)), width=2.0)
            Color(0.4, 0.2, 0.8, 0.15)
            RoundedRectangle(pos=(box.x + dp(4), box.y + box.height * 0.7), size=(box.width - dp(8), box.height * 0.25), radius=[dp(12)])

        box.add_widget(Label(text="⚡  СИСТЕМА УПРАВЛЕНИЯ", font_size="19sp", bold=True, color=(0.35, 0.9, 1, 1)))
        box.add_widget(Label(text="Админ-панель • Полный доступ", font_size="11sp", color=(0.55, 0.7, 0.9, 0.9)))

        add_b = GlassButton(text="💎  +1000 БЛОКСОВ", bg=(0.12, 0.5, 0.28, 1), font_size="13sp", size_hint_y=None, height=dp(44))
        add_b.bind(on_release=self.add_blocksy)
        box.add_widget(add_b)

        add_s = GlassButton(text="🥢  +100 ПАЛОК", bg=(0.5, 0.28, 0.12, 1), font_size="13sp", size_hint_y=None, height=dp(44))
        add_s.bind(on_release=self.add_sticks)
        box.add_widget(add_s)

        self.god_btn = GlassButton(text="💀  РЕЖИМ БЕССМЕРТИЯ: ВЫКЛ", bg=(0.28, 0.18, 0.45, 1), font_size="13sp", size_hint_y=None, height=dp(44))
        self.god_btn.bind(on_release=self.toggle_god)
        box.add_widget(self.god_btn)
        self.update_god_label()

        close = GlassButton(text="✕  ЗАКРЫТЬ ПАНЕЛЬ", bg=(0.55, 0.14, 0.18, 1), font_size="13sp", size_hint_y=None, height=dp(44))
        close.bind(on_release=lambda x: self.close_callback())
        box.add_widget(close)

        self.add_widget(box)

    def add_blocksy(self, *a):
        data = SaveManager.load_data()
        data["blocksy"] = data.get("blocksy", 0) + 1000
        SaveManager.save_data(data)

    def add_sticks(self, *a):
        data = SaveManager.load_data()
        data["owned_sticks"] = data.get("owned_sticks", 0) + 100
        SaveManager.save_data(data)

    def update_god_label(self):
        data = SaveManager.load_data()
        val = data.get("god_mode", False)
        self.god_btn.text = f"РЕЖИМ БЕССМЕРТИЯ: {'ВКЛ' if val else 'ВЫКЛ'}"

    def toggle_god(self, *a):
        data = SaveManager.load_data()
        data["god_mode"] = not data.get("god_mode", False)
        SaveManager.save_data(data)
        self.update_god_label()


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        data = SaveManager.load_data()
        self.bg = DynamicBackground(theme=data.get("bg_theme", "Сакура"))
        self.add_widget(self.bg)

        self.secret_clicks = 0
        self.last_click_time = 0

        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        root.add_widget(Label(text="НАСТРОЙКИ", font_size="22sp", bold=True, size_hint_y=None, height=dp(38)))

        self.accordion = Accordion(orientation="vertical", size_hint_y=0.78, min_space=dp(42))

        self.item_bg = AccordionItem(title="  Фон / Темы")
        self.bg_box = BoxLayout(orientation="vertical", spacing=dp(5), padding=[dp(6), dp(4), dp(6), dp(6)])
        self.item_bg.add_widget(self.bg_box)
        self.accordion.add_widget(self.item_bg)

        item_style = AccordionItem(title="  Кастомизация блоков (Стиль 3D)")
        self.style_box = BoxLayout(orientation="vertical", spacing=dp(5), padding=[dp(6), dp(4), dp(6), dp(6)])
        item_style.add_widget(self.style_box)
        self.accordion.add_widget(item_style)

        item_pal = AccordionItem(title="  Цвета блоков")
        pal_box = BoxLayout(orientation="vertical", spacing=dp(5), padding=[dp(6), dp(4), dp(6), dp(6)])
        for n in ["Неон", "Классика", "Пастель", "Огонь", "Лёд"]:
            b = GlassButton(text=n, font_size="12sp", bg=(0.18, 0.15, 0.32, 1), size_hint_y=None, height=dp(38))
            b.bind(on_release=lambda inst, name=n: self.set_palette(name))
            pal_box.add_widget(b)
        item_pal.add_widget(pal_box)
        self.accordion.add_widget(item_pal)

        item_fps = AccordionItem(title="  FPS (Герцовка)")
        self.fps_box = BoxLayout(orientation="vertical", spacing=dp(5), padding=[dp(6), dp(4), dp(6), dp(6)])
        item_fps.add_widget(self.fps_box)
        self.accordion.add_widget(item_fps)

        item_sys = AccordionItem(title="  Система и Сброс")
        sys_box = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(8))
        
        self.device_btn = GlassButton(text=f"📱  Устройство: {get_device_name()}", font_size="12sp",
                                     bg=(0.12, 0.18, 0.28, 0.95), size_hint_y=None, height=dp(42))
        self.device_btn.bind(on_release=self.on_device_tap)

        self.hz_label = Label(text="Экран: -- Гц", font_size="11sp", size_hint_y=None, height=dp(20), color=(0.4, 0.9, 0.7, 1))
        self.cpu_label = Label(text="CPU: --", font_size="11sp", size_hint_y=None, height=dp(20))
        self.ram_label = Label(text="RAM: --", font_size="11sp", size_hint_y=None, height=dp(20))
        
        reset_btn = GlassButton(text="⚠️ СБРОСИТЬ ВЕСЬ ПРОГРЕСС И РЕКОРД", bg=(0.7, 0.12, 0.12, 1), font_size="12sp", size_hint_y=None, height=dp(42))
        reset_btn.bind(on_release=self.confirm_reset_dialog)

        sys_box.add_widget(self.device_btn)
        sys_box.add_widget(self.hz_label)
        sys_box.add_widget(self.cpu_label)
        sys_box.add_widget(self.ram_label)
        sys_box.add_widget(reset_btn)
        item_sys.add_widget(sys_box)
        self.accordion.add_widget(item_sys)

        root.add_widget(self.accordion)

        back = GlassButton(text="←   НАЗАД", bg=(0.58, 0.14, 0.20, 1), size_hint_y=None, height=dp(46))
        back.bind(on_release=lambda x: setattr(self.manager, "current", "menu"))
        root.add_widget(back)
        self.add_widget(root)

        Clock.schedule_interval(self.update_stats, 1.2)

    def on_device_tap(self, *a):
        now = time.time()
        # Более надёжная детекция на телефонах: собираем timestamps
        if not hasattr(self, '_tap_times'):
            self._tap_times = []
        self._tap_times = [t for t in self._tap_times if now - t < 2.5]
        self._tap_times.append(now)
        self.secret_clicks = len(self._tap_times)
        self.last_click_time = now

        if self.secret_clicks >= 5:
            self._tap_times = []
            self.secret_clicks = 0
            self.prompt_admin_code()

    def prompt_admin_code(self):
        overlay = FloatLayout()
        with overlay.canvas.before:
            Color(0, 0, 0, 0.88)
            Rectangle(pos=(0, 0), size=Window.size)

        box = BoxLayout(orientation="vertical", size_hint=(0.88, 0.36), pos_hint={"center_x": 0.5, "center_y": 0.52}, padding=dp(16), spacing=dp(12))
        with box.canvas.before:
            Color(0.06, 0.08, 0.14, 0.98)
            RoundedRectangle(pos=box.pos, size=box.size, radius=[dp(18)])
            Color(0.2, 0.55, 1.0, 0.35)
            Line(rounded_rectangle=(box.x, box.y, box.width, box.height, dp(18)), width=1.8)

        box.add_widget(Label(text="🔐  СИСТЕМА ДОСТУПА", font_size="17sp", bold=True, color=(0.35, 0.85, 1, 1)))
        box.add_widget(Label(text="Введите код администратора", font_size="11sp", color=(0.6, 0.7, 0.85, 1)))

        inp = TextInput(multiline=False, password=True, size_hint_y=None, height=dp(48),
                        font_size="16sp", background_color=(0.12, 0.14, 0.2, 1),
                        foreground_color=(1, 1, 1, 1), cursor_color=(0.3, 0.9, 1, 1),
                        padding=[dp(12), dp(12)])
        box.add_widget(inp)

        btns = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(46))
        ok = GlassButton(text="ВХОД", bg=(0.12, 0.55, 0.35, 1), font_size="13sp")
        cancel = GlassButton(text="ОТМЕНА", bg=(0.45, 0.18, 0.22, 1), font_size="13sp")

        btns.add_widget(ok)
        btns.add_widget(cancel)
        box.add_widget(btns)
        overlay.add_widget(box)
        self.add_widget(overlay)

        def check(*a):
            code = inp.text
            self.remove_widget(overlay)
            if verify_admin_code(code):
                admin_ov = AdminOverlay(close_callback=lambda: self.remove_widget(admin_ov))
                self.add_widget(admin_ov)

        ok.bind(on_release=check)
        cancel.bind(on_release=lambda x: self.remove_widget(overlay))
        # Автофокус на поле ввода (важно для телефона)
        Clock.schedule_once(lambda dt: setattr(inp, 'focus', True), 0.15)

    def on_pre_leave(self, *a):
        if hasattr(self, "bg"):
            self.bg.set_active(False)

    def on_enter(self):
        screen_hz = get_screen_refresh_rate()
        data = SaveManager.load_data()
        if hasattr(self, "bg"):
            self.bg.set_active(True)
        self.bg.set_theme(data.get("bg_theme", "Сакура"))
        self.device_btn.text = f"📱  Устройство: {get_device_name()}"
        self.hz_label.text = f"Дисплей: {screen_hz} Гц (Макс. лимит)"

        self.style_box.clear_widgets()
        unlocked_styles = data.get("unlocked_styles", ["Стеклянный Взрыв", "Классика 3D", "Глянец", "Киберпанк"])
        curr_style = data.get("block_style", "Стеклянный Взрыв")
        for s in unlocked_styles:
            active_mark = " (Активно)" if s == curr_style else ""
            b = GlassButton(text=f"{s}{active_mark}", font_size="12sp", bg=(0.14, 0.32, 0.42, 1), size_hint_y=None, height=dp(38))
            b.bind(on_release=lambda inst, st=s: self.set_block_style(st))
            self.style_box.add_widget(b)

        self.fps_box.clear_widgets()
        allowed_fps = [f for f in [30, 60, 90, 120, 144] if f <= screen_hz]
        if not allowed_fps: allowed_fps = [screen_hz]

        for f in allowed_fps:
            b = GlassButton(text=f"Лимит: {f} FPS", font_size="12sp", bg=(0.12, 0.28, 0.24, 1), size_hint_y=None, height=dp(38))
            b.bind(on_release=lambda inst, val=f: self.set_fps(val))
            self.fps_box.add_widget(b)

        self.bg_box.clear_widgets()
        unlocked = data.get("unlocked_themes", ["Сакура", "Зима", "Горы & Ветер", "Тёмная"])
        for t in unlocked:
            b = GlassButton(text=t, font_size="12sp", bg=(0.14, 0.24, 0.40, 1), size_hint_y=None, height=dp(38))
            b.bind(on_release=lambda inst, th=t: self.set_theme(th))
            self.bg_box.add_widget(b)

    def confirm_reset_dialog(self, *a):
        overlay = FloatLayout()
        with overlay.canvas.before:
            Color(0, 0, 0, 0.8)
            Rectangle(pos=(0, 0), size=Window.size)

        box = BoxLayout(orientation="vertical", size_hint=(0.85, 0.32), pos_hint={"center_x": 0.5, "center_y": 0.5}, padding=dp(14), spacing=dp(10))
        with box.canvas.before:
            Color(0.1, 0.05, 0.05, 0.98)
            RoundedRectangle(pos=box.pos, size=box.size, radius=[dp(14)])

        box.add_widget(Label(text="ПОЛНЫЙ СБРОС", font_size="18sp", bold=True, color=(1, 0.3, 0.3, 1)))
        box.add_widget(Label(text="Вы действительно хотите сбросить рекорд, блоксы, палки и покупки?", font_size="11sp", halign="center"))

        btns = BoxLayout(spacing=dp(10), size_hint_y=None, height=dp(44))
        yes = GlassButton(text="ДА, СБРОСИТЬ ВСЁ", bg=(0.7, 0.15, 0.15, 1), font_size="11sp")
        no = GlassButton(text="ОТМЕНА", bg=(0.2, 0.4, 0.2, 1), font_size="11sp")

        btns.add_widget(yes)
        btns.add_widget(no)
        box.add_widget(btns)
        overlay.add_widget(box)
        self.add_widget(overlay)

        no.bind(on_release=lambda x: self.remove_widget(overlay))
        yes.bind(on_release=lambda x: (self.do_reset(), self.remove_widget(overlay)))

    def do_reset(self):
        SaveManager.reset_progress()
        game_screen = self.manager.get_screen("game")
        game_screen.score_manager.reset()
        game_screen.update_labels()
        self.on_enter()

    def set_block_style(self, style_name):
        data = SaveManager.load_data()
        data["block_style"] = style_name
        SaveManager.save_data(data)
        invalidate_visual_cache()
        self.on_enter()

    def set_theme(self, theme):
        data = SaveManager.load_data()
        data["bg_theme"] = theme
        SaveManager.save_data(data)
        self.bg.set_theme(theme)

    def set_palette(self, name):
        data = SaveManager.load_data()
        data["block_palette"] = name
        SaveManager.save_data(data)
        invalidate_visual_cache()

    def set_fps(self, value):
        screen_hz = get_screen_refresh_rate()
        val = min(int(value), screen_hz)
        data = SaveManager.load_data()
        data["max_fps"] = val
        SaveManager.save_data(data)
        Clock.max_fps = val

    def update_stats(self, dt):
        if HAS_PSUTIL:
            try:
                self.cpu_label.text = f"CPU: {int(psutil.cpu_percent())}%"
                self.ram_label.text = f"RAM: {int(psutil.virtual_memory().percent)}%"
            except Exception:
                self.cpu_label.text = "CPU: н/д"
                self.ram_label.text = "RAM: н/д"
        else:
            self.cpu_label.text = "CPU: недоступно"
            self.ram_label.text = "RAM: недоступно"


# ================================================================
# ТАБЛИЦА ЛИДЕРОВ
# ================================================================

class LeaderboardScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bg = DynamicBackground(theme="Космос")
        self.add_widget(self.bg)
        self._loading = False

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(6))
        root.add_widget(Label(text="🏆  ТАБЛИЦА ЛИДЕРОВ", font_size="22sp", bold=True,
                              color=(1, 0.9, 0.45, 1), size_hint_y=None, height=dp(40)))
        self.subtitle = Label(text="Общая / локальная", font_size="11sp",
                              color=(0.6, 0.75, 0.9, 1), size_hint_y=None, height=dp(20))
        root.add_widget(self.subtitle)

        url_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        self.url_input = TextInput(
            text=SaveManager.get_leaderboard_url(),
            multiline=False,
            hint_text="http://IP:8765  (адрес сервера)",
            font_size="12sp",
            background_color=(0.1, 0.12, 0.18, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0.4, 1, 0.7, 1),
            padding=[dp(8), dp(10)],
        )
        save_url = GlassButton(text="ОК", bg=(0.15, 0.45, 0.3, 1), size_hint_x=None, width=dp(56), font_size="12sp")
        save_url.bind(on_release=self.save_url)
        url_row.add_widget(self.url_input)
        url_row.add_widget(save_url)
        root.add_widget(url_row)

        self.status = Label(text="", font_size="11sp", color=(0.5, 0.85, 0.7, 1),
                            size_hint_y=None, height=dp(18))
        root.add_widget(self.status)

        actions = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        refresh_btn = GlassButton(text="🔄  ОБНОВИТЬ", bg=(0.18, 0.28, 0.45, 1), font_size="12sp")
        refresh_btn.bind(on_release=lambda x: self.refresh(online=True))
        actions.add_widget(refresh_btn)
        root.add_widget(actions)

        scroll = ScrollView()
        self.content = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        scroll.add_widget(self.content)
        root.add_widget(scroll)

        back = GlassButton(text="←   НАЗАД В МЕНЮ", bg=(0.32, 0.12, 0.14, 1), size_hint_y=None, height=dp(48))
        back.bind(on_release=lambda x: setattr(self.manager, "current", "menu"))
        root.add_widget(back)
        self.add_widget(root)

    def save_url(self, *a):
        url = SaveManager.set_leaderboard_url(self.url_input.text)
        self.url_input.text = url
        self.status.text = "Адрес сохранён" if url else "URL очищен — только локальная таблица"
        self.status.color = (0.4, 1, 0.7, 1)
        self.refresh(online=True)

    def on_pre_leave(self, *a):
        if hasattr(self, "bg"):
            self.bg.set_active(False)

    def on_enter(self):
        if hasattr(self, "bg"):
            self.bg.set_active(True)
            data = SaveManager.load_data()
            self.bg.set_theme(data.get("bg_theme", "Космос"))
        self.url_input.text = SaveManager.get_leaderboard_url()
        self.refresh(online=True)

    def _render_board(self, board, mode_text):
        self.content.clear_widgets()
        name_now = SaveManager.get_player_name() or "—"
        self.subtitle.text = f"{mode_text}  •  Вы: {name_now}"

        if not board:
            self.content.add_widget(Label(
                text="Пока пусто.\nСыграйте партию — результат появится здесь.",
                font_size="14sp", color=(0.55, 0.65, 0.8, 1),
                size_hint_y=None, height=dp(80), halign="center"
            ))
            return

        medals = ["🥇", "🥈", "🥉"]
        for i, entry in enumerate(board):
            n = entry.get("name", "Игрок")
            s = int(entry.get("score", 0))
            mark = medals[i] if i < 3 else f"{i + 1}."
            bg = (0.28, 0.22, 0.1, 1) if i == 0 else (0.16, 0.18, 0.28, 1) if i < 3 else (0.12, 0.14, 0.2, 1)
            row = GlassButton(
                text=f"{mark}  {n}   —   {s}",
                bg=bg, font_size="14sp",
                size_hint_y=None, height=dp(44)
            )
            self.content.add_widget(row)

    def refresh(self, online=False):
        local = SaveManager.get_leaderboard()
        if not online or not SaveManager.get_leaderboard_url():
            self.status.text = "Локальная таблица (сервер не задан)"
            self.status.color = (0.7, 0.75, 0.85, 1)
            self._render_board(local, "Локально")
            return

        if self._loading:
            return
        self._loading = True
        self.status.text = "Загрузка с сервера..."
        self.status.color = (0.5, 0.85, 1, 1)
        self._render_board(local, "Локально (ждём сервер)")

        def done(board, err):
            self._loading = False
            if board is not None:
                self.status.text = f"Общая таблица • {len(board)} записей"
                self.status.color = (0.4, 1, 0.65, 1)
                self._render_board(board, "Общая (онлайн)")
            else:
                self.status.text = f"Сервер недоступен: {err or 'ошибка'}"
                self.status.color = (1, 0.45, 0.4, 1)
                self._render_board(local, "Локально (офлайн)")

        OnlineLeaderboard.fetch_async(done)


# ================================================================
# ОСНОВНОЕ ПРИЛОЖЕНИЕ
# ================================================================

class BlocksStafnApp(App):
    def build(self):
        Window.clearcolor = (0.008, 0.012, 0.02, 1)
        screen_hz = get_screen_refresh_rate()
        data = SaveManager.load_data()
        Clock.max_fps = min(int(data.get("max_fps", screen_hz)), screen_hz)

        sm = ScreenManager(transition=FadeTransition(duration=0.20))
        sm.add_widget(MenuScreen(name="menu"))
        sm.add_widget(GameScreen(name="game"))
        sm.add_widget(SettingsScreen(name="settings"))
        sm.add_widget(ShopScreen(name="shop"))
        sm.add_widget(LeaderboardScreen(name="leaders"))
        return sm


if __name__ == "__main__":
    BlocksStafnApp().run()
