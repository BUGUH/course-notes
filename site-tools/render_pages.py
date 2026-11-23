"""Render the public course index and the reading page for each approved original."""
from collections import defaultdict
from html import escape
from pathlib import Path
import json
import re

def esc(val):return escape(str(val),quote=True)
def size(n):return f"{n/1_000_000:.2f} MB" if n>=1_000_000 else f"{max(1,round(n/1000))} KB"
def opts(values):return "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in values)
def ranges(nums):
    spans=[]
    for n in nums:
        if spans and spans[-1][1]+1==n:spans[-1][1]=n
        else:spans.append([n,n])
    return "、".join(str(a) if a==b else f"{a}–{b}" for a,b in spans)
SUBJECTS={
    "分析与方程":"数学分析 数学分析（二） 数学分析（三） 实分析 复分析 泛函分析 常微分方程 偏微分方程 遍历论",
    "代数与离散数学":"高等代数 近世代数 初等数论 图论",
    "几何与拓扑":"微分几何 拓扑学",
    "概率与统计":"概率论与数理统计 随机过程",
    "计算与数据科学":"科学计算 微分方程数值解 最优化方法 人工智能的数学基础 数据科学基础 强化学习 计算机科学导论",
    "应用与专题":"大学物理 流体力学简介 应用数学 专业研讨课（二） 专业研讨课（四） 知识论 夏令营",
}
subjects={c:s for s,words in SUBJECTS.items() for c in words.split()}
def homefilter(**kwargs):
    from urllib.parse import urlencode
    return "index.html?"+urlencode(kwargs)

def document(title,body,root="",article=False):
    brand=f'<a class="brand" href="{root}index.html">BUGUH<span> / </span>学习笔记</a>'
    nav=f'<nav class="mainnav" aria-label="站点导航"><a href="{root}index.html">资料库</a><a href="{root}courses.html">课程</a><a href="{root}categories.html">分类</a></nav>'
    tools=f'<div class="tools"><a class="search-link" href="{root}index.html#q" aria-label="搜索资料">⌕</a><button type="button" id="theme" aria-label="切换明暗主题" title="切换明暗主题">◐</button></div>'
    header=f'<header class="site-head"><div class="head-inner">{brand}{nav}{tools}</div></header>'
    return f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>{esc(title)} · BUGUH 学习笔记</title><link rel="stylesheet" href="{root}style.css"><script src="{root}preferences.js"></script></head><body><a class="skip" href="#main">跳到正文</a>{header}<main id="main" class="shell">{body}</main><footer><span>BUGUH · 学习笔记</span><a href="https://github.com/BUGUH/course-notes">GitHub</a></footer></body></html>'

def linkrow(name,url,count):
    return f'<a class="listlink" href="{esc(url)}"><span>{esc(name)}</span><small>{count} 份</small></a>'
def series_order(rows):
    # Use the numbers in the author's own assignment or chapter titles when present.
    def key(row):
        t=row["title"];m=re.search(r"(?:hw\s*|作业\s*|第\s*)(\d+)",t,re.I)
        return (0,int(m[1])) if m else (1,0)
    return sorted(rows,key=key)
def article(docs,r,group,previews,meta,fragment):
    rid=r["id"];course=r["course"];s=subjects.get(course,"应用与专题")
    pos=next(i for i,v in enumerate(group) if v["id"]==rid)
    base="../";pdf=previews.get(rid) or (r["url"] if r["format"]=="PDF" else None)
    t=r.get("transcription")
    chosen=t["pdf"] if t else pdf
    pages=(t["pages"] if t else r["pages"]) or 1
    back=f'<a class="back" href="../index.html">返回资料列表</a>'
    badges="".join(f'<a class="tag" href="../{esc(homefilter(**{key:value}))}">{esc(value)}</a>' for key,value in (("subject",s),("course",course)))
    term=esc(r.get("term") or "")
    top=f'<div class="pubmeta"><a href="../{esc(homefilter(type=r["type"]))}">{esc(r["type"])}</a>{("<span>"+term+"</span>") if term else ""}<span>{pages} 页</span></div><h1>{esc(r["title"])}</h1><div class="tags">{badges}</div>'
    course_url="../"+homefilter(course=course)
    if len(group)>1:top+=f'<a class="series" href="{esc(course_url)}">{esc(course)}　{pos+1} / {len(group)} 份</a>'
    top+='<div class="rule"></div>'
    def dl(url,title,label):return f'<a href="../{esc(url)}" download="{esc(title)}">{esc(label)}</a>'
    links=[dl(r["url"],r["title"]+r["ext"],f'下载原件 · {r["format"]} · {size(r["bytes"])}')]
    if r.get("corrected"):
        links=[dl(r["url"],r["title"]+r["ext"],f'下载订正版源文件 · {size(r["bytes"])}')]
    if pdf:links.insert(0,f'<a href="../{esc(pdf)}">打开{"订正" if r.get("corrected") else "原稿"} PDF</a>')
    if t:
        links+=[dl(t["pdf"],r["title"]+"-排版.pdf","下载排版 PDF"),dl(t["source"],r["title"]+"-排版."+t["source"].rsplit(".",1)[-1],"下载排版源文件")]
    download='<section class="downloads" id="downloads"><h2>文件下载</h2><div class="actions">'+"".join(links)+'</div></section>'
    if r.get("source_pages") and r.get("original_pages"):
        download+=f'<details><summary>查看收录的原页码</summary><p>原册 {r["original_pages"]} 页，本版收录 {ranges(r["source_pages"])} 页。</p></details>'
    contents=[];html=""
    if fragment:
        html=fragment["html"];contents=[(sec["id"],sec["name"],sec["level"]) for sec in fragment["headings"]]
        html=re.sub(r'(<math\s+display="(block|inline)"[\s\S]*?</math>)',
                    lambda match:f'<span class="math {match[2]}">{match[1]}</span>',html)
        html='<div class="prose">'+html+'</div>'
    elif chosen:
        m=meta.get(rid,{}) if not t else {}
        headings=m.get("outline",[])
        if headings:contents=[(f'page-{h["page"]}',h["label"],h["level"]) for h in headings if 1<=h["page"]<=pages]
        else:
            step=1 if pages<=12 else (5 if pages<=70 else 10)
            folios=r.get("source_pages") if not t else None
            for i in range(1,pages+1,step):
                n=folios[i-1] if folios and len(folios)==pages else i
                contents.append((f"page-{i}",f"原册第 {n} 页" if folios else f"第 {i} 页",1))
        ratio=m.get("ratio",0.707)
        html=f'<section id="original" class="facsimile" aria-label="原文阅读" data-url="../{esc(chosen)}" data-pages="{pages}" data-ratio="{float(ratio):.4f}"><div class="readtools"><span>{"排版稿" if t else "原稿"}</span><label>页码 <input id="page-number" type="number" min="1" max="{pages}" value="1"></label><span>/ {pages}</span><a href="../{esc(chosen)}">打开 PDF</a></div><div id="sheets"></div><p class="load-note" id="reader-status" role="status">正在载入原文。</p><noscript><a href="../{esc(chosen)}">打开 PDF 阅读原文</a></noscript></section>'
    for extra in [("downloads","文件下载",1)]:contents.append(extra)
    contents_html="".join(f'<a href="#{esc(i)}" class="depth-{min(3,max(1,int(level)))}">{esc(name)}</a>' for i,name,level in contents)
    if r.get("corrected"):html=html.replace('>原稿</span>','>订正版</span>')
    toc='<aside class="toc" aria-label="文章目录"><details open><summary>目录</summary><nav>'+contents_html+'</nav></details></aside>'
    def adjacent(i,label):
        if not 0<=i<len(group):return ""
        x=group[i]
        return f'<a href="{x["id"]}.html"><small>{label}</small><strong>{esc(x["title"])}</strong></a>'
    prevnext='<nav class="prevnext" aria-label="同课程资料">'+adjacent(pos-1,"同课程上一篇")+adjacent(pos+1,"同课程下一篇")+'</nav>'
    script='<script type="module" src="../reader.js"></script>'
    page=back+'<div class="reading-grid"><article>'+top+html+download+prevnext+'</article>'+toc+'</div>'+script
    (docs/"articles"/(rid+".html")).write_text(document(r["title"],page,base,True),encoding="utf8")

def make(docs,catalog,previews):
    rows=catalog["items"];groups=defaultdict(list);types=defaultdict(list);by_subject=defaultdict(list)
    for r in rows:
        groups[r["course"]].append(r);types[r["type"]].append(r);by_subject[subjects.get(r["course"],"应用与专题")].append(r)
    for c in groups:groups[c]=series_order(groups[c])
    data_path=Path(__file__).with_name("reader-meta.json");meta=json.loads(data_path.read_text(encoding="utf-8-sig")) if data_path.exists() else {}
    fragments={}
    fragment_path=Path(__file__).with_name("reading-content.json")
    if fragment_path.exists():fragments=json.loads(fragment_path.read_text(encoding="utf-8-sig"))
    (docs/"articles").mkdir(parents=True,exist_ok=True)
    formats=sorted({r["format"] for r in rows})
    if any("transcription" in r or r.get("corrected") for r in rows):formats.append("已校对的 LaTeX 排版稿")
    body=f'<section class="index-title"><h1>课程笔记</h1><p>{len(groups)} 门课程及专题 · {len(rows)} 份资料</p></section>'
    body+='<div class="filters"><label>搜索<input type="search" id="q" placeholder="题名、课程或关键词"></label>'
    for f,name,values in (("subject","学科",by_subject),("course","课程",groups),("type","资料类型",types),("fmt","格式或版本",formats)):
        body+=f'<label>{name}<select id="{f}"><option value="">全部</option>{opts(sorted(values))}</select></label>'
    body+='</div><p id="count" class="summary" aria-live="polite"></p><p id="empty" hidden>没有匹配的资料。</p>'
    for c,group in groups.items():
        body+=f'<section class="course"><h2>{esc(c)} <small>{len(group)} 份</small></h2>'
        for r in group:
            rid=r["id"];fmt=r["format"];subject=subjects.get(c,"应用与专题")
            editions=[fmt]
            if rid in previews and "PDF" not in editions:editions.append("PDF")
            if r.get("transcription") or r.get("corrected"):editions.extend(v for v in ("LaTeX","PDF","已校对的 LaTeX 排版稿") if v not in editions)
            byline=" · ".join(filter(None,[r.get("term"),r["type"],"订正版" if r.get("corrected") else "已校排版" if r.get("transcription") else None]))
            key=" ".join([c,subject,r["title"],byline,*editions]).lower()
            body+=f'<div class="entry" data-subject="{esc(subject)}" data-course="{esc(c)}" data-type="{esc(r["type"])}" data-fmt="{esc(fmt)}" data-editions="{esc("|".join(editions))}" data-search="{esc(key)}"><div><a class="title" href="articles/{rid}.html">{esc(r["title"])}</a><div class="sub">{esc(byline)}</div></div><small>{esc(fmt)} · {size(r["bytes"])}</small></div>'
            fragment=fragments.get(rid)
            expected=r.get("transcription",{}).get("source",r["url"]).rsplit("/",1)[-1].split(".")[0]
            if fragment and fragment["source_sha256"]==expected and r.get("web_reading")=="files/"+fragment["digest"]+".html":
                import hashlib
                raw=(docs/r["web_reading"]).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=fragment["digest"]:raise ValueError("Web edition digest mismatch")
                fragment=dict(fragment,html=raw.decode("utf-8"))
            else:fragment=None
            article(docs,r,group,previews,meta,fragment)
        body+='</section>'
    (docs/"index.html").write_text(document("课程笔记",body+'<script defer src="index.js"></script>'),encoding="utf8")
    courses='<section class="index-title"><h1>课程</h1></section>'
    for s in SUBJECTS:
        cs=[c for c in groups if subjects.get(c)==s]
        if cs:courses+=f'<section class="course"><h2>{esc(s)}</h2><div class="linkgrid">'+''.join(linkrow(c,homefilter(course=c),len(groups[c])) for c in cs)+'</div></section>'
    (docs/"courses.html").write_text(document("课程",courses),encoding="utf8")
    categories='<section class="index-title"><h1>分类</h1></section>'
    for title,values,key in (("按资料类型",types,"type"),("按学科",by_subject,"subject")):
        categories+=f'<section class="course"><h2>{title}</h2><div class="linkgrid">'+''.join(linkrow(v,homefilter(**{key:v}),len(values[v])) for v in sorted(values))+'</div></section>'
    (docs/"categories.html").write_text(document("分类",categories),encoding="utf8")

