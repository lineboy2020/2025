# -*- coding: utf-8 -*-
"""
微信文章配图生成器（AI插画风 / 专业运营号版）

特点：
- 不依赖 Pillow 等重库
- 输出 SVG，再用 rsvg-convert 转 PNG
- 保持 point_1.png ~ point_4.png 输出不变
- 视觉方向模拟 AI 插画 + 专业公众号运营号审美
"""

from __future__ import annotations

import html
import subprocess
from pathlib import Path
from typing import List, Dict

WIDTH = 1080
HEIGHT = 720
OUTPUT_DIR = Path(__file__).parent.parent / 'output' / 'generated_images'
BRAND = '财商读书会'

PALETTES = [
    {
        'bg1': '#0f172a', 'bg2': '#1e3a8a', 'glow': '#7dd3fc', 'text': '#f8fafc',
        'muted': '#dbeafe', 'accent': '#cbd5e1', 'panel': 'rgba(255,255,255,0.10)', 'line': 'rgba(255,255,255,0.14)'
    },
    {
        'bg1': '#1f2937', 'bg2': '#6d28d9', 'glow': '#c084fc', 'text': '#ffffff',
        'muted': '#f3e8ff', 'accent': '#ddd6fe', 'panel': 'rgba(255,255,255,0.10)', 'line': 'rgba(255,255,255,0.14)'
    },
    {
        'bg1': '#022c22', 'bg2': '#0f766e', 'glow': '#5eead4', 'text': '#f0fdfa',
        'muted': '#ccfbf1', 'accent': '#99f6e4', 'panel': 'rgba(255,255,255,0.10)', 'line': 'rgba(255,255,255,0.14)'
    },
    {
        'bg1': '#3f0d24', 'bg2': '#be185d', 'glow': '#f9a8d4', 'text': '#fff1f2',
        'muted': '#fce7f3', 'accent': '#fbcfe8', 'panel': 'rgba(255,255,255,0.10)', 'line': 'rgba(255,255,255,0.14)'
    },
]


def _escape(text: str) -> str:
    return html.escape(text or '')


def _shorten(text: str, n: int) -> str:
    text = (text or '').strip()
    return text if len(text) <= n else text[: max(0, n - 1)].rstrip('，。；：、 ') + '…'


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
    if len(''.join(lines)) < len(text) and lines:
        lines[-1] = lines[-1].rstrip('，。；：、 ') + '…'
    return lines[:max_lines]


def _extract_keywords(text: str, max_items: int = 2) -> List[str]:
    raw = (text or '').replace('，', ',').replace('、', ',')
    items = [x.strip() for x in raw.split(',') if x.strip()]
    out = []
    for item in items:
        if item not in out:
            out.append(_shorten(item, 10))
        if len(out) >= max_items:
            break
    return out


def _title_svg(lines: List[str], x: int, y: int, color: str) -> str:
    return ''.join([
        f'<text x="{x}" y="{y + i * 72}" font-size="54" font-weight="900" fill="{color}" letter-spacing="1.1">{_escape(line)}</text>'
        for i, line in enumerate(lines)
    ])


def _subtitle_svg(lines: List[str], x: int, y: int, color: str) -> str:
    return ''.join([
        f'<text x="{x}" y="{y + i * 40}" font-size="26" font-weight="500" fill="{color}">{_escape(line)}</text>'
        for i, line in enumerate(lines)
    ])


def _chips_svg(chips: List[str], x: int, y: int, palette: Dict[str, str]) -> str:
    parts = []
    cursor = x
    for chip in chips:
        w = max(96, 30 + len(chip) * 24)
        parts.append(f'<rect x="{cursor}" y="{y}" width="{w}" height="40" rx="20" fill="rgba(255,255,255,0.12)" stroke="{palette["line"]}"/>')
        parts.append(f'<text x="{cursor + w/2}" y="{y + 26}" text-anchor="middle" font-size="20" font-weight="700" fill="{palette["accent"]}">{_escape(chip)}</text>')
        cursor += w + 12
    return ''.join(parts)


def _illustration_block(index: int, palette: Dict[str, str]) -> str:
    return f'''
    <g transform="translate(690,118)">
      <rect x="0" y="0" width="310" height="484" rx="34" fill="rgba(255,255,255,0.08)" stroke="{palette['line']}"/>
      <circle cx="214" cy="92" r="108" fill="{palette['glow']}" fill-opacity="0.18"/>
      <circle cx="214" cy="92" r="62" fill="rgba(255,255,255,0.08)"/>
      <path d="M70 318 C96 228, 212 192, 262 266 C284 299, 288 352, 250 390 C199 442, 101 430, 74 360 Z" fill="rgba(255,255,255,0.08)"/>
      <path d="M115 250 C136 204, 194 179, 235 214 C266 240, 270 286, 248 322 C220 369, 141 377, 108 334 C92 314, 94 282, 115 250 Z" fill="url(#artGlow)" fill-opacity="0.92"/>
      <circle cx="165" cy="278" r="16" fill="rgba(255,255,255,0.26)"/>
      <circle cx="205" cy="242" r="11" fill="rgba(255,255,255,0.18)"/>
      <circle cx="227" cy="300" r="9" fill="rgba(255,255,255,0.16)"/>
      <rect x="42" y="386" width="226" height="1.5" fill="{palette['line']}"/>
      <text x="42" y="430" font-size="18" font-weight="700" fill="{palette['accent']}">AI EDITORIAL ILLUSTRATION</text>
      <text x="42" y="478" font-size="72" font-weight="900" fill="{palette['text']}" opacity="0.92">0{index}</text>
      <text x="42" y="514" font-size="20" font-weight="600" fill="{palette['muted']}">审美升级 · 专业运营号风格</text>
    </g>
    '''


def _build_svg(index: int, title: str, subtitle: str, section: str, book_title: str, chips: List[str], palette: Dict[str, str]) -> str:
    title_lines = _wrap_text(title, 14, 3)
    subtitle_lines = _wrap_text(subtitle, 22, 3)
    book_label = _shorten(f'《{book_title}》' if book_title else '书籍解读', 16)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{palette['bg1']}"/>
      <stop offset="100%" stop-color="{palette['bg2']}"/>
    </linearGradient>
    <radialGradient id="artGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.72"/>
      <stop offset="100%" stop-color="{palette['glow']}" stop-opacity="0.28"/>
    </radialGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="52"/></filter>
  </defs>

  <rect width="100%" height="100%" rx="36" fill="url(#bg)"/>
  <circle cx="948" cy="96" r="188" fill="{palette['glow']}" fill-opacity="0.16" filter="url(#blur)"/>
  <circle cx="124" cy="640" r="188" fill="#ffffff" fill-opacity="0.06" filter="url(#blur)"/>
  <path d="M0 566 C194 480, 372 708, 620 612 C818 535, 940 450, 1080 506 L1080 720 L0 720 Z" fill="rgba(255,255,255,0.045)"/>

  <rect x="54" y="54" width="972" height="612" rx="34" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.14)"/>
  <rect x="88" y="90" width="156" height="42" rx="21" fill="rgba(255,255,255,0.10)" stroke="{palette['line']}"/>
  <text x="166" y="117" text-anchor="middle" font-size="20" font-weight="800" fill="{palette['accent']}">{_escape(section)}</text>

  <text x="88" y="176" font-size="20" font-weight="800" fill="{palette['accent']}">PREMIUM WECHAT VISUAL</text>
  <text x="88" y="210" font-size="18" font-weight="700" fill="{palette['muted']}">{_escape(book_label)}</text>

  {_title_svg(title_lines, 88, 294, palette['text'])}
  {_subtitle_svg(subtitle_lines, 88, 504, palette['muted'])}
  {_chips_svg(chips, 88, 606, palette)}

  {_illustration_block(index, palette)}

  <line x1="88" y1="582" x2="642" y2="582" stroke="rgba(255,255,255,0.14)"/>
  <text x="88" y="654" font-size="22" font-weight="700" fill="{palette['muted']}">{BRAND} · AI插画风专业模板</text>
</svg>
'''


def render_image_cards(image_plan: List[Dict], article: Dict | None = None, style: str = 'ai_editorial') -> List[str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_paths: List[str] = []
    article = article or {}
    book = article.get('book_info', {})
    book_title = book.get('title', '')

    for idx, plan in enumerate(image_plan[:4], start=1):
        palette = PALETTES[(idx - 1) % len(PALETTES)]
        section = plan.get('section') or f'核心观点{idx}'
        title = plan.get('image_theme') or section
        if ' / ' in title:
            _, title = title.split(' / ', 1)
        subtitle = (plan.get('image_keywords') or '').replace('极简插画,', '').replace('书籍观点,', '').strip(' ,')
        subtitle = _shorten(subtitle, 54)
        chips = _extract_keywords(subtitle, max_items=2)

        svg = _build_svg(idx, title.strip(), subtitle, section, book_title, chips, palette)
        svg_path = OUTPUT_DIR / f'point_{idx}.svg'
        png_path = OUTPUT_DIR / f'point_{idx}.png'
        svg_path.write_text(svg, encoding='utf-8')
        subprocess.run([
            'rsvg-convert', '-w', str(WIDTH), '-h', str(HEIGHT), '-o', str(png_path), str(svg_path)
        ], check=True)
        output_paths.append(str(png_path))

    return output_paths


if __name__ == '__main__':
    demo_plan = [
        {'section': '核心观点1', 'image_theme': '思考致富 / 想象力', 'image_keywords': '认知升级, 财富思维, 长期主义'},
        {'section': '核心观点2', 'image_theme': '思考致富 / 欲望', 'image_keywords': '目标感, 行动力, 决心'},
        {'section': '核心观点3', 'image_theme': '思考致富 / 信念', 'image_keywords': '自我暗示, 精神力量, 复利成长'},
        {'section': '核心观点4', 'image_theme': '思考致富 / 专业知识', 'image_keywords': '框架学习, 输出能力, 实践应用'},
    ]
    print(render_image_cards(demo_plan, article={'book_info': {'title': '思考致富'}}))
