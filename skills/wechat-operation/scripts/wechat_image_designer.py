# -*- coding: utf-8 -*-
"""
微信文章配图生成器（高级模板版 / 方案A）

特点：
- 不引入 Pillow 等重依赖
- 直接输出 SVG，再用 rsvg-convert 转 PNG
- 保持现有输出路径：output/generated_images/point_1.png ~ point_4.png
- 升级成更像公众号爆款知识卡片的视觉模板
"""

from __future__ import annotations

import html
import subprocess
from pathlib import Path
from typing import List, Dict

WIDTH = 1080
HEIGHT = 720
OUTPUT_DIR = Path(__file__).parent.parent / 'output' / 'generated_images'
FONT_FAMILY = "'Noto Sans CJK SC','Microsoft YaHei','PingFang SC',sans-serif"
BRAND = '财商读书会'

PALETTES = [
    {
        'bg1': '#0f172a', 'bg2': '#2563eb', 'bg3': '#60a5fa',
        'accent': '#93c5fd', 'accent2': '#dbeafe', 'text': '#f8fafc', 'muted': '#cbd5e1',
        'card': 'rgba(255,255,255,0.11)', 'line': 'rgba(255,255,255,0.18)', 'soft': 'rgba(147,197,253,0.12)'
    },
    {
        'bg1': '#1f1147', 'bg2': '#7c3aed', 'bg3': '#c084fc',
        'accent': '#e9d5ff', 'accent2': '#f5d0fe', 'text': '#ffffff', 'muted': '#eadcff',
        'card': 'rgba(255,255,255,0.10)', 'line': 'rgba(255,255,255,0.16)', 'soft': 'rgba(216,180,254,0.12)'
    },
    {
        'bg1': '#042f2e', 'bg2': '#0f766e', 'bg3': '#2dd4bf',
        'accent': '#99f6e4', 'accent2': '#ccfbf1', 'text': '#ecfeff', 'muted': '#cffafe',
        'card': 'rgba(255,255,255,0.10)', 'line': 'rgba(255,255,255,0.16)', 'soft': 'rgba(45,212,191,0.11)'
    },
    {
        'bg1': '#4a044e', 'bg2': '#db2777', 'bg3': '#f472b6',
        'accent': '#fbcfe8', 'accent2': '#fce7f3', 'text': '#fff1f2', 'muted': '#fbcfe8',
        'card': 'rgba(255,255,255,0.10)', 'line': 'rgba(255,255,255,0.16)', 'soft': 'rgba(244,114,182,0.11)'
    },
]


def _escape(text: str) -> str:
    return html.escape(text or '')


def _shorten(text: str, n: int) -> str:
    text = (text or '').strip()
    if len(text) <= n:
        return text
    return text[: max(0, n - 1)].rstrip('，。；：、 ') + '…'


def _wrap_text(text: str, limit: int, max_lines: int) -> List[str]:
    text = (text or '').strip()
    if not text:
        return []
    lines, buf = [], ''
    for ch in text:
        buf += ch
        if len(buf) >= limit:
            lines.append(buf)
            buf = ''
            if len(lines) >= max_lines:
                break
    if buf and len(lines) < max_lines:
        lines.append(buf)
    used = ''.join(lines)
    if len(used) < len(text) and lines:
        lines[-1] = lines[-1].rstrip('，。；：、 ') + '…'
    return lines[:max_lines]


def _extract_keywords(text: str, max_items: int = 3) -> List[str]:
    raw = (text or '').replace('，', ',').replace('、', ',')
    items = [x.strip() for x in raw.split(',') if x.strip()]
    cleaned = []
    for item in items:
        if item not in cleaned:
            cleaned.append(_shorten(item, 10))
        if len(cleaned) >= max_items:
            break
    return cleaned


def _build_title_svg(lines: List[str], x: int, y: int, palette: Dict[str, str]) -> str:
    out = []
    for i, line in enumerate(lines):
        out.append(
            f'<text x="{x}" y="{y + i * 76}" font-size="56" font-weight="900" fill="{palette["text"]}" letter-spacing="1.2">{_escape(line)}</text>'
        )
    return ''.join(out)


def _build_subtitle_svg(lines: List[str], x: int, y: int, palette: Dict[str, str]) -> str:
    out = []
    for i, line in enumerate(lines):
        out.append(
            f'<text x="{x}" y="{y + i * 42}" font-size="27" font-weight="500" fill="{palette["muted"]}">{_escape(line)}</text>'
        )
    return ''.join(out)


def _build_keyword_chips(chips: List[str], x: int, y: int, palette: Dict[str, str]) -> str:
    if not chips:
        return ''
    parts = []
    cx = x
    for chip in chips:
        w = max(88, 28 + len(chip) * 24)
        parts.append(f'<rect x="{cx}" y="{y}" width="{w}" height="42" rx="21" fill="{palette["soft"]}" stroke="{palette["line"]}"/>')
        parts.append(f'<text x="{cx + w/2}" y="{y + 28}" text-anchor="middle" font-size="21" font-weight="700" fill="{palette["accent2"]}">{_escape(chip)}</text>')
        cx += w + 12
    return ''.join(parts)


def _build_right_visual(index: int, palette: Dict[str, str]) -> str:
    num = f'0{index}'
    return f'''
    <g transform="translate(728,132)">
      <rect x="0" y="0" width="258" height="456" rx="34" fill="rgba(255,255,255,0.08)" stroke="{palette['line']}"/>
      <circle cx="190" cy="72" r="88" fill="url(#orb)" fill-opacity="0.95"/>
      <circle cx="190" cy="72" r="52" fill="rgba(255,255,255,0.15)"/>
      <rect x="30" y="148" width="198" height="112" rx="28" fill="rgba(255,255,255,0.07)" stroke="{palette['line']}"/>
      <text x="46" y="190" font-size="18" font-weight="700" fill="{palette['accent']}">BOOK INSIGHT</text>
      <text x="46" y="236" font-size="72" font-weight="900" fill="{palette['text']}" opacity="0.95">{num}</text>
      <rect x="30" y="294" width="198" height="18" rx="9" fill="rgba(255,255,255,0.08)"/>
      <rect x="30" y="332" width="164" height="18" rx="9" fill="rgba(255,255,255,0.06)"/>
      <rect x="30" y="370" width="142" height="18" rx="9" fill="rgba(255,255,255,0.05)"/>
      <rect x="30" y="412" width="110" height="34" rx="17" fill="{palette['soft']}" stroke="{palette['line']}"/>
      <text x="85" y="435" text-anchor="middle" font-size="18" font-weight="700" fill="{palette['accent2']}">核心拆解</text>
    </g>
    '''


def _build_svg(index: int, title: str, subtitle: str, tag: str, book_title: str, keywords: List[str], palette: Dict[str, str]) -> str:
    title_lines = _wrap_text(title, limit=14, max_lines=3)
    subtitle_lines = _wrap_text(subtitle, limit=23, max_lines=3)
    book_label = _shorten(f'《{book_title}》' if book_title else '经典好书拆解', 18)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{palette['bg1']}"/>
      <stop offset="55%" stop-color="{palette['bg2']}"/>
      <stop offset="100%" stop-color="{palette['bg3']}"/>
    </linearGradient>
    <radialGradient id="orb" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{palette['accent2']}" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="{palette['accent']}" stop-opacity="0.18"/>
    </radialGradient>
    <linearGradient id="shine" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.22"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0.02"/>
    </linearGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="46"/></filter>
  </defs>

  <rect width="100%" height="100%" rx="36" fill="url(#bg)"/>
  <circle cx="958" cy="88" r="176" fill="{palette['accent']}" fill-opacity="0.24" filter="url(#blur)"/>
  <circle cx="116" cy="652" r="174" fill="#ffffff" fill-opacity="0.08" filter="url(#blur)"/>
  <path d="M0,560 C250,470 360,730 640,620 C850,538 920,440 1080,486 L1080,720 L0,720 Z" fill="rgba(255,255,255,0.05)"/>

  <rect x="52" y="52" width="976" height="616" rx="32" fill="rgba(10,14,25,0.14)" stroke="rgba(255,255,255,0.18)"/>
  <rect x="52" y="52" width="976" height="616" rx="32" fill="url(#shine)" opacity="0.32"/>

  <rect x="90" y="92" width="166" height="44" rx="22" fill="rgba(255,255,255,0.10)" stroke="{palette['line']}"/>
  <text x="173" y="121" text-anchor="middle" font-size="21" font-weight="800" fill="{palette['accent2']}">{_escape(tag)}</text>

  <text x="92" y="176" font-size="22" font-weight="800" fill="{palette['accent']}">BOOK NOTES / POINT 0{index}</text>
  <text x="92" y="210" font-size="18" font-weight="700" fill="{palette['muted']}">{_escape(book_label)}</text>

  {_build_title_svg(title_lines, 92, 292, palette)}
  {_build_subtitle_svg(subtitle_lines, 92, 500, palette)}
  {_build_keyword_chips(keywords, 92, 610, palette)}

  {_build_right_visual(index, palette)}

  <line x1="92" y1="576" x2="660" y2="576" stroke="rgba(255,255,255,0.14)"/>
  <text x="92" y="654" font-size="22" font-weight="700" fill="{palette['muted']}">{BRAND} · 公众号高级模板图</text>
</svg>
'''


def render_image_cards(image_plan: List[Dict], article: Dict | None = None, style: str = 'editorial_cards') -> List[str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_paths: List[str] = []
    article = article or {}
    book = article.get('book_info', {})
    book_title = book.get('title', '')

    for idx, plan in enumerate(image_plan[:4], start=1):
        palette = PALETTES[(idx - 1) % len(PALETTES)]
        section = plan.get('section') or f'核心观点{idx}'
        title = plan.get('image_theme') or section
        subtitle = plan.get('image_keywords') or ''
        if ' / ' in title:
            _, right = title.split(' / ', 1)
            title = right.strip() or title
        subtitle = subtitle.replace('极简插画,', '').replace('书籍观点,', '').strip(' ,')
        subtitle = _shorten(subtitle, 58)
        keywords = _extract_keywords(subtitle, max_items=3)

        svg = _build_svg(
            idx,
            title=title,
            subtitle=subtitle,
            tag=section,
            book_title=book_title,
            keywords=keywords,
            palette=palette,
        )
        svg_path = OUTPUT_DIR / f'point_{idx}.svg'
        png_path = OUTPUT_DIR / f'point_{idx}.png'
        svg_path.write_text(svg, encoding='utf-8')

        subprocess.run([
            'rsvg-convert',
            '-w', str(WIDTH),
            '-h', str(HEIGHT),
            '-o', str(png_path),
            str(svg_path)
        ], check=True)
        output_paths.append(str(png_path))

    return output_paths


if __name__ == '__main__':
    demo_plan = [
        {'section': '核心观点1', 'image_theme': '富爸爸穷爸爸 / 资产与负债', 'image_keywords': '财富思维, 现金流, 长期主义'},
        {'section': '核心观点2', 'image_theme': '富爸爸穷爸爸 / 被动收入系统', 'image_keywords': '复利, 生意系统, 财务自由'},
        {'section': '核心观点3', 'image_theme': '富爸爸穷爸爸 / 多元思维模型', 'image_keywords': '框架, 洞察, 认知升级'},
        {'section': '核心观点4', 'image_theme': '富爸爸穷爸爸 / 从知道到做到', 'image_keywords': '行动, 习惯, 实践'},
    ]
    print(render_image_cards(demo_plan, article={'book_info': {'title': '富爸爸穷爸爸'}}))
