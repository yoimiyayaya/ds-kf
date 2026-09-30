# -*- coding: utf-8 -*-
"""
饿饿饭饭 · 余额桌宠 V3
======================

一只端着空碗的小家伙，蹲在桌面角落帮你盯着 DeepSeek 账户余额。
余额就是她的饭钱：钱多她笑，钱少她饿，没钱碗就空了。

    ┌────────────────────────┐
    │ 饿饿饭饭 · 余额      ● │   ← 状态灯
    │ ¥128.66                │   ← 主数字
    │ 赠金 ¥8.66 · 充值 ¥120  │   ← 金额构成
    │ 12:30 更新 · 4分55秒后…│   ← 倒计时
    │ ▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░ │   ← 刷新进度条
    └───────────┬────────────┘
            立绘（点击刷新）

交互
----
    左键单击桌宠   立刻刷新余额（本程序最核心的用法）
    左键拖动       移动桌宠，松手后自动记住位置
    右键           菜单：立刻刷新 / 每隔 1、5、10 分钟刷新 / 暂停 / 置顶 / 密钥 / 退出
    Esc            退出

    「每隔 1 分钟刷新」「每隔 5 分钟刷新」「每隔 10 分钟刷新」三档是固定的，
    选中的那一档会记在 config.json 里，下次启动照旧。

刷新节奏
--------
    自动刷新由「刷新进度条 + 倒计时」提示；单击桌宠手动刷新后，倒计时重新开始。

依赖
----
    只用 Python 标准库（tkinter + urllib + threading），不需要 pip 安装任何东西。
    立绘素材在 assets/ 里，由 build_assets.py 从原始图片一次性生成（构建期才需要 Pillow）。

文件
----
    balance_pet.py   桌宠本体，唯一需要运行的脚本
    assets/          立绘素材与图标
    启动桌宠.bat      双击启动（优先 pythonw，无黑窗）
    启动桌宠.vbs      完全静默启动（桌面快捷方式指向它）
    诊断.bat         环境 / 素材 / 配置 / 接口 自检
    config.json      首次运行后生成，存密钥与偏好
"""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

# ------------------------------------------------------------------ 基本常量

APP_NAME = "饿饿饭饭"
APP_SUB = "余额桌宠"
VERSION = "3.0"

# 自动刷新只提供这三档（需求就是这三档），0 表示暂停
INTERVAL_CHOICES = (60, 300, 600)
INTERVAL_LABEL = {
    60: "每隔 1 分钟刷新",
    300: "每隔 5 分钟刷新",
    600: "每隔 10 分钟刷新",
    0: "暂停自动刷新",
}

DEFAULT_BASE_URL = "https://api.deepseek.com"

# 立绘尺寸阶梯：素材就是按这些倍数生成的，菜单里的「大小」正好一一对应。
# 实际倍数 = 屏幕缩放 × size_scale，再挑阶梯里最接近的一档。
SIZE_CHOICES = (0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5)
SIZE_LABEL = {
    0.6: "很小（60%）",
    0.8: "小（80%）",
    1.0: "标准（100%）",
    1.25: "大（125%）",
    1.5: "特大（150%）",
    2.0: "巨大（200%）",
    2.5: "超大（250%）",
}

# 窗口不透明度
OPACITY_CHOICES = (1.0, 0.95, 0.9, 0.85, 0.8, 0.7, 0.6, 0.5, 0.4)
OPACITY_LABEL = {
    1.0: "100%（不透明）",
    0.95: "95%",
    0.9: "90%",
    0.85: "85%",
    0.8: "80%",
    0.7: "70%",
    0.6: "60%",
    0.5: "50%",
    0.4: "40%（很淡）",
}

DEFAULT_CONFIG = {
    "api_key": "",                       # DeepSeek 密钥（sk- 开头）
    "base_url": DEFAULT_BASE_URL,        # 接口地址，可指向代理
    "interval_sec": 300,                 # 60 / 300 / 600，或 0 = 暂停
    "low_threshold": 10.0,               # 低于该金额开始喊饿
    "size_scale": 1.0,                   # 桌宠大小：SIZE_CHOICES 里的一档
    "opacity": 1.0,                      # 整体不透明度：0.3 ~ 1.0
    "always_on_top": True,
    "pos": None,                         # 上次窗口位置 [x, y]
}

# 透明色键：必须与素材里的键色一致，且立绘中不含该颜色
KEY_COLOR = "#ff00ff"

# 配色（贴合立绘的蓝白调）
PANEL = "#151f36"
PANEL_EDGE = "#2c3d61"
TRACK = "#243352"
TEXT = "#eaf1ff"
DIM = "#94a5c5"
ACCENT = "#5b8dff"
GOOD = "#57d69b"
WARN = "#ffb648"
BAD = "#ff6b6b"
GOLD = "#ffd76e"

# 自绘右键菜单的配色
MENU_BG = "#161f33"
MENU_EDGE = "#33456b"
MENU_HOT = "#2f4a86"
MENU_SEP = "#2b3a5c"

FONT_UI = "Microsoft YaHei UI"
FONT_MONO = "Consolas"

# 布局基准值（都按 96 DPI 设计，运行时再乘缩放系数）
BASE_PET_W = 240
BASE_BUBBLE_W = 252
BASE_BUBBLE_H = 104
BASE_PAD = 10
BASE_TAIL = 14
BASE_BOTTOM = 14

# 立绘素材：文件按倍数命名，运行时按实际需要的倍数挑最接近的一张
PET_ASSETS = (
    (0.60, "pet_060.png"),
    (0.80, "pet_080.png"),
    (1.00, "pet.png"),
    (1.25, "pet_125.png"),
    (1.50, "pet_150.png"),
    (2.00, "pet_200.png"),
    (2.50, "pet_250.png"),
    (3.00, "pet_300.png"),
)

# ------------------------------------------------------------------ 路径


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):                       # 将来若打包成 exe
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = _app_dir()
CONFIG_PATH = APP_DIR / "config.json"
ASSET_DIR = APP_DIR / "assets"
PET_IMAGE = ASSET_DIR / "pet.png"
ICON_FILE = ASSET_DIR / "pet.ico"
ERROR_LOG = APP_DIR / "pet_error.log"
CONFIG_ERROR = ""                 # config.json 读失败时的提示（load_config 填）


# ------------------------------------------------------------------ 小工具


def warn(text: str) -> None:
    """往 stderr 打字，但绝不因为编码问题把程序搞崩。"""
    try:
        print(text, file=sys.stderr)
    except Exception:
        try:
            sys.stderr.write(text.encode("ascii", "replace").decode("ascii") + "\n")
        except Exception:
            pass


def init_console() -> None:
    """把控制台切到 UTF-8；失败就算了，不影响桌宠。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def enable_dpi_awareness() -> None:
    """在创建 Tk 窗口之前声明 DPI 感知，高分屏下字和立绘才不糊。"""
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)      # 系统 DPI 感知
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def money(value: float, symbol: str = "¥") -> str:
    """金额格式化：小额多留几位小数，免得显示成 ¥0.00。"""
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 1:
        return f"{symbol}{value:,.2f}"
    if value > 0:
        return f"{symbol}{value:.4f}"
    return f"{symbol}0.00"


def to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def human_interval(sec: int) -> str:
    sec = int(sec or 0)
    if sec <= 0:
        return INTERVAL_LABEL[0]
    if sec % 60 == 0:
        return f"每隔 {sec // 60} 分钟刷新"
    return f"每隔 {sec} 秒刷新"


def countdown_text(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds >= 60:
        return f"{seconds // 60}分{seconds % 60:02d}秒"
    return f"{seconds} 秒"


def clock_text(ts: float | None = None) -> str:
    return time.strftime("%H:%M", time.localtime(ts if ts else time.time()))


def clamp(value, low, high):
    return max(low, min(high, value))


# ------------------------------------------------------------------ 配置读写


def normalize_config(cfg: dict) -> dict:
    """把读进来的字典收拾干净，任何脏数据都不该让桌宠起不来。"""
    out = dict(DEFAULT_CONFIG)
    if isinstance(cfg, dict):
        for key in DEFAULT_CONFIG:
            if key in cfg:
                out[key] = cfg[key]

    try:
        iv = int(out.get("interval_sec", 300))
    except (TypeError, ValueError):
        iv = 300
    out["interval_sec"] = iv if (iv in INTERVAL_CHOICES or iv == 0) else 300

    try:
        out["low_threshold"] = float(out.get("low_threshold", 10.0))
    except (TypeError, ValueError):
        out["low_threshold"] = 10.0

    out["api_key"] = str(out.get("api_key") or "").strip()
    out["base_url"] = str(out.get("base_url") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    out["always_on_top"] = bool(out.get("always_on_top", True))

    # 大小：吸附到最近的素材档位（手改配置写个 1.3 也能用）
    size = to_float(out.get("size_scale"), 1.0)
    out["size_scale"] = min(SIZE_CHOICES, key=lambda c: abs(c - size))

    # 不透明度：夹在 0.3 ~ 1.0 之间，允许手改任意值
    out["opacity"] = round(clamp(to_float(out.get("opacity"), 1.0), 0.3, 1.0), 3)

    pos = out.get("pos")
    if not (isinstance(pos, (list, tuple)) and len(pos) == 2):
        out["pos"] = None
    else:
        try:
            out["pos"] = [int(pos[0]), int(pos[1])]
        except (TypeError, ValueError):
            out["pos"] = None
    return out


def load_config() -> dict:
    """读配置。用 utf-8-sig 是为了容忍记事本存出来的 BOM ——
    否则 BOM 会让整个 JSON 解析失败，用户的密钥被静默忽略。"""
    global CONFIG_ERROR
    CONFIG_ERROR = ""
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
            return normalize_config(raw)
        except Exception as exc:
            CONFIG_ERROR = f"config.json 读不出来（{type(exc).__name__}），已改用默认配置"
            warn(f"[warn] {CONFIG_ERROR}：{exc}")
    return normalize_config({})


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except Exception as exc:
        warn(f"[warn] 配置保存失败：{exc}")


def resolve_key(cfg: dict) -> str:
    """环境变量优先（方便临时换密钥），其次是 config.json。"""
    return (os.environ.get("DEEPSEEK_API_KEY") or cfg.get("api_key") or "").strip()


# ------------------------------------------------------------------ 余额接口


def fetch_balance(api_key: str, base_url: str, timeout: float = 12.0) -> dict:
    """GET {base_url}/user/balance，失败抛 RuntimeError（带人话原因）。"""
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + "/user/balance"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": f"balance-pet/{VERSION}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
            detail = ((payload.get("error") or {}).get("message")
                      or payload.get("message") or "")
        except Exception:
            pass
        if exc.code == 401:
            raise RuntimeError("密钥无效或已失效 (401)") from exc
        if exc.code == 403:
            raise RuntimeError("这把密钥没有查余额的权限 (403)") from exc
        if exc.code == 429:
            raise RuntimeError("问得太频繁了，歇会儿再问 (429)") from exc
        raise RuntimeError(f"接口报错 HTTP {exc.code} {detail}".strip()) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络不通：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("接口返回的不是合法 JSON") from exc


def parse_balance(payload: dict) -> dict:
    """把接口返回整理成好用的字典。"""
    infos = payload.get("balance_infos") or []
    info = {}
    if isinstance(infos, list):
        for item in infos:
            if isinstance(item, dict) and item.get("currency") == "CNY":
                info = item
                break
        if not info and infos and isinstance(infos[0], dict):
            info = infos[0]
    currency = str(info.get("currency") or "CNY")
    symbol = {"CNY": "¥", "USD": "$"}.get(currency, "")
    return {
        "total": to_float(info.get("total_balance")),
        "granted": to_float(info.get("granted_balance")),
        "topped_up": to_float(info.get("topped_up_balance")),
        "currency": currency,
        "symbol": symbol,
        "available": bool(payload.get("is_available", True)),
        "raw": payload,
    }


# ------------------------------------------------------------------ 自绘菜单


class MenuPanel:
    """自己画的右键菜单：一个无边框置顶小窗口 + Canvas，点击靠自己的绑定收。

    为什么不用 Tk 原生菜单？因为在这只桌宠窗口上它不可靠：
    原生菜单其实是系统弹的独立窗口，Tk 那边靠 grab 收事件，实测
    「菜单弹出来了，点任何一项都只把菜单收掉、命令不执行」。
    自绘之后点击走的是我们自己的 Canvas 绑定（桌宠本身的点击就是这么工作的），
    稳、可测，样式也能跟气泡统一。
    """

    def __init__(self, pet, rows, x, y):
        import tkinter.font as tkfont

        self.pet = pet
        self.stack = [rows]                       # 下钻历史，返回时弹栈
        self.hot = -1
        self.x = self.y = 0
        self.opened_at = time.time()
        self._closing = False
        self.tk = pet.tk

        s = max(1.0, pet.dpi)                     # 菜单尺寸跟屏幕缩放走，不跟桌宠大小
        self.s = s
        self.row_h = int(round(26 * s))
        self.sep_h = max(5, int(round(9 * s)))
        self.pad_x = int(round(12 * s))
        self.pad_y = max(3, int(round(5 * s)))
        self.indent = int(round(10 * s))
        self.font_main = tkfont.Font(family=FONT_UI, size=-pet._fpx(9, s))
        self.font_small = tkfont.Font(family=FONT_UI, size=-pet._fpx(8, s))

        self.width = self._measure_width()
        self.height = self._panel_height()

        self.win = self.tk.Toplevel(pet.root)
        self.win.overrideredirect(True)
        try:
            self.win.attributes("-topmost", True)
        except self.tk.TclError:
            pass
        try:
            self.win.wm_attributes("-transparentcolor", KEY_COLOR)
        except self.tk.TclError:
            pass
        self.canvas = self.tk.Canvas(self.win, width=self.width, height=self.height,
                                     bg=KEY_COLOR, highlightthickness=0, bd=0)
        self.canvas.pack()
        self._place(x, y)
        self.canvas.bind("<Motion>", self._on_motion)
        # 必须绑「按下」而不是「点击」：右键开菜单的那次「松开」会被 grab 送到这里，
        # 绑 <Button-1/3> 的话菜单刚弹出来就被自己收掉了。
        self.canvas.bind("<ButtonPress-1>", self._on_click)
        self.canvas.bind("<ButtonPress-3>", self._on_click)
        self.win.bind("<Escape>", lambda _e: self.close())
        self.win.bind("<FocusOut>", self._on_focus_out)
        try:
            self.win.focus_force()
        except self.tk.TclError:
            pass
        self._force_topmost()
        self._draw()
        # 这里刻意不 grab_set()：实测局内抓取会把「面板外面」的点击吞掉——
        # 桌宠收不到（不刷新），面板也收不到（不收菜单），点了跟没点一样。
        # 改成「桌宠自己收 + 轮询鼠标」来收菜单，见 BalancePet._poll_menu_dismiss。

    @property
    def rows(self) -> list:
        return self.stack[-1]

    def _force_topmost(self) -> None:
        """把菜单压到最上层。

        Tk 的 -topmost 只是 SetWindowPos 一次，实测别的置顶窗口（比如聊天窗口）
        晚一步激活就会盖住菜单，点了等于点在别人身上，所以这里再明确压一次。
        """
        if os.name != "nt":
            return
        try:
            import ctypes

            hwnd = self.win.winfo_id()
            root = ctypes.windll.user32.GetAncestor(hwnd, 2)   # GA_ROOT
            if not root:
                return
            SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
            ctypes.windll.user32.SetWindowPos(
                root, -1, 0, 0, 0, 0,                                # HWND_TOPMOST
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        except Exception:
            pass

    # -------------------------------------------------------- 尺寸与摆放

    def _panel_height(self) -> int:
        return (self.pad_y * 2 +
                sum(self.sep_h if r["kind"] == "sep" else self.row_h
                    for r in self.rows))

    def _measure_width(self) -> int:
        widest = 0
        for row in self.rows:
            if row["kind"] == "sep":
                continue
            w = self.pad_x * 2 + self.indent + self.font_main.measure(row.get("label", ""))
            w += int(round(24 * self.s))           # 指示点 / 箭头的位置
            if row.get("hint"):
                w += self.font_small.measure(row["hint"]) + int(round(14 * self.s))
            if row.get("sub"):
                w += int(round(14 * self.s))
            widest = max(widest, w)
        return max(int(round(158 * self.s)), widest)

    def _place(self, x: int, y: int) -> None:
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = int(clamp(x, 0, max(0, sw - self.width)))
        y = int(clamp(y, 0, max(0, sh - self.height)))
        self.x, self.y = x, y
        self.win.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def contains(self, sx: int, sy: int) -> bool:
        return (self.x <= sx < self.x + self.width and
                self.y <= sy < self.y + self.height)

    def _relayout(self) -> None:
        """换页之后重新量尺寸，左上角保持不动。"""
        self.width = self._measure_width()
        self.height = self._panel_height()
        try:
            self.canvas.configure(width=self.width, height=self.height)
        except Exception:
            pass
        self._place(self.x, self.y)
        self._force_topmost()

    def _push_page(self, label: str, rows: list) -> None:
        """钻进子页：同一扇窗换内容，比再开一个窗口稳得多
        （第二个窗口会被别的置顶窗口盖住、点击也容易被 grab 绕过去）。"""
        back = {"kind": "back", "label": f"← {label}"}
        self.stack.append([back] + list(rows))
        self.hot = -1
        self._relayout()
        self._draw()

    def _pop_page(self) -> None:
        if len(self.stack) > 1:
            self.stack.pop()
            self.hot = -1
            self._relayout()
            self._draw()

    # -------------------------------------------------------- 绘制

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        r = max(0.0, min(float(r), (x2 - x1) / 2.0, (y2 - y1) / 2.0))
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
               x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
               x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def _draw(self) -> None:
        c = self.canvas
        c.delete("all")
        s = self.s
        self._round_rect(1, 1, self.width - 1, self.height - 1, 8 * s,
                         fill=MENU_BG, outline=MENU_EDGE, width=max(1, int(round(1.4 * s))))
        y = self.pad_y
        for i, row in enumerate(self.rows):
            kind = row["kind"]
            if kind == "sep":
                ly = y + self.sep_h // 2
                c.create_line(self.pad_x, ly, self.width - self.pad_x, ly, fill=MENU_SEP)
                y += self.sep_h
                continue
            y0, y1 = y, y + self.row_h
            cy = (y0 + y1) // 2
            clickable = kind in ("cmd", "radio", "check", "sub")
            hot = clickable and i == self.hot
            if hot:
                self._round_rect(self.pad_x - 4 * s, y0 + 1,
                                 self.width - self.pad_x + 4 * s, y1 - 1,
                                 5 * s, fill=MENU_HOT, outline="")
            fg = "#ffffff" if hot else (DIM if kind == "title" else TEXT)
            tx = self.pad_x + self.indent
            if kind == "radio":
                rr = max(3, int(round(4 * s)))
                if row.get("checked"):
                    c.create_oval(tx - rr, cy - rr, tx + rr, cy + rr,
                                  fill=ACCENT, outline="")
                else:
                    c.create_oval(tx - rr, cy - rr, tx + rr, cy + rr, outline=MENU_EDGE,
                                  width=max(1, int(round(1.3 * s))))
                tx += int(round(17 * s))
            elif kind == "check":
                if row.get("checked"):
                    c.create_line(tx - 4 * s, cy + 1 * s, tx - 1 * s, cy + 4 * s,
                                  tx + 5 * s, cy - 4 * s, fill=("#ffffff" if hot else GOOD),
                                  width=max(1, int(round(2 * s))),
                                  capstyle="round", joinstyle="round")
                tx += int(round(17 * s))
            c.create_text(tx, cy, text=row.get("label", ""), anchor="w", fill=fg,
                          font=self.font_small if kind == "title" else self.font_main)
            if row.get("hint"):
                c.create_text(self.width - self.pad_x - (14 * s if row.get("sub") else 0),
                              cy, text=row["hint"], anchor="e", fill=DIM,
                              font=self.font_small)
            if row.get("sub"):
                c.create_text(self.width - self.pad_x, cy, text="▸", anchor="e",
                              fill=fg, font=self.font_main)
            y += self.row_h

    # -------------------------------------------------------- 交互

    def _row_at(self, local_y: int):
        y = self.pad_y
        for i, row in enumerate(self.rows):
            h = self.sep_h if row["kind"] == "sep" else self.row_h
            if y <= local_y < y + h:
                return i
            y += h
        return -1

    def _clickable(self, idx: int) -> bool:
        return 0 <= idx < len(self.rows) and self.rows[idx]["kind"] in (
            "cmd", "radio", "check", "sub", "back")

    def _on_motion(self, event) -> None:
        idx = self._row_at(event.y)
        if not self._clickable(idx):
            idx = -1
        if idx != self.hot:
            self.hot = idx
            self._draw()

    def _on_click(self, event) -> None:
        self._click_at(self.x + event.x, self.y + event.y)

    def _click_at(self, sx: int, sy: int) -> None:
        if time.time() - self.opened_at < 0.15:    # 开菜单那一下的余波，忽略
            return
        idx = self._row_at(sy - self.y)
        if not self._clickable(idx):
            self.close()                           # 点到面板外（比如桌宠身上）：收掉
            return
        row = self.rows[idx]
        if row["kind"] == "back":
            self._pop_page()
            return
        if row.get("sub"):
            self._push_page(row.get("label", ""), row["sub"])
            return
        action = row.get("action")
        self.close()                               # 先收菜单，再执行，免得回调里又开
        if action is not None:
            try:
                action()
            except Exception as exc:               # 菜单里出问题也不能把桌宠带崩
                warn(f"[warn] 菜单命令执行失败：{exc}")

    # -------------------------------------------------------- 关闭

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
        if self.pet._menu_panel is self:
            self.pet._menu_panel = None

    def _on_focus_out(self, _event) -> None:
        """焦点跑到别的程序去了（比如用户去点浏览器）就收掉菜单。"""
        if time.time() - self.opened_at < 0.35:
            return
        try:
            focused = self.win.focus_get()
        except Exception:
            focused = None
        if focused is not None:
            try:
                if focused.winfo_toplevel() is self.win:
                    return
            except Exception:
                pass
        self.close()


# ------------------------------------------------------------------ 桌宠


class BalancePet:
    """无边框 / 真透明 / 置顶的小窗口：上面一个气泡，下面一张立绘。"""

    def __init__(self, cfg: dict, demo: bool = False) -> None:
        import tkinter as tk

        self.tk = tk
        self.cfg = normalize_config(cfg)
        self.demo = bool(demo)
        self.key = "" if self.demo else resolve_key(self.cfg)
        self.queue: "queue.Queue[tuple]" = queue.Queue()

        # ---- 运行状态 ----
        self.state = "loading"        # loading | ok | low | empty | error | nokey
        self.headline = "正在看看饭钱…"
        self.detail = "马上就好"
        self.balance = None           # 上次成功的余额
        self.last_ok = 0.0
        self.next_at = 0.0            # 下次自动刷新的时间戳（0 = 暂停）
        self.busy = False
        self.tick = 0
        self.hover = False
        self.dragging = False
        self.moved = False
        self._swallow_click = False   # 菜单开着时那一下点击只用来收菜单
        self._mouse_down_seen = False # 轮询鼠标按键用（收菜单）
        self.press_from = (0, 0)
        self.win_from = (0, 0)
        self.cur_pos = None           # 拖动过程中自己算的位置（winfo_x 有延迟）
        self.click_at = 0.0           # 最近一次点击（画涟漪用）
        self.toast = ""               # 临时飘字
        self.toast_until = 0.0
        self._menu_panel = None       # 自绘右键菜单（可能带子面板）

        # ---- 窗口 ----
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} · {APP_SUB}")
        self.root.overrideredirect(True)
        try:
            self.root.attributes("-topmost", bool(self.cfg["always_on_top"]))
        except tk.TclError:
            pass
        try:
            self.root.wm_attributes("-transparentcolor", KEY_COLOR)
        except tk.TclError:
            pass
        self._apply_opacity(self.cfg["opacity"], save=False)   # 开机就是设定的透明度
        self._set_window_icon()

        # ---- 尺寸与缩放 ----
        self.dpi = self._detect_dpi()             # 屏幕缩放（1.0 = 100%）
        self._compute_layout()

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height,
                                bg=KEY_COLOR, highlightthickness=0, bd=0)
        self.canvas.pack()

        self._place_window()
        self._bind_events()
        try:
            self.root.focus_force()               # 让 Esc 立刻可用
        except tk.TclError:
            pass

        # ---- 开跑 ----
        if self.demo:
            self._demo_tick()
        else:
            self.refresh(reason="start")          # 没密钥时 refresh() 会自己弹输入框
        self._pump()

    # -------------------------------------------------------- 尺寸与布局

    def _px(self, value: float) -> int:
        return int(round(value * self.scale))

    def _fpx(self, pt: float, scale: float | None = None) -> int:
        """字号换算成像素（Tk 里负数字号就是像素）。"""
        s = self.scale if scale is None else scale
        return max(7, int(round(pt * s * 96.0 / 72.0)))

    def _f(self, pt: float, bold: bool = False, scale: float | None = None):
        """字号跟着「大小」一起缩，否则桌宠调小之后气泡会被字撑破。"""
        px = self._fpx(pt, scale)
        return (FONT_UI, -px, "bold") if bold else (FONT_UI, -px)

    def _detect_dpi(self) -> float:
        try:
            dpi = float(self.root.winfo_fpixels("1i"))
        except Exception:
            return 1.0
        if dpi <= 0:
            return 1.0
        return clamp(dpi / 96.0, 0.75, 3.0)

    def _target_scale(self) -> float:
        """想要的倍数 = 屏幕缩放 × 用户选的大小。"""
        want = self.dpi * to_float(self.cfg.get("size_scale"), 1.0)
        return clamp(want, 0.5, 3.0)

    def _compute_layout(self) -> None:
        """按当前大小算出窗口/气泡/立绘的所有尺寸与坐标。"""
        target = self._target_scale()
        self.image, self.pet_file = self._load_pet_image(target)
        if self.image is not None:
            # 素材是整数倍生成的，以实际加载到的素材为准，字号/留白才不会跟图对不上
            self.scale = round(self.image.width() / float(BASE_PET_W), 4)
            self.pet_w = int(self.image.width())
            self.pet_h = int(self.image.height())
        else:                                     # 素材丢了也不至于开不了窗
            self.scale = target
            self.pet_w = max(80, int(BASE_PET_W * target))
            self.pet_h = int(self.pet_w * 1.18)

        self.pad = self._px(BASE_PAD)
        self.bubble_w = self._px(BASE_BUBBLE_W)
        self.bubble_h = self._px(BASE_BUBBLE_H)
        self.tail = self._px(BASE_TAIL)
        self.bottom = self._px(BASE_BOTTOM)

        self.width = max(self.bubble_w, self.pet_w) + self.pad * 2
        self.bubble_x0 = (self.width - self.bubble_w) // 2
        self.bubble_y0 = self._px(6)
        self.height = self.bubble_y0 + self.bubble_h + self.tail + self.pet_h + self.bottom
        self.pet_x = (self.width - self.pet_w) // 2
        self.pet_y = self.bubble_y0 + self.bubble_h + self.tail

    def _set_window_icon(self) -> None:
        try:
            if ICON_FILE.exists():
                self.root.iconbitmap(default=str(ICON_FILE))
        except Exception:
            pass

    def _load_pet_image(self, target: float):
        """挑最接近 target 倍数的立绘；一张都没有就返回 None（走占位画法）。"""
        candidates = []
        for factor, name in PET_ASSETS:
            path = ASSET_DIR / name
            if path.exists():
                candidates.append((abs(math.log(factor / target)), path))
        if not candidates and PET_IMAGE.exists():
            candidates.append((0.0, PET_IMAGE))
        candidates.sort(key=lambda item: item[0])
        for _delta, path in candidates:
            try:
                img = self.tk.PhotoImage(file=str(path))
                if img.width() > 1:
                    return img, path.name
            except Exception as exc:
                warn(f"[warn] 立绘 {path.name} 加载失败：{exc}")
        warn("[warn] 没找到可用立绘，改用内置占位形象")
        return None, ""

    def _apply_geometry(self, x: int, y: int) -> None:
        """把窗口摆到 (x, y)，并保证整只（或至少顶部气泡）留在屏幕里。

        桌宠调到很大时窗口可能比屏幕还高，那就贴顶显示，
        否则窗口会被推到屏幕外，只剩一条边露出来。
        """
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = int(clamp(x, 0, max(0, sw - self.width)))
        y = int(clamp(y, 0, max(0, sh - self.height)))
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def _place_window(self) -> None:
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        pos = self.cfg.get("pos")
        if pos:
            x, y = int(pos[0]), int(pos[1])
        else:                                     # 默认落在右下角
            x, y = sw - self.width - self._px(40), sh - self.height - self._px(80)
        self._apply_geometry(x, y)

    def _bind_events(self) -> None:
        """鼠标事件只绑在 canvas 上。

        canvas 铺满整个窗口，而 Tk 的 bindtags 是「控件 -> 类 -> 顶层窗口 -> all」，
        给 root 也绑一份的话，同一次点击会被处理两遍：右键会连开两次菜单
        （第二次立刻把第一次关掉，看起来就是「点了没反应」），
        单击也会连发两次刷新请求。这个坑踩过一次，别再踩。
        """
        c = self.canvas
        c.bind("<Button-1>", self._on_press)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<Button-3>", self._on_menu)
        c.bind("<Enter>", self._on_enter)
        c.bind("<Leave>", self._on_leave)
        self.root.bind("<Escape>", lambda _e: self.quit())
        self.root.bind("<Double-Button-1>", lambda _e: self.refresh(reason="manual"))
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

    # -------------------------------------------------------- 鼠标交互

    def _on_press(self, event) -> None:
        # 菜单开着的时候，点桌宠只收菜单，不做别的（和系统菜单一样）
        if self._menu_is_open():
            self._close_menu()
            self._swallow_click = True
            self.dragging = False
            return
        self.press_from = (event.x_root, event.y_root)
        self.win_from = (self.root.winfo_x(), self.root.winfo_y())
        self.cur_pos = None
        self.moved = False
        self.dragging = True

    def _on_drag(self, event) -> None:
        if not self.dragging or self._swallow_click:
            return
        dx = event.x_root - self.press_from[0]
        dy = event.y_root - self.press_from[1]
        if abs(dx) > 4 or abs(dy) > 4:
            self.moved = True
        # 自己算目标位置：winfo_x() 要等 Windows 回 Configure 事件才更新，
        # 拖完立刻松手的话读到的还是旧坐标。
        self.cur_pos = (self.win_from[0] + dx, self.win_from[1] + dy)
        self.root.geometry(f"+{self.cur_pos[0]}+{self.cur_pos[1]}")

    def _current_pos(self) -> list:
        """尽量拿到窗口的真实位置（先让 Tk 把待处理的几何变更落下来）。"""
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        return [self.root.winfo_x(), self.root.winfo_y()]

    def _on_release(self, _event) -> None:
        if self._swallow_click:                    # 这一下只是用来收菜单的
            self._swallow_click = False
            self.dragging = False
            return
        self.dragging = False
        if self.moved:                            # 拖过 = 挪窝，顺手记住位置
            self.cfg["pos"] = list(self.cur_pos) if self.cur_pos else self._current_pos()
            self.cur_pos = None
            save_config(self.cfg)
            return
        self.click_at = time.time()
        self.refresh(reason="manual")             # 单击桌宠 = 立刻刷新

    def _on_menu(self, event) -> None:
        # 万一同一次右键被投递了两遍，0.3 秒内只认第一下（否则会把刚开的菜单关掉）
        now = time.time()
        if now - getattr(self, "_menu_toggle_at", 0.0) < 0.3:
            return
        self._menu_toggle_at = now
        # 菜单已经开着，就只收掉（右键当开关用）
        if self._menu_is_open():
            self._close_menu()
            return
        self._open_menu(event.x_root, event.y_root)

    def _on_enter(self, _event) -> None:
        self.hover = True

    def _on_leave(self, _event) -> None:
        self.hover = False

    # -------------------------------------------------------- 画图

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        r = max(0.0, min(float(r), (x2 - x1) / 2.0, (y2 - y1) / 2.0))
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def _accent(self) -> str:
        return {
            "ok": GOOD,
            "low": WARN,
            "empty": BAD,
            "error": BAD,
            "nokey": ACCENT,
            "loading": ACCENT,
        }.get(self.state, ACCENT)

    def _draw(self) -> None:
        c = self.canvas
        c.delete("all")
        self._draw_bubble()
        self._draw_pet()

    def _draw_bubble(self) -> None:
        c = self.canvas
        accent = self._accent()
        x0, y0 = self.bubble_x0, self.bubble_y0
        x1, y1 = x0 + self.bubble_w, y0 + self.bubble_h

        # 气泡主体 + 指向立绘的小尾巴
        self._round_rect(x0, y0, x1, y1, self._px(14),
                         fill=PANEL, outline=accent, width=max(1, self._px(2)))
        cx = self.width // 2
        c.create_polygon(cx - self._px(11), y1 - 2, cx + self._px(11), y1 - 2,
                         cx, y1 + self.tail - 2, fill=PANEL, outline=accent,
                         width=max(1, self._px(2)))

        inner_x = x0 + self._px(13)

        # 标题 + 状态灯（有飘字时，标题让位给飘字，免得飘到窗口外面被裁掉）
        toast_on = bool(self.toast) and time.time() < self.toast_until
        if toast_on:
            c.create_text((x0 + x1) // 2 - self._px(6), y0 + self._px(17),
                          text=self.toast, fill=GOLD, font=self._f(9, bold=True))
        else:
            c.create_text(inner_x, y0 + self._px(17), text=f"{APP_NAME} · {APP_SUB}",
                          anchor="w", fill=DIM, font=self._f(9))
        dot_r = self._px(5)
        dot_x = x1 - self._px(15)
        dot_y = y0 + self._px(17)
        if self.busy:                              # 刷新中转圈
            r = dot_r + self._px(4) + self._px(2) * math.sin(self.tick / 3.0)
            c.create_arc(dot_x - r, dot_y - r, dot_x + r, dot_y + r,
                         start=(self.tick * 14) % 360, extent=250, style="arc",
                         outline=ACCENT, width=max(1, self._px(2)))
        c.create_oval(dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r,
                      fill=accent, outline="")

        # 主数字 / 状态语
        head = self.headline
        size = 19 if len(head) <= 12 else (15 if len(head) <= 18 else 12)
        color = accent if self.state in ("low", "empty", "error", "nokey") else TEXT
        c.create_text(inner_x, y0 + self._px(47), text=head, anchor="w",
                      fill=color, font=self._f(size, bold=True))

        # 金额构成 / 错误原因
        c.create_text(inner_x, y0 + self._px(70), text=self.detail, anchor="w",
                      fill=DIM, font=self._f(8))

        # 倒计时 / 操作提示
        c.create_text(inner_x, y0 + self._px(86), text=self._footer_text(),
                      anchor="w", fill=DIM, font=self._f(8))

        # 刷新进度条（离气泡底边留点缝隙，免得跟描边糊成一条）
        bx0, bx1 = inner_x, x1 - self._px(13)
        by0 = y1 - self._px(12)
        by1 = y1 - self._px(8)
        self._round_rect(bx0, by0, bx1, by1, (by1 - by0) / 2.0, fill=TRACK, outline="")
        frac = self._progress()
        if frac > 0.02:
            self._round_rect(bx0, by0, bx0 + (bx1 - bx0) * frac, by1,
                             (by1 - by0) / 2.0, fill=accent, outline="")

    def _footer_text(self) -> str:
        if self.busy:
            return "正在刷新…"
        if self.demo:
            self._demo_tick()
            return f"演示模式 · {clock_text()} · 假数据，不联网"
        if self.state in ("ok", "low", "empty"):
            if self.next_at and self.cfg["interval_sec"]:
                left = countdown_text(self.next_at - time.time())
                return f"{clock_text(self.last_ok)} 更新 · 剩 {left} 自动刷新"
            return f"{clock_text(self.last_ok)} 更新 · 自动刷新已暂停"
        return "单击我立刻刷新 · 右键看菜单"

    def _progress(self) -> float:
        iv = int(self.cfg.get("interval_sec") or 0)
        if not iv or not self.next_at:
            return 0.0
        return clamp((self.next_at - time.time()) / iv, 0.0, 1.0)

    def _draw_pet(self) -> None:
        c = self.canvas
        bob = math.sin(self.tick / 16.0) * self._px(3)
        x, y = self.pet_x, self.pet_y + bob

        # 单击涟漪
        age = time.time() - self.click_at
        if age < 0.45:
            grow = self._px(10) + age * self._px(70)
            cxx, cyy = x + self.pet_w // 2, y + self.pet_h // 2
            c.create_oval(cxx - grow, cyy - grow, cxx + grow, cyy + grow,
                          outline=ACCENT, width=max(1, self._px(2)))

        # 悬停描边：告诉用户「这里可以点」
        if self.hover and not self.busy:
            m = self._px(3)
            self._round_rect(x + m, y + m, x + self.pet_w - m, y + self.pet_h - m,
                             self._px(12), fill="", outline=ACCENT,
                             width=max(1, self._px(2)))

        if self.image is not None:
            c.create_image(x, y, image=self.image, anchor="nw")
        else:
            self._draw_placeholder(x, y)

        # 刷新中：立绘右上角转个圈
        if self.busy:
            r = self._px(15) + self._px(5) * math.sin(self.tick / 4.0)
            ox = x + self.pet_w - self._px(20)
            oy = y + self._px(24)
            c.create_arc(ox - r, oy - r, ox + r, oy + r,
                         start=(self.tick * 12) % 360, extent=260, style="arc",
                         outline=ACCENT, width=max(2, self._px(3)))

    def _draw_placeholder(self, x: int, y: int) -> None:
        """立绘缺失时的兜底：一只端着碗的小家伙。"""
        c = self.canvas
        cx = x + self.pet_w // 2
        cy = y + int(self.pet_h * 0.45)
        r = min(self.pet_w, self.pet_h) // 3
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#f3f6fc",
                      outline="#2b3348", width=2)
        for dx in (-r // 2, r // 2):
            c.create_oval(cx + dx - r // 6, cy - r // 3, cx + dx + r // 6, cy - r // 6,
                          fill="#ffffff", outline="#2b3348", width=2)
            c.create_oval(cx + dx - r // 16, cy - r // 4, cx + dx + r // 8, cy - r // 8,
                          fill="#1b2338", outline="")
        c.create_arc(cx - r // 2, cy + r // 6, cx + r // 2, cy + r * 0.9,
                     start=0, extent=180, style="pieslice", fill="#dfe7f5",
                     outline="#2b3348", width=2)
        c.create_text(cx, y + self.pet_h - self._px(10),
                      text="（立绘缺失，跑一下 build_assets.py）", fill=DIM,
                      font=self._f(8))

    # -------------------------------------------------------- 主循环

    def _pump(self) -> None:
        """唯一的定时器：收后台结果、到点自动刷新、重画一帧。"""
        self._drain_results()
        self._maybe_auto_refresh()
        self._poll_menu_dismiss()
        self._draw()
        self.tick += 1
        try:
            self.root.after(50, self._pump)
        except Exception:
            pass

    def _drain_results(self) -> None:
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                return
            self.busy = False
            if kind == "ok":
                self._apply_balance(payload)
            else:
                self.state = "error"
                self.headline = "查不到饭钱了"
                self.detail = str(payload)[:22]
                self._schedule_next()

    def _maybe_auto_refresh(self) -> None:
        iv = int(self.cfg.get("interval_sec") or 0)
        if self.demo and self.next_at and time.time() >= self.next_at:
            self._demo_tick()
            return
        if not iv or not self.key or self.busy:
            return
        if self.next_at and time.time() >= self.next_at:
            self.refresh(reason="auto")

    def _demo_tick(self) -> None:
        """演示模式：编一个慢慢变少的余额，完全不联网。"""
        total = 88.88 if self.balance is None else max(0.0, self.balance["total"] - 13.33)
        self._apply_balance({
            "total": total,
            "granted": round(total * 0.1, 2),
            "topped_up": round(total * 0.9, 2),
            "currency": "CNY",
            "symbol": "¥",
            "available": True,
            "raw": {},
        })

    # -------------------------------------------------------- 状态与刷新

    def _set_state(self, state: str, headline: str, detail: str = "") -> None:
        self.state = state
        self.headline = headline
        self.detail = detail

    def _schedule_next(self) -> None:
        iv = int(self.cfg.get("interval_sec") or 0)
        self.next_at = (time.time() + iv) if iv else 0.0

    def refresh(self, reason: str = "auto") -> None:
        """发一次查询。reason: start / manual / auto。手动与自动都会重新计时。"""
        if self.busy:
            if reason == "manual":
                self._toast("正在刷新…")
            return
        if self.demo:
            self._demo_tick()
            self._toast("演示数据已刷新")
            return
        if not self.key:
            self.state = "nokey"
            self.headline = "还没给我饭钱"
            self.detail = ("配置文件读不出来，右键 →「设置密钥」" if CONFIG_ERROR
                           else "右键 →「设置密钥」，或双击这里")
            self.next_at = 0.0
            if reason in ("start", "manual"):
                self.root.after(200, self._ask_key_dialog)
            return

        self.busy = True
        if reason == "manual":
            self._toast("刷新中…")
        if self.balance is None:
            self.state = "loading"
            self.headline = "正在看看饭钱…"
            self.detail = "马上就好"
        threading.Thread(target=self._worker, args=(self.key, self.cfg["base_url"]),
                         daemon=True).start()

    def _worker(self, key: str, base_url: str) -> None:
        """后台线程查余额，结果丢进队列交给主线程处理。"""
        try:
            info = parse_balance(fetch_balance(key, base_url))
            self.queue.put(("ok", info))
        except RuntimeError as exc:
            self.queue.put(("err", str(exc)))
        except Exception as exc:                   # 兜底：桌宠绝不能崩
            self.queue.put(("err", f"{type(exc).__name__}: {exc}"))

    def _apply_balance(self, info: dict) -> None:
        before = self.balance["total"] if self.balance else None
        self.balance = info
        self.last_ok = time.time()
        self._schedule_next()

        sym = info["symbol"]
        total = info["total"]
        low = total < float(self.cfg.get("low_threshold", 10.0))

        if total <= 0:
            self._set_state("empty", "碗空了…", "该充值啦，她真的要饿死了")
        elif low:
            self._set_state("low", money(total, sym), "余额见底，快喂饭！")
        else:
            self._set_state("ok", money(total, sym),
                            f"赠金 {money(info['granted'], sym)} · "
                            f"充值 {money(info['topped_up'], sym)}")
        if not info["available"]:
            self.detail = "余额不足，接口已被停用"

        if before is not None and total > before + 0.0001:
            self._toast(f"+{money(total - before, sym)}")

    def _toast(self, text: str) -> None:
        self.toast = text
        self.toast_until = time.time() + 1.4

    # -------------------------------------------------------- 菜单

    def _menu_rows(self) -> list:
        """整份菜单的内容。自绘菜单只认这份数据，加项改项都只改这里。"""
        rows = [
            {"kind": "cmd", "label": "立刻刷新一次",
             "action": lambda: self.refresh(reason="manual")},
            {"kind": "sep"},
            {"kind": "title", "label": "自动刷新"},
        ]
        cur = int(self.cfg.get("interval_sec") or 0)
        for sec in INTERVAL_CHOICES + (0,):
            rows.append({"kind": "radio", "label": INTERVAL_LABEL[sec],
                         "checked": cur == sec,
                         "action": (lambda s=sec: self._set_interval(s))})

        rows.append({"kind": "sep"})
        size_rows = [{"kind": "radio", "label": SIZE_LABEL[f],
                      "checked": float(self.cfg.get("size_scale", 1.0)) == f,
                      "action": (lambda x=f: self._set_size(x))}
                     for f in SIZE_CHOICES]
        size_rows.append({"kind": "sep"})
        size_rows.append({"kind": "cmd", "label": "恢复默认大小",
                          "action": lambda: self._set_size(1.0)})
        rows.append({"kind": "sub", "label": "桌宠大小", "sub": size_rows,
                     "hint": f"{int(round(float(self.cfg.get('size_scale', 1.0)) * 100))}%"})

        op_rows = [{"kind": "radio", "label": OPACITY_LABEL[v],
                    "checked": abs(float(self.cfg.get("opacity", 1.0)) - v) < 1e-6,
                    "action": (lambda x=v: self._set_opacity(x))}
                   for v in OPACITY_CHOICES]
        op_rows.append({"kind": "sep"})
        op_rows.append({"kind": "cmd", "label": "恢复不透明",
                        "action": lambda: self._set_opacity(1.0)})
        rows.append({"kind": "sub", "label": "不透明度", "sub": op_rows,
                     "hint": f"{int(round(float(self.cfg.get('opacity', 1.0)) * 100))}%"})

        rows += [
            {"kind": "sep"},
            {"kind": "check", "label": "总在最前",
             "checked": bool(self.cfg.get("always_on_top", True)),
             "action": lambda: self._toggle_top(not self.cfg.get("always_on_top", True))},
            {"kind": "cmd", "label": "设置密钥…", "action": self._ask_key_dialog},
            {"kind": "cmd", "label": "打开充值页", "action": self._open_topup},
            {"kind": "cmd", "label": "打开配置文件", "action": self._open_config},
            {"kind": "sep"},
            {"kind": "cmd", "label": "隐藏 10 秒", "action": self._snooze},
            {"kind": "cmd", "label": "退出桌宠", "action": self.quit},
        ]
        return rows

    def _open_menu(self, x: int, y: int) -> None:
        self._close_menu()
        try:
            self._menu_panel = MenuPanel(self, self._menu_rows(), x, y)
        except Exception as exc:                   # 菜单开不出来也不能带崩桌宠
            self._menu_panel = None
            warn(f"[warn] 菜单打开失败：{exc}")

    def _close_menu(self) -> None:
        panel = getattr(self, "_menu_panel", None)
        if panel is not None:
            panel.close()
            self._menu_panel = None

    def _menu_is_open(self) -> bool:
        panel = getattr(self, "_menu_panel", None)
        if panel is None:
            return False
        try:
            if panel.win.winfo_exists():
                return True
        except Exception:
            pass
        self._menu_panel = None
        return False

    def _poll_menu_dismiss(self) -> None:
        """菜单开着时盯着鼠标：在面板外面按下左/右键就收菜单。

        不用 grab 的原因见 MenuPanel.__init__ 里的注释 —— 抓取会把点击吞掉。
        这里只做「按下」沿检测，面板里面的点击交给 canvas 自己的绑定。
        """
        panel = getattr(self, "_menu_panel", None)
        if panel is None or os.name != "nt":
            return
        try:
            import ctypes
            import ctypes.wintypes as wintypes

            u = ctypes.windll.user32
            down = bool(u.GetAsyncKeyState(0x01) & 0x8000) or \
                bool(u.GetAsyncKeyState(0x02) & 0x8000)
            if down and not self._mouse_down_seen:
                pt = wintypes.POINT()
                u.GetCursorPos(ctypes.byref(pt))
                if not panel.contains(pt.x, pt.y):
                    panel.close()
                    self._menu_panel = None
            self._mouse_down_seen = down
        except Exception:
            pass

    def _set_interval(self, sec: int) -> None:
        sec = int(sec)
        if sec != 0 and sec not in INTERVAL_CHOICES:
            sec = 300
        self.cfg["interval_sec"] = sec
        save_config(self.cfg)
        self._schedule_next()
        self._toast(human_interval(sec))

    # -------------------------------------------------------- 大小 / 透明度

    def _set_size(self, factor: float) -> None:
        """换一档大小：重新挑素材、重算布局，左上角位置保持不变。"""
        factor = min(SIZE_CHOICES, key=lambda c: abs(c - float(factor)))
        self.cfg["size_scale"] = factor
        save_config(self.cfg)

        x, y = self.root.winfo_x(), self.root.winfo_y()
        try:
            self.canvas.delete("all")              # 先把旧图的引用清掉再换素材
        except Exception:
            pass
        self._compute_layout()
        try:
            self.canvas.configure(width=self.width, height=self.height)
        except Exception:
            pass
        self._apply_geometry(x, y)
        self.click_at = 0.0                        # 别留下尺寸不对的涟漪

        # 屏幕缩放很大时，最上面几档会顶到素材上限，这里说清楚
        note = ""
        want = self._target_scale()
        if want > self.scale * 1.15:
            note = "（已是最大）"
        self._toast(f"大小：{SIZE_LABEL[factor]}{note}")

    def _apply_opacity(self, value: float, save: bool = True) -> None:
        value = round(clamp(to_float(value, 1.0), 0.3, 1.0), 3)
        self.cfg["opacity"] = value
        if save:
            save_config(self.cfg)
        try:
            self.root.attributes("-alpha", value)
        except Exception as exc:                   # 个别系统不支持就算了
            warn(f"[warn] 设置透明度失败：{exc}")

    def _set_opacity(self, value: float) -> None:
        self._apply_opacity(value)
        pct = f"{int(round(self.cfg['opacity'] * 100))}%"
        self._toast(f"不透明度：{pct}" if self.cfg["opacity"] < 1.0 else "已恢复不透明")

    def _toggle_top(self, on: bool) -> None:
        self.cfg["always_on_top"] = bool(on)
        save_config(self.cfg)
        try:
            self.root.attributes("-topmost", bool(on))
        except self.tk.TclError:
            pass

    def _open_topup(self) -> None:
        self._safe_open("https://platform.deepseek.com/top_up")

    def _open_config(self) -> None:
        try:
            if not CONFIG_PATH.exists():
                save_config(self.cfg)
            os.startfile(str(CONFIG_PATH))        # noqa: S606  Windows 专用
        except Exception as exc:
            warn(f"[warn] 打开配置文件失败：{exc}")

    def _safe_open(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _snooze(self) -> None:
        self.root.withdraw()
        self.root.after(10_000, self._wake)

    def _wake(self) -> None:
        try:
            self.root.deiconify()
            self.root.attributes("-topmost", bool(self.cfg["always_on_top"]))
        except Exception:
            pass

    # -------------------------------------------------------- 密钥对话框

    def _ask_key_dialog(self) -> None:
        tk = self.tk
        old = getattr(self, "_key_dialog", None)
        if old is not None:                        # 已经开着就别再开一个
            try:
                if old.winfo_exists():
                    old.lift()
                    old.focus_force()
                    return
            except Exception:
                pass
        try:
            win = tk.Toplevel(self.root)
        except Exception:
            return
        self._key_dialog = win
        win.title("设置 DeepSeek API 密钥")
        win.configure(bg=PANEL)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        # 对话框按屏幕缩放走，不跟桌宠大小走（桌宠调到很小也能看清）
        w, h = int(round(470 * self.dpi)), int(round(250 * self.dpi))
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{max(20, (sw - w) // 2)}+{max(20, (sh - h) // 3)}")

        tk.Label(win, text="把 DeepSeek 的饭钱钥匙填进来（sk- 开头）", bg=PANEL, fg=TEXT,
                 font=self._f(10, bold=True, scale=self.dpi)
                 ).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(win, text="密钥只写在本机的 config.json 里，除了 api.deepseek.com 不会发往别处。",
                 bg=PANEL, fg=DIM, font=self._f(8, scale=self.dpi)).pack(anchor="w", padx=18)

        entry = tk.Entry(win, width=54, show="•", bg="#0d1526", fg=TEXT,
                         insertbackground=TEXT, relief="flat",
                         font=(FONT_MONO, -max(8, int(round(10 * self.dpi * 96 / 72)))))
        entry.pack(padx=18, pady=(12, 0), ipady=6, fill="x")
        entry.insert(0, self.cfg.get("api_key", ""))
        entry.focus_set()

        bar = tk.Frame(win, bg=PANEL)
        bar.pack(fill="x", padx=18, pady=16)

        def submit() -> None:
            key = entry.get().strip()
            if not key:
                return
            self.cfg["api_key"] = key
            save_config(self.cfg)
            self.key = key
            win.destroy()
            self.refresh(reason="manual")

        btn_font = self._f(9, scale=self.dpi)
        tk.Button(bar, text="保存并刷新", command=submit, bg=ACCENT, fg="#ffffff",
                  relief="flat", font=btn_font, padx=16, pady=5).pack(side="right")
        tk.Button(bar, text="取消", command=win.destroy, bg="#2b3348", fg=TEXT,
                  relief="flat", font=btn_font, padx=16, pady=5).pack(side="right", padx=8)
        tk.Button(bar, text="去申请密钥", bg="#2b3348", fg=TEXT, relief="flat",
                  font=btn_font, padx=16, pady=5,
                  command=lambda: self._safe_open("https://platform.deepseek.com/api_keys")
                  ).pack(side="left")

        win.bind("<Return>", lambda _e: submit())
        win.bind("<Escape>", lambda _e: win.destroy())

    # -------------------------------------------------------- 生命周期

    def quit(self) -> None:
        try:
            self._close_menu()
        except Exception:
            pass
        try:
            self.cfg["pos"] = list(self.cur_pos) if self.cur_pos else self._current_pos()
            save_config(self.cfg)
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self) -> None:
        self.root.mainloop()


# ------------------------------------------------------------------ 崩溃处理


def log_crash() -> None:
    """写日志 + 弹窗：用 pythonw 启动时看不到控制台，只能弹窗。"""
    text = traceback.format_exc()
    try:
        ERROR_LOG.write_text(text, encoding="utf-8")
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        last = text.strip().splitlines()[-1] if text.strip() else ""
        messagebox.showerror(f"{APP_NAME} 启动失败",
                             "启动时出错，详情已写入 pet_error.log：\n\n" + last)
        root.destroy()
    except Exception:
        warn(text)


# ------------------------------------------------------------------ 自检


def do_check() -> int:
    ok = True
    print(f"{APP_NAME} · {APP_SUB} V{VERSION} 自检")
    print(f"Python  : {sys.version.split()[0]}  ({sys.executable})")
    print(f"目录    : {APP_DIR}")
    try:
        import tkinter

        print(f"tkinter : OK (Tk {tkinter.TkVersion})")
    except Exception as exc:
        ok = False
        print(f"tkinter : 不可用 -> {exc}")

    if PET_IMAGE.exists():
        print(f"立绘    : OK  {PET_IMAGE.name} ({PET_IMAGE.stat().st_size} 字节)")
        for _f, name in PET_ASSETS:
            p = ASSET_DIR / name
            print(f"          {'有' if p.exists() else '缺'}  {name}")
    else:
        print(f"立绘    : 缺失 -> {PET_IMAGE}（会退回内置占位形象）")
        ok = False

    cfg = load_config()
    print(f"配置    : {CONFIG_PATH}（{'存在' if CONFIG_PATH.exists() else '不存在，用默认值'}）")
    if CONFIG_ERROR:
        ok = False
        print(f"          [警告] {CONFIG_ERROR}")
    print(f"刷新    : {human_interval(int(cfg.get('interval_sec') or 0))}")
    print(f"大小    : {SIZE_LABEL.get(cfg['size_scale'], cfg['size_scale'])}"
          f"（配置值 {cfg['size_scale']}）")
    print(f"透明度  : {int(round(cfg['opacity'] * 100))}%")
    print(f"接口    : {cfg['base_url']}")

    key = resolve_key(cfg)
    if not key:
        print("密钥    : 未配置（启动后会弹窗让你填）")
        return 0 if ok else 1
    print(f"密钥    : {key[:8]}…{key[-4:]}（长度 {len(key)}）")
    try:
        info = parse_balance(fetch_balance(key, cfg["base_url"]))
        print(f"接口    : OK  余额 {money(info['total'], info['symbol'])}"
              f"（赠金 {info['granted']:.2f} / 充值 {info['topped_up']:.2f}，"
              f"可用={info['available']}）")
    except Exception as exc:
        ok = False
        print(f"接口    : 失败 -> {exc}")
    return 0 if ok else 1


# ------------------------------------------------------------------ 入口


def main(argv=None) -> int:
    init_console()
    ap = argparse.ArgumentParser(description=f"{APP_NAME} · {APP_SUB} V{VERSION}")
    ap.add_argument("--check", action="store_true", help="自检环境 / 立绘 / 配置 / 接口后退出")
    ap.add_argument("--pause", action="store_true", help="自检结束后等一次回车（给 bat 用）")
    ap.add_argument("--set-key", metavar="KEY", help="保存 API 密钥并验证连通性")
    ap.add_argument("--interval", type=int, metavar="SEC",
                    help="设置自动刷新间隔：60 / 300 / 600 秒，0 表示暂停")
    ap.add_argument("--size", type=float, metavar="PCT",
                    help="设置桌宠大小百分比：60 / 80 / 100 / 125 / 150 / 200 / 250")
    ap.add_argument("--opacity", type=float, metavar="PCT",
                    help="设置不透明度百分比：30 ~ 100")
    ap.add_argument("--demo", action="store_true", help="演示模式：用假数据看外观，不联网")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} V{VERSION}")
    args = ap.parse_args(argv)

    if args.check:
        code = do_check()
        if args.pause:
            try:
                input("\n按回车键关闭…")
            except EOFError:
                pass
        return code

    cfg = load_config()

    if args.set_key:
        cfg["api_key"] = args.set_key.strip()
        save_config(cfg)
        print(f"密钥已保存到 {CONFIG_PATH}")
        try:
            info = parse_balance(fetch_balance(cfg["api_key"], cfg["base_url"]))
            print(f"连通性验证通过，当前余额 {money(info['total'], info['symbol'])}")
        except Exception as exc:
            warn(f"警告：接口验证失败 -> {exc}")
        return 0

    if args.interval is not None:
        if args.interval not in INTERVAL_CHOICES and args.interval != 0:
            warn("间隔只支持 60 / 300 / 600 秒，或 0 表示暂停")
            return 2
        cfg["interval_sec"] = args.interval
        save_config(cfg)
        print("自动刷新间隔已设为 " + human_interval(args.interval))
        return 0

    if args.size is not None:
        pct = args.size / 100.0 if args.size > 5 else args.size      # 100 或 1.0 都认
        if not 30 <= pct * 100 <= 300:
            warn("大小只支持 30% ~ 300%")
            return 2
        factor = min(SIZE_CHOICES, key=lambda c: abs(c - pct))
        cfg["size_scale"] = factor
        save_config(cfg)
        print(f"桌宠大小已设为 {SIZE_LABEL[factor]}"
              + ("" if abs(factor - pct) < 1e-6 else f"（最接近 {pct * 100:.0f}% 的一档）"))
        return 0

    if args.opacity is not None:
        pct = args.opacity / 100.0 if args.opacity > 1.5 else args.opacity
        if not 0.3 <= pct <= 1.0:
            warn("不透明度只支持 30% ~ 100%")
            return 2
        cfg["opacity"] = round(pct, 3)
        save_config(cfg)
        print(f"不透明度已设为 {int(round(pct * 100))}%")
        return 0

    enable_dpi_awareness()
    try:
        pet = BalancePet(cfg, demo=args.demo)
    except Exception:
        log_crash()
        raise
    pet.run()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        log_crash()
        sys.exit(1)
