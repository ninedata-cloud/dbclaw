from pathlib import Path
import math
import textwrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "wechat"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1600, 900
FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def font(size, weight="regular"):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


F = {
    "hero": font(64, "bold"),
    "h1": font(48, "bold"),
    "h2": font(34, "bold"),
    "h3": font(26, "bold"),
    "body": font(24),
    "small": font(18),
    "tiny": font(15),
    "mono": font(22),
}


COLORS = {
    "bg": (12, 17, 28),
    "bg2": (16, 24, 39),
    "panel": (26, 35, 55),
    "panel2": (31, 42, 66),
    "line": (61, 82, 118),
    "blue": (47, 129, 247),
    "cyan": (57, 210, 192),
    "green": (63, 185, 80),
    "yellow": (210, 153, 34),
    "red": (248, 81, 73),
    "purple": (163, 113, 247),
    "text": (232, 238, 247),
    "muted": (151, 162, 181),
    "dim": (102, 115, 137),
    "white": (255, 255, 255),
}


def rgba(c, a=255):
    return (*c, a)


def gradient_bg(w=W, h=H, accent=(47, 129, 247)):
    img = Image.new("RGB", (w, h), COLORS["bg"])
    px = img.load()
    for y in range(h):
        for x in range(w):
            nx = x / w
            ny = y / h
            base = [12, 17, 28]
            glow1 = max(0, 1 - math.hypot(nx - 0.18, ny - 0.12) / 0.62)
            glow2 = max(0, 1 - math.hypot(nx - 0.86, ny - 0.72) / 0.78)
            for i in range(3):
                val = base[i] + int(accent[i] * glow1 * 0.18) + int((57, 210, 192)[i] * glow2 * 0.08)
                px[x, y] = tuple(min(255, max(0, v)) for v in (px[x, y] if False else [0, 0, 0]))
            px[x, y] = (
                min(255, base[0] + int(accent[0] * glow1 * 0.20) + int(57 * glow2 * 0.10)),
                min(255, base[1] + int(accent[1] * glow1 * 0.20) + int(210 * glow2 * 0.10)),
                min(255, base[2] + int(accent[2] * glow1 * 0.20) + int(192 * glow2 * 0.10)),
            )
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for x in range(-100, w + 200, 90):
        d.line((x, 0, x - 460, h), fill=(255, 255, 255, 10), width=1)
    for y in range(70, h, 80):
        d.line((0, y, w, y), fill=(255, 255, 255, 8), width=1)
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def shadowed_round(draw_img, box, radius=18, fill=(26, 35, 55, 255), outline=None, shadow=True, width=1):
    layer = Image.new("RGBA", draw_img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if shadow:
        sx0, sy0, sx1, sy1 = box
        d.rounded_rectangle((sx0, sy0 + 10, sx1, sy1 + 18), radius=radius, fill=(0, 0, 0, 90))
        layer = layer.filter(ImageFilter.GaussianBlur(18))
        draw_img.alpha_composite(layer)
        layer = Image.new("RGBA", draw_img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    draw_img.alpha_composite(layer)


def draw_text(draw, xy, text, fnt, fill=COLORS["text"], anchor=None, spacing=8):
    draw.multiline_text(xy, text, font=fnt, fill=fill, anchor=anchor, spacing=spacing)


def text_size(draw, text, fnt):
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def wrap_zh(text, max_chars):
    lines = []
    for part in text.split("\n"):
        if len(part) <= max_chars:
            lines.append(part)
        else:
            lines.extend(textwrap.wrap(part, width=max_chars, replace_whitespace=False, drop_whitespace=False))
    return "\n".join(lines)


def pill(draw, box, text, fill, txt=COLORS["text"], outline=None, fnt=None):
    fnt = fnt or F["small"]
    if isinstance(fill, tuple) and len(fill) == 4 and fill[3] < 255:
        alpha = fill[3] / 255
        base = COLORS["panel"]
        fill = tuple(int(fill[i] * alpha + base[i] * (1 - alpha)) for i in range(3))
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=fill, outline=outline, width=1)
    tw, th = text_size(draw, text, fnt)
    draw.text(((box[0] + box[2] - tw) / 2, (box[1] + box[3] - th) / 2 - 2), text, font=fnt, fill=txt)


def arrow(draw, start, end, fill, width=4):
    draw.line((start, end), fill=fill, width=width)
    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 14
    pts = [
        end,
        (end[0] - size * math.cos(ang - 0.45), end[1] - size * math.sin(ang - 0.45)),
        (end[0] - size * math.cos(ang + 0.45), end[1] - size * math.sin(ang + 0.45)),
    ]
    draw.polygon(pts, fill=fill)


def draw_logo_mark(img, x, y, s):
    d = ImageDraw.Draw(img)
    col1, col2 = COLORS["cyan"], COLORS["blue"]
    pts = [
        (x + s * 0.50, y),
        (x + s * 0.86, y + s * 0.14),
        (x + s * 0.86, y + s * 0.58),
        (x + s * 0.50, y + s * 0.96),
        (x + s * 0.14, y + s * 0.58),
        (x + s * 0.14, y + s * 0.14),
    ]
    d.line(pts + [pts[0]], fill=col2, width=max(3, s // 18), joint="curve")
    d.rounded_rectangle((x + s * 0.30, y + s * 0.32, x + s * 0.70, y + s * 0.66), radius=s // 16, outline=col1, width=max(3, s // 22))
    d.arc((x + s * 0.30, y + s * 0.20, x + s * 0.70, y + s * 0.44), 0, 180, fill=col1, width=max(3, s // 22))
    d.arc((x + s * 0.30, y + s * 0.54, x + s * 0.70, y + s * 0.78), 0, 180, fill=col1, width=max(3, s // 22))
    d.line((x + s * 0.10, y + s * 0.52, x + s * 0.30, y + s * 0.52), fill=COLORS["purple"], width=max(3, s // 24))
    d.line((x + s * 0.70, y + s * 0.52, x + s * 0.92, y + s * 0.52), fill=COLORS["purple"], width=max(3, s // 24))


def card(draw, img, box, title, body=None, accent=COLORS["blue"], icon=None):
    shadowed_round(img, box, radius=18, fill=rgba(COLORS["panel"], 230), outline=rgba(COLORS["line"], 180))
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((x0 + 20, y0 + 22, x0 + 64, y0 + 66), radius=12, fill=rgba(accent, 34), outline=rgba(accent, 180))
    if icon:
        d.text((x0 + 42, y0 + 42), icon, font=F["small"], anchor="mm", fill=accent)
    else:
        d.ellipse((x0 + 36, y0 + 38, x0 + 48, y0 + 50), fill=accent)
    d.text((x0 + 82, y0 + 22), title, font=F["h3"], fill=COLORS["text"])
    if body:
        d.multiline_text((x0 + 82, y0 + 62), wrap_zh(body, 16), font=F["small"], fill=COLORS["muted"], spacing=7)


def create_cover():
    img = gradient_bg(accent=(47, 129, 247))
    d = ImageDraw.Draw(img)
    draw_logo_mark(img, 86, 78, 118)
    d.text((230, 84), "DBClaw", font=F["h1"], fill=COLORS["text"])
    d.text((232, 145), "数据库智能卫士", font=F["body"], fill=COLORS["cyan"])
    d.text((86, 285), "AI 原生的\n开源数据库监控诊断系统", font=F["hero"], fill=COLORS["text"], spacing=14)
    d.text((90, 470), "让监控看见问题，让 AI 理解问题，让诊断沉淀为团队能力", font=F["body"], fill=COLORS["muted"])
    pill(d, (90, 555, 285, 605), "多数据库统一纳管", rgba(COLORS["blue"], 45), txt=COLORS["text"], outline=rgba(COLORS["blue"], 160))
    pill(d, (310, 555, 475, 605), "AI Agent 诊断", rgba(COLORS["purple"], 45), txt=COLORS["text"], outline=rgba(COLORS["purple"], 160))
    pill(d, (500, 555, 665, 605), "主动巡检告警", rgba(COLORS["green"], 45), txt=COLORS["text"], outline=rgba(COLORS["green"], 160))
    pill(d, (690, 555, 830, 605), "开源可扩展", rgba(COLORS["cyan"], 45), txt=COLORS["text"], outline=rgba(COLORS["cyan"], 160))

    # Product console mockup
    shadowed_round(img, (920, 110, 1515, 780), radius=24, fill=(14, 20, 33, 240), outline=rgba(COLORS["line"], 190))
    d.rounded_rectangle((920, 110, 1515, 168), radius=24, fill=(20, 28, 44, 255))
    for i, c in enumerate([(248, 81, 73), (210, 153, 34), (63, 185, 80)]):
        d.ellipse((948 + i * 26, 132, 962 + i * 26, 146), fill=c)
    d.text((1022, 130), "AI Diagnosis Workbench", font=F["tiny"], fill=COLORS["muted"])
    # Sidebar
    d.rounded_rectangle((945, 195, 1105, 742), radius=14, fill=(18, 26, 42, 255), outline=(55, 72, 104, 255))
    navs = ["资源大盘", "实例详情", "智能巡检", "告警管理", "技能管理"]
    for idx, n in enumerate(navs):
        y = 224 + idx * 62
        fill = (28, 53, 88, 255) if idx == 1 else (18, 26, 42, 0)
        if idx == 1:
            d.rounded_rectangle((960, y - 10, 1090, y + 34), radius=10, fill=fill)
        d.text((974, y), n, font=F["tiny"], fill=COLORS["text"] if idx == 1 else COLORS["muted"])
    # Metrics and chat
    for i, (label, value, col) in enumerate([
        ("连接数", "1 / 17", COLORS["cyan"]),
        ("QPS", "2691.6", COLORS["blue"]),
        ("缓存命中率", "72.3%", COLORS["green"]),
    ]):
        x = 1130 + (i % 2) * 178
        y = 205 + (i // 2) * 118
        d.rounded_rectangle((x, y, x + 160, y + 92), radius=14, fill=(31, 42, 66, 255), outline=(55, 72, 104, 255))
        d.text((x + 18, y + 17), label, font=F["tiny"], fill=COLORS["muted"])
        d.text((x + 18, y + 48), value, font=F["h3"], fill=COLORS["text"])
        d.rectangle((x, y, x + 5, y + 92), fill=col)
    d.rounded_rectangle((1130, 440, 1490, 735), radius=16, fill=(31, 42, 66, 255), outline=(55, 72, 104, 255))
    d.text((1155, 465), "AI 诊断计划", font=F["h3"], fill=COLORS["text"])
    lines = ["1. OS 层面：CPU / 内存 / I/O", "2. 数据库层面：连接 / SQL / 锁", "3. 关联分析：指标交叉定位", "4. 输出建议：处置路径"]
    for i, line in enumerate(lines):
        d.text((1158, 508 + i * 38), line, font=F["small"], fill=COLORS["muted"])
    for i, (skill, col) in enumerate([("get_os_metrics", COLORS["green"]), ("pg_get_db_status", COLORS["cyan"])]):
        y = 660 + i * 42
        d.rounded_rectangle((1155, y, 1470, y + 30), radius=8, fill=(21, 47, 58, 220), outline=rgba(col, 150))
        d.text((1174, y + 6), skill, font=F["tiny"], fill=COLORS["text"])
        d.text((1390, y + 6), "完成", font=F["tiny"], fill=col)
    img.save(OUT / "00-cover.png")


def create_architecture():
    img = gradient_bg(accent=(57, 210, 192))
    d = ImageDraw.Draw(img)
    d.text((80, 60), "DBClaw 产品架构", font=F["h1"], fill=COLORS["text"])
    d.text((82, 122), "AI 原生设计：从接入、采集、诊断到告警协同，形成数据库运维闭环", font=F["body"], fill=COLORS["muted"])
    layers = [
        ("用户入口", ["Web 控制台", "飞书 / 钉钉 / 企业微信机器人", "Webhook / 邮件通知"], COLORS["blue"]),
        ("智能运维中枢", ["FastAPI 服务", "AI Agent / 意图识别", "上下文构建 / 知识增强"], COLORS["purple"]),
        ("诊断与监控能力", ["技能系统", "指标采集", "自动巡检", "阈值 & AI 告警", "通知分发"], COLORS["cyan"]),
        ("连接与适配", ["DB Connector", "SSH 连接池", "云监控集成", "可编程适配器"], COLORS["green"]),
        ("基础资源", ["MySQL", "PostgreSQL", "Oracle", "SQL Server", "openGauss", "SAP HANA", "主机 OS"], COLORS["yellow"]),
    ]
    y = 190
    for idx, (title, items, accent) in enumerate(layers):
        x0, y0, x1, y1 = 95, y, 1505, y + 108
        shadowed_round(img, (x0, y0, x1, y1), radius=20, fill=rgba(COLORS["panel"], 228), outline=rgba(accent, 170), shadow=True)
        d.rectangle((x0, y0 + 22, x0 + 7, y1 - 22), fill=accent)
        d.text((130, y0 + 32), title, font=F["h3"], fill=COLORS["text"])
        item_x = 395
        for item in items:
            tw, _ = text_size(d, item, F["small"])
            pill(d, (item_x, y0 + 33, item_x + tw + 46, y0 + 78), item, rgba(accent, 34), txt=COLORS["text"], outline=rgba(accent, 140), fnt=F["small"])
            item_x += tw + 72
        if idx < len(layers) - 1:
            arrow(d, (800, y1 + 4), (800, y1 + 46), rgba(COLORS["line"], 210), width=3)
        y += 132
    d.text((1160, 815), "开源部署 | 私有化可控 | 技能可扩展", font=F["small"], fill=COLORS["muted"])
    img.save(OUT / "01-architecture.png")


def create_ai_flow():
    img = gradient_bg(accent=(163, 113, 247))
    d = ImageDraw.Draw(img)
    d.text((80, 62), "AI Agent 诊断流程", font=F["h1"], fill=COLORS["text"])
    d.text((82, 124), "AI 不只是回答问题，而是理解意图、调用工具、综合证据并输出可执行建议", font=F["body"], fill=COLORS["muted"])
    steps = [
        ("用户问题", "“这个实例为什么变慢了？”", COLORS["blue"]),
        ("意图识别", "诊断 / 查询 / 管理操作", COLORS["purple"]),
        ("上下文构建", "实例信息、历史指标、告警、知识库", COLORS["cyan"]),
        ("技能选择", "自动挑选数据库与 OS 诊断技能", COLORS["green"]),
        ("证据执行", "SQL / 指标 / 主机命令 / 文档检索", COLORS["yellow"]),
        ("AI 综合", "根因判断、影响评估、处置建议", COLORS["red"]),
    ]
    start_x, start_y = 95, 250
    box_w, box_h, gap = 220, 150, 38
    for i, (title, body, accent) in enumerate(steps):
        x = start_x + i * (box_w + gap)
        y = start_y if i % 2 == 0 else start_y + 180
        shadowed_round(img, (x, y, x + box_w, y + box_h), radius=20, fill=rgba(COLORS["panel"], 235), outline=rgba(accent, 190))
        d.ellipse((x + 22, y + 22, x + 62, y + 62), fill=rgba(accent, 80), outline=accent, width=2)
        d.text((x + 42, y + 29), str(i + 1), font=F["small"], fill=COLORS["text"], anchor="ma")
        d.text((x + 22, y + 76), title, font=F["h3"], fill=COLORS["text"])
        d.multiline_text((x + 22, y + 112), wrap_zh(body, 10), font=F["tiny"], fill=COLORS["muted"], spacing=4)
        if i < len(steps) - 1:
            nx = start_x + (i + 1) * (box_w + gap)
            ny = start_y if (i + 1) % 2 == 0 else start_y + 180
            arrow(d, (x + box_w + 5, y + box_h // 2), (nx - 8, ny + box_h // 2), rgba(COLORS["line"], 220), width=4)

    # Tool cards
    y = 660
    shadowed_round(img, (170, y, 1430, y + 120), radius=22, fill=rgba((18, 29, 46), 232), outline=rgba(COLORS["line"], 180))
    d.text((210, y + 28), "可调用技能示例", font=F["h3"], fill=COLORS["text"])
    x = 460
    for skill, col in [
        ("get_os_metrics", COLORS["green"]),
        ("pg_get_db_status", COLORS["cyan"]),
        ("analyze_top_sql", COLORS["blue"]),
        ("check_lock_waits", COLORS["yellow"]),
        ("read_document", COLORS["purple"]),
    ]:
        tw, _ = text_size(d, skill, F["tiny"])
        pill(d, (x, y + 35, x + tw + 38, y + 76), skill, rgba(col, 40), txt=COLORS["text"], outline=rgba(col, 150), fnt=F["tiny"])
        x += tw + 64
    img.save(OUT / "02-ai-diagnosis-flow.png")


def create_capability_matrix():
    img = gradient_bg(accent=(63, 185, 80))
    d = ImageDraw.Draw(img)
    d.text((80, 60), "一套系统覆盖数据库运维关键场景", font=F["h1"], fill=COLORS["text"])
    d.text((82, 122), "监控、巡检、告警、诊断、知识与集成能力围绕 AI Agent 统一编排", font=F["body"], fill=COLORS["muted"])
    cards = [
        ("多数据库纳管", "MySQL / PostgreSQL / Oracle / SQL Server / openGauss / SAP HANA", COLORS["blue"], "DB"),
        ("实时性能监控", "连接、QPS、缓存命中率、会话、Top SQL、主机资源指标", COLORS["cyan"], "M"),
        ("AI 智能诊断", "意图识别、上下文构建、技能调用、证据综合", COLORS["purple"], "AI"),
        ("自动巡检", "定时巡检、事件触发、规则检查、结构化报告", COLORS["green"], "I"),
        ("告警闭环", "阈值告警、AI 判警、去重聚合、自动恢复、通知分发", COLORS["red"], "A"),
        ("开放扩展", "YAML 技能、文档知识、云监控集成、可编程适配器", COLORS["yellow"], "X"),
    ]
    x0, y0 = 92, 215
    cw, ch = 455, 175
    for i, (title, body, accent, icon) in enumerate(cards):
        x = x0 + (i % 3) * (cw + 54)
        y = y0 + (i // 3) * (ch + 56)
        card(d, img, (x, y, x + cw, y + ch), title, body, accent, icon)
    # Supported DB bar
    shadowed_round(img, (92, 740, 1508, 820), radius=20, fill=rgba((18, 29, 46), 235), outline=rgba(COLORS["line"], 180))
    d.text((125, 764), "支持数据库", font=F["h3"], fill=COLORS["text"])
    x = 310
    for db, col in [
        ("MySQL", COLORS["blue"]),
        ("PostgreSQL", COLORS["cyan"]),
        ("Oracle", COLORS["red"]),
        ("SQL Server", COLORS["purple"]),
        ("openGauss", COLORS["green"]),
        ("SAP HANA", COLORS["yellow"]),
        ("TDSQL-C MySQL", COLORS["blue"]),
    ]:
        tw, _ = text_size(d, db, F["tiny"])
        pill(d, (x, 762, x + tw + 36, 802), db, rgba(col, 34), txt=COLORS["text"], outline=rgba(col, 135), fnt=F["tiny"])
        x += tw + 57
    img.save(OUT / "03-capability-matrix.png")


def fit_image(src, box_w, box_h):
    src_w, src_h = src.size
    scale = min(box_w / src_w, box_h / src_h)
    nw, nh = int(src_w * scale), int(src_h * scale)
    return src.resize((nw, nh), Image.LANCZOS)


def create_screenshot_frame(src_path, out_name, title, subtitle, accent):
    img = gradient_bg(accent=accent)
    d = ImageDraw.Draw(img)
    d.text((80, 54), title, font=F["h1"], fill=COLORS["text"])
    d.text((82, 116), subtitle, font=F["body"], fill=COLORS["muted"])
    frame = (80, 185, 1520, 835)
    shadowed_round(img, frame, radius=24, fill=(11, 15, 25, 255), outline=rgba(COLORS["line"], 185))
    d.rounded_rectangle((frame[0], frame[1], frame[2], frame[1] + 54), radius=24, fill=(22, 30, 46, 255))
    for i, c in enumerate([(248, 81, 73), (210, 153, 34), (63, 185, 80)]):
        d.ellipse((frame[0] + 24 + i * 28, frame[1] + 20, frame[0] + 39 + i * 28, frame[1] + 35), fill=c)
    d.text((frame[0] + 125, frame[1] + 17), "DBClaw Console", font=F["tiny"], fill=COLORS["muted"])
    src = Image.open(src_path).convert("RGB")
    thumb = fit_image(src, frame[2] - frame[0] - 36, frame[3] - frame[1] - 86)
    x = frame[0] + (frame[2] - frame[0] - thumb.size[0]) // 2
    y = frame[1] + 68
    mask = Image.new("L", thumb.size, 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, thumb.size[0], thumb.size[1]), radius=14, fill=255)
    img.paste(thumb, (x, y), mask)
    img.save(OUT / out_name)


def create_alert_screenshot():
    img = gradient_bg(accent=(248, 81, 73))
    d = ImageDraw.Draw(img)
    d.text((80, 54), "告警管理与通知闭环", font=F["h1"], fill=COLORS["text"])
    d.text((82, 116), "阈值告警、AI 判警、聚合去重、恢复状态和多渠道通知统一管理", font=F["body"], fill=COLORS["muted"])
    shadowed_round(img, (70, 180, 1530, 840), radius=26, fill=(12, 17, 28, 245), outline=rgba(COLORS["line"], 185))
    d.rounded_rectangle((70, 180, 1530, 235), radius=26, fill=(22, 30, 46, 255))
    d.text((104, 198), "告警管理", font=F["h3"], fill=COLORS["text"])
    pill(d, (1240, 192, 1360, 225), "活跃 12", rgba(COLORS["red"], 42), txt=COLORS["red"], outline=rgba(COLORS["red"], 150), fnt=F["tiny"])
    pill(d, (1376, 192, 1495, 225), "已恢复 46", rgba(COLORS["green"], 38), txt=COLORS["green"], outline=rgba(COLORS["green"], 140), fnt=F["tiny"])

    # Left list
    headers = ["级别", "告警标题", "对象", "状态", "首次触发", "通知"]
    xs = [105, 210, 620, 920, 1080, 1300]
    for x, h in zip(xs, headers):
        d.text((x, 270), h, font=F["tiny"], fill=COLORS["dim"])
    rows = [
        ("HIGH", "数据库连接数超过阈值", "mysql-prod-01", "活跃", "3 分钟前", "飞书 / 邮件"),
        ("AI", "QPS 突增且缓存命中率下降", "pg-order-02", "确认中", "8 分钟前", "钉钉"),
        ("WARN", "主机磁盘使用率接近上限", "db-host-07", "活跃", "16 分钟前", "企业微信"),
        ("INFO", "巡检发现慢 SQL 风险", "oracle-pay-03", "已恢复", "42 分钟前", "Webhook"),
    ]
    y = 315
    for i, row in enumerate(rows):
        d.rounded_rectangle((96, y - 14, 1504, y + 62), radius=14, fill=(24, 33, 52, 235), outline=(48, 64, 95, 255))
        sev, title, obj, status, time, notify = row
        col = COLORS["red"] if sev == "HIGH" else COLORS["purple"] if sev == "AI" else COLORS["yellow"] if sev == "WARN" else COLORS["blue"]
        pill(d, (105, y + 4, 175, y + 38), sev, rgba(col, 40), txt=col, outline=rgba(col, 135), fnt=F["tiny"])
        d.text((210, y + 4), title, font=F["small"], fill=COLORS["text"])
        d.text((620, y + 4), obj, font=F["small"], fill=COLORS["muted"])
        d.text((920, y + 4), status, font=F["small"], fill=COLORS["green"] if status == "已恢复" else COLORS["text"])
        d.text((1080, y + 4), time, font=F["small"], fill=COLORS["muted"])
        d.text((1300, y + 4), notify, font=F["small"], fill=COLORS["muted"])
        y += 92
    # Detail panel
    shadowed_round(img, (96, 705, 1504, 810), radius=18, fill=rgba((18, 29, 46), 235), outline=rgba(COLORS["blue"], 130), shadow=False)
    d.text((128, 728), "AI 诊断摘要", font=F["h3"], fill=COLORS["text"])
    d.text((330, 730), "连接数持续升高，Top SQL 中发现长事务未提交；建议先确认业务发布窗口，并终止异常会话。", font=F["small"], fill=COLORS["muted"])
    img.save(OUT / "06-alerts-screenshot.png")


def create_all():
    create_cover()
    create_architecture()
    create_ai_flow()
    create_capability_matrix()
    create_screenshot_frame(ROOT / "docs/img/db_monitor.jpg", "04-monitor-screenshot.png", "实例级性能监控", "数据库指标与主机资源同屏呈现，便于快速发现性能变化", COLORS["blue"])
    create_screenshot_frame(ROOT / "docs/img/db_ai_diagnosis.jpg", "05-ai-diagnosis-screenshot.png", "AI 对话诊断工作台", "围绕实例上下文自动调用诊断技能，输出分析计划、证据和建议", COLORS["purple"])
    create_alert_screenshot()


if __name__ == "__main__":
    create_all()
    print(f"Generated assets under {OUT}")
