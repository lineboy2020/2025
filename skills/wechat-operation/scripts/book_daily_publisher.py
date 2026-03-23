# -*- coding: utf-8 -*-
"""
财商书籍解读 - 微信公众号发布模块

功能：
1. 生成财商书籍解读文章
2. 结合当日市场热点
3. 自动发布到公众号草稿箱

Usage:
    python book_daily_publisher.py
    python book_daily_publisher.py --hot-topic "AI投资热潮"
    python book_daily_publisher.py --dry-run
"""

import argparse
import sys
import os
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 加载环境变量
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / 'config' / 'wechat_credentials.env'
load_dotenv(env_path)

from book_interpreter import generate_daily_article
from wechat_publisher import WechatPublisher
from wechat_formatter import WechatFormatter
from wechat_image_designer import render_image_cards


def build_article_image_plan(article: dict):
    book = article.get('book_info', {})
    concepts = book.get('core_concepts', [])
    plan = []
    for i, concept in enumerate(concepts[:4], start=1):
        plan.append({
            'section': f'核心观点{i}',
            'image_theme': f"{book.get('title', '')} / {concept}",
            'image_keywords': f"极简插画, 书籍观点, {concept}, 成长, 商业思维",
            'placement': f'正文第{i}个核心观点后',
            'image_url': ''
        })
    return plan


def upload_article_images(image_plan, publisher: WechatPublisher, source_image: str = ''):
    if not image_plan:
        return image_plan
    generated_dir = Path(__file__).parent.parent / 'output' / 'generated_images'
    for idx, plan in enumerate(image_plan, start=1):
        try:
            candidate = generated_dir / f'point_{idx}.png'
            img_path = str(candidate if candidate.exists() else (Path(source_image) if source_image else Path('/tmp/book_cover_daily.png')))
            result = publisher.upload_image(img_path, 'image')
            if result and result.get('success'):
                plan['image_url'] = result.get('url', '')
                plan['local_path'] = img_path
        except Exception:
            plan['image_url'] = ''
    return image_plan


def replace_image_placeholders_with_urls(content: str, image_plan):
    updated = content
    for plan in image_plan:
        placeholder = f"[配图建议：{plan['section']}｜{plan['image_theme']}｜{plan['image_keywords']}｜{plan['placement']}]"
        if plan.get('image_url'):
            replacement = f'<img src="{plan["image_url"]}" alt="{plan["image_theme"]}" />'
            updated = updated.replace(placeholder, replacement)
    return updated


def publish_book_article(hot_topic: str = "", dry_run: bool = False) -> dict:
    """
    生成并发布财商书籍解读文章
    
    Args:
        hot_topic: 市场热点话题
        dry_run: 是否为测试模式（不实际发布）
        
    Returns:
        发布结果字典
    """
    print("="*70)
    print("📚 财商书籍解读 - 公众号文章生成")
    print("="*70)
    
    # 1. 生成文章
    print(f"\n📝 正在生成文章...")
    if hot_topic:
        print(f"   结合热点: {hot_topic}")
    
    article = generate_daily_article(hot_topic=hot_topic)
    article['core_points'] = article.get('book_info', {}).get('core_concepts', [])[:5]
    article['image_plan'] = build_article_image_plan(article)
    if article.get('image_plan'):
        try:
            render_image_cards(article['image_plan'], article=article, style='editorial_cards')
            print(f"   已生成 {min(len(article['image_plan']), 4)} 张视觉卡片配图")
        except Exception as e:
            print(f"   配图生成失败，继续走原发布链路: {e}")
        lines = article['content'].splitlines()
        updated = []
        point_idx = 0
        for line in lines:
            updated.append(line)
            stripped = line.strip()
            if stripped.startswith('**核心概念深度解析') or stripped.startswith('**如何在日常生活中应用？**') or stripped.startswith('**真实案例启示**'):
                if point_idx < len(article['image_plan']):
                    plan = article['image_plan'][point_idx]
                    updated.append(f"[配图建议：{plan['section']}｜{plan['image_theme']}｜{plan['image_keywords']}｜{plan['placement']}]")
                    point_idx += 1
        while point_idx < len(article['image_plan']):
            plan = article['image_plan'][point_idx]
            updated.append(f"[配图建议：{plan['section']}｜{plan['image_theme']}｜{plan['image_keywords']}｜{plan['placement']}]")
            point_idx += 1
        article['content'] = "\n".join(updated)
    
    print(f"\n✅ 文章生成完成!")
    print(f"   标题: {article['title']}")
    print(f"   书籍: 《{article['book_info']['title']}》by {article['book_info']['author']}")
    print(f"   分类: {article['book_info']['category']}")
    print(f"   字数: {article['word_count']}")
    
    # 2. 格式化内容
    print(f"\n🎨 正在格式化...")
    formatter = WechatFormatter()
    article_data = {
        'title': article['title'],
        'content': article['content'],
        'author': '财商读书会'
    }
    formatted = formatter.format_for_wechat(article_data, theme="default")
    formatted_content = formatted.get('content', article['content'])
    
    # 3. 发布或保存
    if dry_run:
        print(f"\n🧪 测试模式 - 不发布到公众号")
        print(f"\n{'='*70}")
        print("预览内容:")
        print(f"{'='*70}\n")
        print(f"标题: {article['title']}\n")
        print(f"正文:\n{article['content']}\n")
        
        # 保存到本地
        output_dir = Path(__file__).parent.parent / "output" / "book_articles"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f"book_article_{article['generated_at'][:10]}.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# {article['title']}\n\n")
            f.write(f"**书籍**: 《{article['book_info']['title']}》by {article['book_info']['author']}\n\n")
            f.write(f"**分类**: {article['book_info']['category']}\n\n")
            f.write(f"**生成时间**: {article['generated_at']}\n\n")
            f.write(f"**字数**: {article['word_count']}\n\n")
            if article.get('core_points'):
                f.write("## 核心观点\n")
                for p in article['core_points']:
                    f.write(f"- {p}\n")
                f.write("\n")
            if article.get('image_plan'):
                f.write("## 配图建议\n")
                for plan in article['image_plan']:
                    f.write(f"- {plan['section']}｜{plan['image_theme']}｜{plan['image_keywords']}｜{plan['placement']}\n")
                f.write("\n")
            f.write("---\n\n")
            f.write(article['content'])
        
        print(f"✅ 已保存到: {output_file}")
        
        return {
            "success": True,
            "mode": "dry_run",
            "title": article['title'],
            "book": article['book_info'],
            "word_count": article['word_count'],
            "saved_to": str(output_file)
        }
    
    else:
        # 实际发布
        print(f"\n📤 正在发布到公众号草稿箱...")
        
        try:
            publisher = WechatPublisher()
            
            # 上传封面图片
            import urllib.request
            cover_path = '/tmp/book_cover_daily.png'
            if not os.path.exists(cover_path):
                # 下载封面图片
                urllib.request.urlretrieve('https://picsum.photos/900/383', cover_path)
            thumb_result = publisher.upload_image(cover_path, 'thumb')
            thumb_media_id = thumb_result.get('media_id') if thumb_result else None

            # 上传正文图片并替换占位
            article['image_plan'] = upload_article_images(article.get('image_plan', []), publisher, cover_path)
            article['content'] = replace_image_placeholders_with_urls(article['content'], article['image_plan'])
            article_data = {
                'title': article['title'],
                'content': article['content'],
                'author': '财商读书会',
                'core_points': article.get('core_points', [])
            }
            formatted = formatter.format_for_wechat(article_data, theme="default")
            formatted_content = formatted.get('content', article['content'])
            
            # 发布文章到草稿箱
            draft_article = {
                'title': article['title'],
                'content': formatted_content,
                'author': "财商读书会",
                'digest': f"深度解读《{article['book_info']['title']}》：{', '.join(article['book_info']['core_concepts'][:2])}",
                'thumb_media_id': thumb_media_id,
                'need_open_comment': 1,
                'only_fans_can_comment': 0
            }
            result = publisher.add_draft(draft_article)
            
            if result.get('media_id'):
                print(f"\n✅ 发布成功!")
                print(f"   草稿ID: {result.get('media_id', 'N/A')}")
                
                return {
                    "success": True,
                    "mode": "publish",
                    "title": article['title'],
                    "book": article['book_info'],
                    "word_count": article['word_count'],
                    "media_id": result.get('media_id'),
                    "published_at": article['generated_at']
                }
            else:
                print(f"\n❌ 发布失败: {result.get('error', '未知错误')}")
                return {
                    "success": False,
                    "error": result.get('error'),
                    "title": article['title']
                }
                
        except Exception as e:
            print(f"\n❌ 发布异常: {e}")
            return {
                "success": False,
                "error": str(e),
                "title": article['title']
            }


def main():
    parser = argparse.ArgumentParser(
        description="财商书籍解读 - 公众号自动发布",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python book_daily_publisher.py
  python book_daily_publisher.py --hot-topic "AI投资热潮"
  python book_daily_publisher.py --dry-run
        """
    )
    
    parser.add_argument(
        "--hot-topic",
        type=str,
        default="",
        help="市场热点话题（可选）"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="测试模式（不实际发布）"
    )
    
    args = parser.parse_args()
    
    # 执行发布
    result = publish_book_article(
        hot_topic=args.hot_topic,
        dry_run=args.dry_run
    )
    
    # 返回结果
    if result['success']:
        print(f"\n{'='*70}")
        print("✅ 任务完成")
        print(f"{'='*70}")
        return 0
    else:
        print(f"\n{'='*70}")
        print("❌ 任务失败")
        print(f"{'='*70}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
