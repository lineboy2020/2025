"""
智能排版引擎 (Wechat Formatter)
将 Markdown 转换为公众号兼容的 HTML
优化样式，提升阅读体验
"""
import re
import markdown
from typing import Dict, Optional
from datetime import datetime

class WechatFormatter:
    """公众号排版优化器"""

    def __init__(self, theme: str = 'pro'):
        self.theme = theme
        self.css_templates = {
            'default': self._default_css(),
            'tech': self._tech_css(),
            'minimal': self._minimal_css(),
            'fancy': self._fancy_css(),
            'pro': self._pro_css(),
        }

    def _default_css(self) -> str:
        return """
        <style>
        .rich_media_content {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.8;
            color: #333;
            max-width: 100%;
            padding: 20px 15px;
            font-size: 16px;
        }
        h1 { font-size: 22px; color: #1a1a1a; margin: 25px 0 20px; font-weight: bold; }
        h2 {
            font-size: 20px;
            color: #2c3e50;
            border-left: 4px solid #3498db;
            padding-left: 15px;
            margin: 30px 0 20px;
            font-weight: bold;
        }
        h3 { font-size: 18px; color: #34495e; margin: 25px 0 15px; font-weight: bold; }
        h4 { font-size: 16px; color: #555; margin: 20px 0 10px; font-weight: bold; }
        p { margin: 15px 0; text-align: justify; text-indent: 2em; }
        blockquote {
            border-left: 4px solid #e74c3c;
            background: #f8f9fa;
            padding: 15px 20px;
            margin: 20px 0;
            color: #555;
            font-style: italic;
            border-radius: 0 8px 8px 0;
        }
        blockquote p { text-indent: 0; margin: 5px 0; }
        code {
            background: #f4f4f4;
            padding: 2px 8px;
            border-radius: 4px;
            font-family: Monaco, Consolas, 'Courier New', monospace;
            font-size: 14px;
            color: #e74c3c;
        }
        pre {
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            margin: 20px 0;
        }
        pre code {
            background: none;
            padding: 0;
            color: #f8f8f2;
        }
        img { max-width: 100%; border-radius: 8px; margin: 20px auto; display: block; }
        ul, ol { margin: 15px 0; padding-left: 25px; }
        li { margin: 8px 0; line-height: 1.6; }
        .highlight {
            background: linear-gradient(120deg, #a8edea 0%, #fed6e3 100%);
            padding: 2px 8px;
            border-radius: 4px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }
        th {
            background: #f5f5f5;
            font-weight: bold;
        }
        hr {
            border: none;
            height: 1px;
            background: #eee;
            margin: 30px 0;
        }
        </style>
        """

    def _tech_css(self) -> str:
        return """
        <style>
        .rich_media_content {
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.75;
            color: #24292e;
            max-width: 100%;
            padding: 20px 15px;
            font-size: 15px;
        }
        h1 { font-size: 24px; color: #0366d6; margin: 30px 0 20px; border-bottom: 2px solid #0366d6; padding-bottom: 10px; }
        h2 { font-size: 20px; color: #0056b3; margin: 25px 0 15px; border-bottom: 1px solid #eee; padding-bottom: 8px; }
        h3 { font-size: 18px; color: #333; margin: 20px 0 12px; }
        p { margin: 12px 0; text-align: justify; }
        code { background: #f6f8fa; padding: 3px 8px; border-radius: 3px; font-size: 14px; color: #d73a49; }
        pre { background: #f6f8fa; border: 1px solid #e1e4e8; padding: 16px; border-radius: 6px; overflow-x: auto; }
        pre code { background: none; color: #24292e; }
        blockquote { border-left: 4px solid #0366d6; background: #f1f8ff; padding: 12px 16px; margin: 16px 0; color: #0366d6; }
        img { max-width: 100%; border-radius: 4px; margin: 16px auto; display: block; }
        .highlight { background: #fff8c5; padding: 2px 6px; border-radius: 2px; }
        </style>
        """

    def _minimal_css(self) -> str:
        return """
        <style>
        .rich_media_content {
            font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
            line-height: 2;
            color: #333;
            max-width: 100%;
            padding: 20px;
            font-size: 16px;
        }
        h1, h2, h3 { color: #000; margin: 30px 0 20px; font-weight: 500; }
        h1 { font-size: 24px; }
        h2 { font-size: 20px; }
        h3 { font-size: 18px; }
        p { margin: 20px 0; text-align: justify; text-indent: 2em; }
        blockquote { border-left: 3px solid #000; padding-left: 20px; margin: 20px 0; color: #666; }
        code { font-family: 'SF Mono', Monaco, monospace; font-size: 14px; }
        pre { background: #fafafa; padding: 20px; margin: 20px 0; overflow-x: auto; }
        img { max-width: 100%; margin: 20px auto; display: block; }
        </style>
        """

    def _fancy_css(self) -> str:
        return """
        <style>
        .rich_media_content {
            font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
            line-height: 1.8;
            color: #333;
            max-width: 100%;
            padding: 25px 20px;
            font-size: 16px;
            background: linear-gradient(180deg, #fff 0%, #f8f9fa 100%);
        }
        h1 {
            font-size: 26px;
            color: transparent;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            background-clip: text;
            margin: 30px 0 25px;
            text-align: center;
        }
        h2 {
            font-size: 22px;
            color: #fff;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 10px 20px;
            margin: 25px -20px;
            border-radius: 0;
        }
        h3 { font-size: 18px; color: #667eea; margin: 20px 0 15px; }
        p { margin: 15px 0; text-align: justify; }
        blockquote {
            border-left: 4px solid #667eea;
            background: linear-gradient(135deg, rgba(102,126,234,0.1) 0%, rgba(118,75,162,0.1) 100%);
            padding: 15px 20px;
            margin: 20px 0;
            border-radius: 0 10px 10px 0;
        }
        code { background: #f0f0f0; padding: 2px 8px; border-radius: 4px; color: #e91e63; }
        pre { background: #2d2d2d; color: #f8f8f2; padding: 20px; border-radius: 10px; margin: 20px 0; }
        img { max-width: 100%; border-radius: 12px; margin: 20px auto; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .highlight {
            background: linear-gradient(120deg, #f093fb 0%, #f5576c 100%);
            color: #fff;
            padding: 2px 10px;
            border-radius: 20px;
        }
        </style>
        """

    def _pro_css(self) -> str:
        return """
        <style>
        body {
            margin: 0;
            background: #f5f6f8;
        }
        .rich_media_content {
            font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.95;
            color: #202124;
            max-width: 100%;
            padding: 28px 18px 40px;
            font-size: 17px;
            background: #f5f6f8;
            letter-spacing: 0.2px;
        }
        .rich_media_content > * {
            box-sizing: border-box;
        }
        h1 {
            font-size: 30px;
            line-height: 1.45;
            color: #101828;
            margin: 8px 0 24px;
            font-weight: 800;
            letter-spacing: 0.6px;
        }
        h2 {
            font-size: 22px;
            line-height: 1.5;
            color: #111827;
            margin: 34px 0 18px;
            padding: 0 0 0 16px;
            border-left: 5px solid #111827;
            font-weight: 800;
        }
        h3 {
            font-size: 19px;
            color: #111827;
            margin: 26px 0 14px;
            font-weight: 700;
        }
        h4 {
            font-size: 17px;
            color: #374151;
            margin: 20px 0 10px;
            font-weight: 700;
        }
        p {
            margin: 16px 0;
            text-align: justify;
            text-indent: 2em;
            color: #2b2f36;
        }
        blockquote {
            margin: 24px 0;
            padding: 18px 18px 18px 20px;
            background: #ffffff;
            border-left: 4px solid #c7a96b;
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(17, 24, 39, 0.05);
            color: #374151;
        }
        blockquote p {
            text-indent: 0;
            margin: 6px 0;
        }
        img {
            width: 100%;
            max-width: 100%;
            border-radius: 18px;
            margin: 26px auto;
            display: block;
            box-shadow: 0 14px 36px rgba(15, 23, 42, 0.10);
        }
        ul, ol {
            margin: 14px 0 18px;
            padding-left: 28px;
            color: #2b2f36;
        }
        li {
            margin: 8px 0;
            line-height: 1.8;
        }
        hr {
            border: none;
            height: 1px;
            background: linear-gradient(90deg, transparent, #d0d5dd, transparent);
            margin: 36px 0;
        }
        code {
            background: #f2f4f7;
            color: #b54708;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 14px;
        }
        pre {
            background: #111827;
            color: #f8fafc;
            padding: 18px;
            border-radius: 12px;
            overflow-x: auto;
            margin: 20px 0;
        }
        pre code {
            background: none;
            color: inherit;
            padding: 0;
        }
        .highlight {
            background: linear-gradient(180deg, rgba(255,255,255,0) 55%, rgba(199,169,107,0.28) 55%);
            color: inherit;
            padding: 0 2px;
            border-radius: 0;
        }
        .wechat-image-caption {
            text-align: center;
            font-size: 13px;
            color: #98a2b3;
            margin-top: -10px;
            margin-bottom: 18px;
        }
        </style>
        """

    def format_for_wechat(self, article: Dict, theme: Optional[str] = None) -> Dict:
        md_content = article.get('raw_markdown', '') or article.get('content', '')
        selected_theme = theme or self.theme

        html_body = markdown.markdown(
            md_content,
            extensions=['extra', 'codehilite', 'toc', 'tables', 'fenced_code']
        )

        html_body = self._optimize_images(html_body)
        html_body = self._optimize_highlights(html_body)
        html_body = self._optimize_links(html_body)
        html_body = self._cleanup_paragraphs(html_body)

        css = self.css_templates.get(selected_theme, self._pro_css())
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            {css}
        </head>
        <body>
            <div class="rich_media_content">
                {html_body}
            </div>
        </body>
        </html>
        """

        plain_text = re.sub('<[^<]+?>', '', html_body)
        digest = plain_text[:120] + '...' if len(plain_text) > 120 else plain_text

        return {
            'title': article['title'],
            'content': full_html,
            'digest': digest,
            'thumb_media_id': None,
            'need_open_comment': 1,
            'only_fans_can_comment': 0,
            'theme': selected_theme,
            'formatted_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def _optimize_images(self, html: str) -> str:
        html = re.sub(
            r'<img src="([^"]+)" alt="([^"]*)" ?/?>',
            r'<img src="\1" alt="\2" style="width:100%;max-width:100%;border-radius:18px;display:block;margin:28px auto;" /><div class="wechat-image-caption">\2</div>',
            html
        )
        html = re.sub(
            r'<img src="([^"]+)"',
            r'<img src="\1" style="width:100%;max-width:100%;border-radius:18px;display:block;margin:28px auto;"',
            html
        )
        html = re.sub(r'\[配图建议：(.*?)\]', '', html)
        return html

    def _optimize_highlights(self, html: str) -> str:
        return re.sub(
            r'<strong>([^<]+)</strong>',
            r'<span class="highlight">\1</span>',
            html
        )

    def _optimize_links(self, html: str) -> str:
        return re.sub(
            r'<a href="[^"]+">([^<]+)</a>',
            r'<span style="color:#3559a6;">\1</span>',
            html
        )

    def _cleanup_paragraphs(self, html: str) -> str:
        html = re.sub(r'<p>\s*</p>', '', html)
        return html

    def generate_cover_prompt(self, title: str, style: str = 'editorial') -> str:
        prompts = {
            'editorial': f"Premium editorial illustration for WeChat article, Chinese aesthetic, refined composition, soft cinematic lighting, tasteful minimal luxury, {title}, professional content marketing style, high-end magazine feeling, 16:9",
            'business': f"High-end business editorial illustration, sophisticated color palette, clean and premium layout, {title}, suitable for professional WeChat official account, 16:9",
            'lifestyle': f"Elegant lifestyle editorial illustration, warm and artistic, tasteful composition, {title}, premium magazine style, 16:9",
            'creative': f"Art-directed illustration, premium Chinese content branding style, stylish and aesthetic, {title}, visually strong but clean, 16:9"
        }
        return prompts.get(style, prompts['editorial'])

    def add_watermark(self, html: str, watermark: str = "公众号名称") -> str:
        footer = f"""
        <div style="text-align:center;color:#98a2b3;font-size:12px;margin-top:36px;padding:18px 0;border-top:1px solid #e5e7eb;">
            —— {watermark} ——
        </div>
        """
        return html.replace('</body>', f'{footer}</body>')
