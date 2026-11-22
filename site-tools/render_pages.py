"""Render the searchable index and permanent article URLs from the public catalog."""
import html
import json
import zipfile
from collections import defaultdict
from pathlib import Path

def esc(value):
    return html.escape(str(value), quote=True)

def size(n):
    return f"{n / 1_000_000:.2f} MB" if n >= 1_000_000 else f"{max(1,round(n/1000))} KB"

def document(title, inner, article=False):
    base = "../" if article else ""
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · 学习笔记</title><link rel="stylesheet" href="{base}style.css"></head><body><a class="skip" href="#main">跳到正文</a><header><a class="brand" href="{base}index.html">学习笔记</a><span>课程资料</span></header><main class="shell" id="main">{inner}</main><footer>学习笔记 · 课程资料</footer></body></html>'''

def ranges(pages):
    spans=[]
    for page in pages:
        if spans and spans[-1][1]+1==page:spans[-1][1]=page
        else:spans.append([page,page])
    return "、".join(str(a) if a==b else f"{a}–{b}" for a,b in spans)

def options(values):
    return "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in values)

def make(docs, catalog, previews):
    groups = defaultdict(list)
    for r in catalog["items"]:
        groups[r["course"]].append(r)
    count = len(catalog["items"])
    body = f'<section class="intro"><h1>课程笔记</h1><p>{len(groups)} 门课程及专题 · {count} 份笔记和作业</p></section>'
    formats = sorted({r["format"] for r in catalog["items"]})
    body += f'''<div class="filters"><label>查找资料<input type="search" id="q" placeholder="题名、关键词或学期"></label><label>课程<select id="course"><option value="">全部课程</option>{options(groups)}</select></label><label>下载格式<select id="fmt"><option value="">全部格式</option>{options(formats)}</select></label></div><p id="count" class="summary" aria-live="polite"></p><p id="empty" hidden>没有匹配的资料。</p>'''
    articles = docs / "articles"
    articles.mkdir(exist_ok=True, parents=True)
    for course, rows in groups.items():
        body += f'<section class="course"><h2>{esc(course)} <small>{len(rows)} 份</small></h2>'
        for r in rows:
            rid, fmt = r["id"], r["format"]
            url = f'articles/{rid}.html'
            byline = " · ".join(v for v in [r["term"], r["type"]] if v)
            key = " ".join((course, r["title"], byline,fmt)).lower()
            body += f'<div class="entry" data-course="{esc(course)}" data-fmt="{esc(fmt)}" data-search="{esc(key)}"><div><a class="title" href="{url}">{esc(r["title"])}</a><div class="sub">{esc(byline)}</div></div><span class="tags">{esc(fmt)} · {size(r["bytes"])}</span></div>'
            download = r["url"] if r["url"].startswith("https://") else "../" + r["url"]
            view = previews.get(rid) or (r["url"] if fmt=="PDF" and not r["url"].startswith("https://") else None)
            info = " · ".join(filter(None,[r["term"],f'{r["pages"]} 页' if r.get("pages") else "",f'{fmt} · {size(r["bytes"])}']))
            item = f'<article class="article"><div class="intro"><p class="meta">{esc(course)}　/　{esc(r["type"])}</p><h1>{esc(r["title"])}</h1><p class="meta">{esc(info)}</p></div><div class="actions">'
            if view:
                item += f'<a href="../{esc(view)}">打开完整 PDF</a>'
            extension = r["ext"]
            filename = r["title"] + extension
            label = "下载 LaTeX 源文件" if fmt=="LaTeX" else "下载 "+fmt
            item += f'<a download="{esc(filename)}" href="{esc(download)}">{esc(label)}</a></div>'
            if r.get("original_pages"):
                item += f'<p class="meta">原册 {r["original_pages"]} 页，阅读版收录其中 {r["pages"]} 页。</p>'
            if r.get("source_pages"):
                item += f'<details><summary>查看收录的原页码</summary><p>{ranges(r["source_pages"])}</p></details>'
            if view:
                item += f'<object class="reader" aria-label="{esc(r["title"])} PDF" type="application/pdf" data="../{esc(view)}#view=FitH"><a href="../{esc(view)}">在 PDF 阅读器中打开</a></object>'
            elif fmt == "LaTeX":
                item += '<p class="notice">下载源文件后可用 XeLaTeX 或 Tectonic 编译阅读。</p>'
                file = docs / r["url"]
                if file.is_file():
                    if file.suffix == ".zip":
                        with zipfile.ZipFile(file) as z:
                            source = z.read(r["main"])
                    else:
                        source = file.read_bytes()
                    text = source.decode("utf-8-sig", errors="replace")
                    if len(text) <= 2_000_000:
                        item += '<details><summary>查看主文件 LaTeX 源码</summary><pre style="overflow:auto;max-height:65vh;tab-size:2">' + esc(text) + "</pre></details>"
            elif fmt == "Goodnotes":
                item += '<p class="notice">下载后可用 Goodnotes 打开完整笔记。</p>'
            (docs/url).write_text(document(r["title"], item+"</article>", True), encoding="utf-8")
        body += "</section>"
    (docs/"index.html").write_text(document("课程笔记",body+'<script defer src="index.js"></script>'), encoding="utf-8")

