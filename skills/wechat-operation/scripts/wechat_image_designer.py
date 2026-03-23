# -*- coding: utf-8 -*-
"""
微信文章配图生成器（轻量模板版）

目标：
- 不引入 Pillow 等重依赖
- 直接输出 SVG，再用 rsvg-convert 转 PNG
- 保持现有输出路径：output/generated_images/point_1.png ~ point_4.png
- 先把“程序图”升级成更像公众号视觉卡片的设计模板图
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


PALETTES = [
    {
        'bg1': '#0f172a',
        'bg2': '#1d4ed8',
        'accent': '#60a5fa',
        'card': 'rgba(255,255,255,0.10)',
        'line': 'rgba(255,255,255,0.18)',
        'text': '#f8fafc',
        'muted': '#cbd5e1',
        'tag_bg': 'rgba(96,165,250,0.16)',
        'tag_text': '#bfdbfe',
    },
    {
        'bg1': '#1f2937',
        'bg2': '#7c3aed',
        'accent': '#c084fc',
        'card': 'rgba(255,255,255,0.09)',
        'line': 'rgba(255,255,255,0.16)',
        'text': '#ffffff',
        'muted': '#e9d5ff',
        'tag_bg': 'rgba(192,132,252,0.16)',
        'tag_text': '#f3e8ff',
    },
    {
        'bg1': '#0b3b2e',
        'bg2': '#0f766e',
        'accent': '#2dd4bf',
        'card': 'rgba(255,255,255,0.10)',
        'line': 'rgba(255,255,255,0.16)',
        'text': '#f0fdfa',
        'muted': '#ccfbf1',
        'tag_bg': 'rgba(45,212,191,0.14)',
        'tag_text': '#ccfbf1',
    },
    {
        'bg1': '#4c0519',
        'bg2': '#be185d',
        'accent': '#f472b6',
        'card': 'rgba(255,255,255,0.10)',
        'line': 'rgba(255,255,255,0.16)',
        'text': '#fff1f2',
        'muted': '#fbcfe8',
        'tag_bg': 'rgba(244,114,182,0.14)',
        'tag_text': '#fce7f3',
    },
]


def _escape(text: str) -> str:
    return html.escape(text or '')


def _wrap_text(text: str, limit: int = 18, max_lines: int = 3) -> List[str]:
    text = (text or '').strip()
    if not text:
        return []
    lines = []
    buf = ''
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


def _build_svg(index: int, title: str, subtitle: str, tag: str, palette: Dict[str, str]) -> str:
    title_lines = _wrap_text(title, limit=16, max_lines=3)
    subtitle_lines = _wrap_text(subtitle, limit=24, max_lines=3)

    title_svg = []
    title_y = 250
    for i, line in enumerate(title_lines):
        title_svg.append(
            f'<text x="110" y="{title_y + i * 74}" font-size="54" font-weight="800" fill="{palette["text"]}" letter-spacing="1">{_escape(line)}</text>'
        )

    subtitle_svg = []
    subtitle_y = 500
    for i, line in enumerate(subtitle_lines):
        subtitle_svg.append(
            f'<text x="110" y="{subtitle_y + i * 44}" font-size="28" font-weight="500" fill="{palette["muted"]}">{_escape(line)}</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{palette['bg1']}"/>
      <stop offset="100%" stop-color="{palette['bg2']}"/>
    </linearGradient>
    <linearGradient id="glow" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{palette['accent']}" stop-opacity="0.55"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0.05"/>
    </linearGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="40"/></filter>
  </defs>

  <rect width="100%" height="100%" fill="url(#bg)" rx="36"/>
  <circle cx="920" cy="110" r="180" fill="url(#glow)" filter="url(#blur)"/>
  <circle cx="140" cy="640" r="160" fill="{palette['accent']}" fill-opacity="0.10" filter="url(#blur)"/>

  <rect x="70" y="60" width="940" height="600" rx="28" fill="{palette['card']}" stroke="{palette['line']}"/>
  <rect x="110" y="110" width="156" height="44" rx="22" fill="{palette['tag_bg']}" stroke="{palette['line']}"/>
  <text x="188" y="139" text-anchor="middle" font-size="22" font-weight="700" fill="{palette['tag_text']}">{_escape(tag)}</text>

  <text x="110" y="190" font-size="24" font-weight="700" fill="{palette['accent']}">POINT 0{index}</text>
  {''.join(title_svg)}
  {''.join(subtitle_svg)}

  <line x1="110" y1="600" x2="970" y2="600" stroke="{palette['line']}"/>
  <text x="110" y="640" font-size="24" font-weight="600" fill="{palette['muted']}">财商读书会 · 微信公众号视觉卡片</text>

  <g transform="translate(820,420)">
    <rect x="0" y="0" width="120" height="120" rx="26" fill="rgba(255,255,255,0.08)" stroke="{palette['line']}"/>
    <circle cx="60" cy="60" r="26" fill="none" stroke="{palette['accent']}" stroke-width="3"/>
    <path d="M60 38 L60 82 M38 60 L82 60" stroke="{palette['accent']}" stroke-width="3" stroke-linecap="round"/>
  </g>
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
        title = plan.get('image_theme') or plan.get('section') or f'核心观点{idx}'
        subtitle = plan.get('image_keywords') or ''
        if book_title and book_title not in title:
            subtitle = f"《{book_title}》 · {subtitle}" if subtitle else f"《{book_title}》"
        tag = plan.get('section') or f'核心观点{idx}'

        svg = _build_svg(idx, title=title, subtitle=subtitle, tag=tag, palette=palette)
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
        {'section': '核心观点1', 'image_theme': '资产与负债', 'image_keywords': '极简插画, 财富思维, 长期主义'},
        {'section': '核心观点2', 'image_theme': '被动收入系统', 'image_keywords': '增长飞轮, 复利, 认知升级'},
        {'section': '核心观点3', 'image_theme': '多元思维模型', 'image_keywords': '框架, 决策, 商业洞察'},
        {'section': '核心观点4', 'image_theme': '从知道到做到', 'image_keywords': '行动, 习惯, 实践'},
    ]
    print(render_image_cards(demo_plan, article={'book_info': {'title': '富爸爸穷爸爸'}}))
