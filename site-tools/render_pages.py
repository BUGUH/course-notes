"""Render the public course index and the reading page for each approved original."""
from collections import defaultdict
from html import escape
from pathlib import Path
import json
import re
import hashlib
from datetime import datetime, timezone
from email.utils import format_datetime
import xml.etree.ElementTree as ET
from bisect import bisect_right
from html.parser import HTMLParser
from urllib.parse import quote, unquote

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
    nav=f'<nav class="mainnav" aria-label="站点导航"><a href="{root}index.html">资料库</a><a href="{root}courses.html">课程</a><a href="{root}series.html">系列</a><a href="{root}categories.html">分类</a><a href="{root}tags.html">标签</a></nav>'
    tools=f'<div class="tools"><a class="search-link" href="{root}index.html#q" aria-label="搜索资料">⌕</a><button type="button" id="theme" aria-label="切换明暗主题" title="切换明暗主题">◐</button></div>'
    header=f'<header class="site-head"><div class="head-inner">{brand}{nav}{tools}</div></header>'
    return f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>{esc(title)} · BUGUH 学习笔记</title><link rel="stylesheet" href="{root}style.css"><link rel="alternate" type="application/rss+xml" title="BUGUH 学习笔记" href="{root}feed.xml"><script src="{root}preferences.js"></script></head><body><a class="skip" href="#main">跳到正文</a>{header}<main id="main" class="shell">{body}</main><footer><span>BUGUH · 学习笔记</span><nav aria-label="更多入口"><a href="{root}archive.html">归档</a> · <a href="{root}feed.xml">RSS</a> · <a href="https://github.com/BUGUH/course-notes">GitHub</a></nav></footer></body></html>'

def linkrow(name,url,count):
    return f'<a class="listlink" href="{esc(url)}"><span>{esc(name)}</span><small>{count} 份</small></a>'

def topic_url(label):
    return "tags/"+quote(label,safe="")+".html"

def load_discovery(rows):
    path=Path(__file__).with_name("discovery-content.json")
    if not path.exists():return {}
    data=json.loads(path.read_text(encoding="utf8"))
    catalogue=Path(__file__).resolve().parent.parent/"catalog.json"
    canonical=json.dumps(json.loads(catalogue.read_text(encoding="utf-8-sig")),
                         ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf8")
    if hashlib.sha256(canonical).hexdigest()!=data["catalog_content_sha256"]:
        raise ValueError("Rebuild discovery data for the current catalogue")
    documents=data["documents"]
    if set(documents)!={r["id"] for r in rows}:raise ValueError("Discovery scope mismatch")
    for row in rows:
        if documents[row["id"]]["pdf_sha256"]!=row["sha256"]:
            raise ValueError("Discovery content belongs to another PDF edition")
    return documents
def series_order(rows):
    # Use the numbers in the author's own assignment or chapter titles when present.
    def key(row):
        t=row["title"];m=re.search(r"(?:hw\s*|作业\s*|第\s*)(\d+)",t,re.I)
        return (0,int(m[1])) if m else (1,0)
    return sorted(rows,key=key)
class FragmentLocations(HTMLParser):
    """Locate boundaries without serializing or changing reviewed mathematics."""
    voids={"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}
    def __init__(self,raw):
        super().__init__(convert_charrefs=False)
        self.offsets=[0]
        for line in raw.split("\n")[:-1]:self.offsets.append(self.offsets[-1]+len(line)+1)
        self.stack=[];self.ids={}
        self.feed(raw)
        if self.stack:raise ValueError("Unbalanced reviewed HTML fragment")
    def handle_starttag(self,tag,attrs):
        key=dict(attrs).get("id")
        if key:
            if key in self.ids:raise ValueError("Duplicate fragment anchor")
            line,col=self.getpos()
            self.ids[key]=(self.offsets[line-1]+col,tuple(self.stack),tag)
        if tag not in self.voids:self.stack.append(tag)
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in self.voids:self.handle_endtag(tag)
    def handle_endtag(self,tag):
        if not self.stack or self.stack[-1]!=tag:raise ValueError("Unbalanced reviewed HTML tags")
        self.stack.pop()

def book_sections(row,fragment,meta):
    headings=fragment["headings"] if fragment else meta.get(row["id"],{}).get("outline",[])
    if not headings:return []
    level=min(h["level"] for h in headings)
    top=[h for h in headings if h["level"]==level]
    if len(top)<2:return []
    chapters=[]
    locations=FragmentLocations(fragment["html"]) if fragment else None
    starts=[locations.ids[h["id"]][0] for h in top] if fragment else []
    if starts!=sorted(set(starts)):raise ValueError("Chapter order differs from reviewed body")
    for i,h in enumerate(top):
        name=h["name"] if fragment else h["label"]
        key=h["id"] if fragment else str(h["page"])+":"+name
        suffix=hashlib.sha256(key.encode("utf8")).hexdigest()[:12]
        chapter={"name":name,"slug":row["id"]+"-s"+suffix,"position":i+1}
        if fragment:
            start=0 if i==0 else starts[i]
            end=starts[i+1] if i+1<len(top) else len(fragment["html"])
            if locations.ids[h["id"]][1]:raise ValueError("Chapter boundary must be at the fragment root")
            chapter.update(start=start,end=end,
                           headings=[x for x in headings if start<=locations.ids[x["id"]][0]<end],
                           raw=fragment["html"][start:end])
            FragmentLocations(chapter["raw"])
        else:
            first=1 if i==0 else h["page"]
            last=max(h["page"],top[i+1]["page"]-1) if i+1<len(top) else row["pages"]
            if not 1<=first<=last<=row["pages"]:raise ValueError("Invalid reviewed chapter page range")
            chapter.update(first=first,last=last)
        chapters.append(chapter)
    if fragment:
        if "".join(x["raw"] for x in chapters)!=fragment["html"]:raise ValueError("Chapter body coverage mismatch")
        boundaries=[c["start"] for c in chapters]
        owners={key:chapters[bisect_right(boundaries,value[0])-1]["slug"] for key,value in locations.ids.items()}
        for chapter in chapters:
            def relocate(match):
                target=unquote(match[2]);owner=owners.get(target)
                if owner and owner!=chapter["slug"]:
                    return 'href='+match[1]+owner+'.html#'+quote(target,safe="")+match[1]
                return match[0]
            chapter["html"]=re.sub(r'''\bhref=(["'])#([^"']+)\1''',relocate,chapter["raw"])
    else:
        covered={p for chapter in chapters for p in range(chapter["first"],chapter["last"]+1)}
        if covered!=set(range(1,row["pages"]+1)):raise ValueError("Chapter PDF coverage mismatch")
    return chapters

def series_index(docs,row,chapters):
    body=f'<a class="back" href="../articles/{row["id"]}.html">整份阅读</a><section class="index-title"><p>{esc(row["course"])}</p><h1>{esc(row["title"])}</h1><p>{len(chapters)} 节 · 按原文顺序</p></section><ol class="chapter-list">'
    for chapter in chapters:
        position=chapter["position"]
        note=f'PDF 第 {chapter["first"]}–{chapter["last"]} 页' if "first" in chapter else "网页正文"
        body+=f'<li><a class="listlink" href="../articles/{chapter["slug"]}.html"><span>{esc(chapter["name"])}</span><small>{esc(note)}</small></a></li>'
    body+='</ol>'
    (docs/"series"/(row["id"]+".html")).write_text(document(row["title"]+" · 分节目录",body,"../"),encoding="utf8")

def article(docs,r,group,previews,meta,fragment,discovery=None,book=None,chapter=None):
    rid=r["id"];course=r["course"];s=subjects.get(course,"应用与专题")
    pos=next(i for i,v in enumerate(group) if v["id"]==rid)
    base="../";pdf=previews.get(rid) or (r["url"] if r["format"]=="PDF" else None)
    t=r.get("transcription")
    chosen=t["pdf"] if t else pdf
    pages=(t["pages"] if t else r["pages"]) or 1
    back=f'<a class="back" href="../index.html">返回资料列表</a>'
    badges="".join(f'<a class="tag" href="../{esc(homefilter(**{key:value}))}">{esc(value)}</a>' for key,value in (("subject",s),("course",course)))
    badges+="".join(f'<a class="tag concept" href="../{topic_url(label)}">{esc(label)}</a>'
                    for label in (discovery or {}).get("tags",[]))
    term=esc(r.get("term") or "")
    title=chapter["name"] if chapter else r["title"]
    folio=f'PDF 第 {chapter["first"]}–{chapter["last"]} 页' if chapter and "first" in chapter else f'{pages} 页'
    top=f'<div class="pubmeta"><a href="../{esc(homefilter(type=r["type"]))}">{esc(r["type"])}</a>{("<span>"+term+"</span>") if term else ""}<span>{folio}</span></div><h1>{esc(title)}</h1><div class="tags">{badges}</div>'
    course_url="../"+homefilter(course=course)
    if len(group)>1:top+=f'<a class="series" href="{esc(course_url)}">{esc(course)}　{pos+1} / {len(group)} 份</a>'
    if book:
        label=f'{r["title"]} · 第 {chapter["position"]} / {len(book)} 节' if chapter else f'分节目录 · {len(book)} 节'
        top+=f'<a class="series book-series" href="../series/{rid}.html">{esc(label)}</a>'
        if chapter:top+=f'<a class="whole-book" href="{rid}.html">整份阅读</a>'
    top+='<div class="rule"></div>'
    def dl(url,title,label):return f'<a href="../{esc(url)}" download="{esc(title)}">{esc(label)}</a>'
    links=[dl(r["url"],r["title"]+r["ext"],f'下载原件 · {r["format"]} · {size(r["bytes"])}')]
    pdf_label="原稿"
    if r.get("corrected"):
        links=[dl(r["url"],r["title"]+r["ext"],f'下载订正版 · {r["format"]} · {size(r["bytes"])}')]
        pdf_label="订正"
    elif r.get("reviewed"):
        links=[dl(r["url"],r["title"]+r["ext"],f'下载已校排版稿 · {r["format"]} · {size(r["bytes"])}')]
        pdf_label="已校"
    if pdf:links.insert(0,f'<a href="../{esc(pdf)}">打开{pdf_label} PDF</a>')
    if t:
        links+=[dl(t["pdf"],r["title"]+"-排版.pdf","下载排版 PDF"),dl(t["source"],r["title"]+"-排版."+t["source"].rsplit(".",1)[-1],"下载排版源文件")]
    download='<section class="downloads" id="downloads"><h2>文件下载</h2><div class="actions">'+"".join(links)+'</div></section>'
    if r.get("source_pages") and r.get("original_pages"):
        download+=f'<details><summary>查看收录的原页码</summary><p>原册 {r["original_pages"]} 页，本版收录 {ranges(r["source_pages"])} 页。</p></details>'
    contents=[];html=""
    if fragment:
        html=fragment["html"];contents=[(sec["id"],sec["name"],sec["level"]) for sec in fragment["headings"]]
        html=re.sub(r'(<math\s+display="(block|inline)"[\s\S]*?</math>)',
                    lambda match:f'<span class="math {"display" if match[2]=="block" else "inline"}">{match[1]}</span>',html)
        html='<div class="prose">'+html+'</div>'
    elif chosen:
        m=meta.get(rid,{}) if not t else {}
        headings=m.get("outline",[])
        first,last=(chapter["first"],chapter["last"]) if chapter else (1,pages)
        if headings:contents=[(f'page-{h["page"]}',h["label"],h["level"]) for h in headings if first<=h["page"]<=last]
        else:
            step=1 if pages<=12 else (5 if pages<=70 else 10)
            folios=r.get("source_pages") if not t else None
            for i in range(1,pages+1,step):
                n=folios[i-1] if folios and len(folios)==pages else i
                contents.append((f"page-{i}",f"原册第 {n} 页" if folios else f"第 {i} 页",1))
        ratio=m.get("ratio",0.707)
        html=f'<section id="original" class="facsimile" aria-label="原文阅读" data-url="../{esc(chosen)}" data-pages="{pages}" data-start-page="{first}" data-end-page="{last}" data-ratio="{float(ratio):.4f}"><div class="readtools"><span>{"排版稿" if t else "原稿"}</span><label>页码 <input id="page-number" type="number" min="{first}" max="{last}" value="{first}"></label><span>/ {pages}</span><a href="../{esc(chosen)}#page={first}">打开 PDF</a></div><div id="sheets"></div><p class="load-note" id="reader-status" role="status">正在载入原文。</p><noscript><a href="../{esc(chosen)}#page={first}">打开 PDF 阅读原文</a></noscript></section>'
    for extra in [("downloads","文件下载",1)]:contents.append(extra)
    contents_html="".join(f'<a href="#{esc(i)}" class="depth-{min(3,max(1,int(level)))}">{esc(name)}</a>' for i,name,level in contents)
    if r.get("corrected"):html=html.replace('>原稿</span>','>订正版</span>')
    elif r.get("reviewed"):html=html.replace('>原稿</span>','>已校排版稿</span>')
    toc='<aside class="toc" aria-label="文章目录"><details open><summary>目录</summary><nav>'+contents_html+'</nav></details></aside>'
    def adjacent(i,label):
        if not 0<=i<len(group):return ""
        x=group[i]
        return f'<a href="{x["id"]}.html"><small>{label}</small><strong>{esc(x["title"])}</strong></a>'
    prevnext='<nav class="prevnext" aria-label="同课程资料">'+adjacent(pos-1,"同课程上一篇")+adjacent(pos+1,"同课程下一篇")+'</nav>'
    if chapter:
        def next_section(index,label):
            if not 0<=index<len(book):return ""
            other=book[index]
            return f'<a href="{other["slug"]}.html"><small>{label}</small><strong>{esc(other["name"])}</strong></a>'
        prevnext='<nav class="prevnext chapter-nav" aria-label="本份资料上下节">'+next_section(chapter["position"]-2,"上一节")+next_section(chapter["position"],"下一节")+'</nav>'
    script='<script type="module" src="../reader.js"></script>'
    page=back+'<div class="reading-grid"><article>'+top+html+download+prevnext+'</article>'+toc+'</div>'+script
    filename=chapter["slug"] if chapter else rid
    (docs/"articles"/(filename+".html")).write_text(document(title,page,base,True),encoding="utf8")

def make(docs,catalog,previews):
    rows=catalog["items"];groups=defaultdict(list);types=defaultdict(list);by_subject=defaultdict(list)
    discovery=load_discovery(rows)
    topics=defaultdict(list)
    for row in rows:
        for label in discovery.get(row["id"],{}).get("tags",[]):topics[label].append(row)
    for r in rows:
        groups[r["course"]].append(r);types[r["type"]].append(r);by_subject[subjects.get(r["course"],"应用与专题")].append(r)
    for c in groups:groups[c]=series_order(groups[c])
    data_path=Path(__file__).with_name("reader-meta.json");meta=json.loads(data_path.read_text(encoding="utf-8-sig")) if data_path.exists() else {}
    fragments={}
    fragment_path=Path(__file__).with_name("reading-content.json")
    if fragment_path.exists():fragments=json.loads(fragment_path.read_text(encoding="utf-8-sig"))
    (docs/"articles").mkdir(parents=True,exist_ok=True)
    (docs/"series").mkdir(parents=True,exist_ok=True)
    books=[]
    formats=sorted({r["format"] for r in rows})
    if any("transcription" in r or r.get("corrected") or r.get("typeset_source_sha256") for r in rows):formats.append("已校对的 LaTeX 排版稿")
    body=f'<section class="index-title"><h1>课程笔记</h1><p>{len(groups)} 门课程及专题 · {len(rows)} 份资料</p></section>'
    body+='<div class="filters"><label>搜索<input type="search" id="q" placeholder="搜索题名、课程和正文"></label>'
    for f,name,values in (("subject","学科",by_subject),("course","课程",groups),("type","资料类型",types),("fmt","格式或版本",formats),("tag","概念标签",topics)):
        body+=f'<label>{name}<select id="{f}"><option value="">全部</option>{opts(sorted(values))}</select></label>'
    body+='</div><p id="count" class="summary" aria-live="polite"></p><p id="empty" hidden>没有匹配的资料。</p>'
    for c,group in groups.items():
        body+=f'<section class="course"><h2>{esc(c)} <small>{len(group)} 份</small></h2>'
        for r in group:
            rid=r["id"];fmt=r["format"];subject=subjects.get(c,"应用与专题")
            editions=[fmt]
            if rid in previews and "PDF" not in editions:editions.append("PDF")
            if r.get("transcription") or r.get("corrected") or r.get("typeset_source_sha256"):
                editions.extend(v for v in ("PDF","已校对的 LaTeX 排版稿") if v not in editions)
            byline=" · ".join(filter(None,[r.get("term"),r["type"],"订正版" if r.get("corrected") else "已校排版" if r.get("transcription") else None]))
            key=" ".join([c,subject,r["title"],byline,*editions]).lower()
            tags=discovery.get(rid,{}).get("tags",[])
            body+=f'<div class="entry" data-id="{rid}" data-sha="{esc(r["sha256"])}" data-tags="{esc("|".join(tags))}" data-subject="{esc(subject)}" data-course="{esc(c)}" data-type="{esc(r["type"])}" data-fmt="{esc(fmt)}" data-editions="{esc("|".join(editions))}" data-search="{esc(key)}"><div><a class="title" href="articles/{rid}.html">{esc(r["title"])}</a><div class="sub">{esc(byline)}</div><div class="search-excerpt" hidden></div></div><small>{esc(fmt)} · {size(r["bytes"])}</small></div>'
            fragment=fragments.get(rid)
            expected=r.get("typeset_source_sha256") or r.get("transcription",{}).get("source",r["url"]).rsplit("/",1)[-1].split(".")[0]
            if fragment and fragment["source_sha256"]==expected and r.get("web_reading")=="files/"+fragment["digest"]+".html":
                import hashlib
                raw=(docs/r["web_reading"]).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=fragment["digest"]:raise ValueError("Web edition digest mismatch")
                fragment=dict(fragment,html=raw.decode("utf-8"))
            else:fragment=None
            chapters=book_sections(r,fragment,meta)
            article(docs,r,group,previews,meta,fragment,discovery.get(rid),chapters)
            if chapters:
                series_index(docs,r,chapters)
                books.append({"id":rid,"title":r["title"],"course":c,"mode":"html" if fragment else "pdf",
                              "chapters":[{k:v for k,v in ch.items() if k not in {"raw","html","headings"}} for ch in chapters]})
                for ch in chapters:
                    part={"html":ch["html"],"headings":ch["headings"]} if fragment else None
                    article(docs,r,group,previews,meta,part,discovery.get(rid),chapters,ch)
        body+='</section>'
    (docs/"index.html").write_text(document("课程笔记",body+'<script defer src="index.js"></script>'),encoding="utf8")
    courses='<section class="index-title"><h1>课程</h1></section>'
    for s in SUBJECTS:
        cs=[c for c in groups if subjects.get(c)==s]
        if cs:courses+=f'<section class="course"><h2>{esc(s)}</h2><div class="linkgrid">'+''.join(linkrow(c,homefilter(course=c),len(groups[c])) for c in cs)+'</div></section>'
    (docs/"courses.html").write_text(document("课程",courses),encoding="utf8")
    series='<section class="index-title"><h1>章节系列</h1><p>沿用原资料的章节、题目和日期标题，按原文顺序分节阅读。</p></section>'
    for course in groups:
        selected=[book for book in books if book["course"]==course]
        if selected:
            series+=f'<section class="course"><h2>{esc(course)}</h2><div class="linkgrid">'
            for book in selected:
                series+=f'<a class="listlink" href="series/{book["id"]}.html"><span>{esc(book["title"])}</span><small>{len(book["chapters"])} 节</small></a>'
            series+='</div></section>'
    (docs/"series.html").write_text(document("章节系列",series),encoding="utf8")
    (docs/"series-index.json").write_text(json.dumps(books,ensure_ascii=False,separators=(",",":")),encoding="utf8")
    terms=defaultdict(list)
    for row in rows:terms[row.get("term") or "学期未注明"].append(row)
    archive='<section class="index-title"><h1>资料归档</h1><p>按原资料注明的学期归档。</p></section>'
    for term,documents in terms.items():
        archive+=f'<section class="course"><h2>{esc(term)}</h2><div class="linkgrid">'
        for row in documents:
            archive+=f'<a class="listlink" href="articles/{row["id"]}.html"><span>{esc(row["title"])}</span><small>{esc(row["course"])} · {esc(row["type"])}</small></a>'
        archive+='</div></section>'
    (docs/"archive.html").write_text(document("资料归档",archive),encoding="utf8")
    origin="https://buguh.github.io/course-notes/"
    rss=ET.Element("rss",version="2.0");channel=ET.SubElement(rss,"channel")
    for key,value in (("title","BUGUH 学习笔记"),("link",origin),("description","课程笔记、作业与汇报的已校公开版本。"),("language","zh-CN"),("lastBuildDate",format_datetime(datetime.now(timezone.utc)))):
        ET.SubElement(channel,key).text=value
    atom="http://www.w3.org/2005/Atom";ET.register_namespace("atom",atom)
    ET.SubElement(channel,"{"+atom+"}link",href=origin+"feed.xml",rel="self",type="application/rss+xml")
    for row in rows:
        item=ET.SubElement(channel,"item")
        for key,value in (("title",row["title"]),("link",origin+"articles/"+row["id"]+".html"),("description"," · ".join(filter(None,(row["course"],row["type"],row.get("term")))))):
            ET.SubElement(item,key).text=value
        ET.SubElement(item,"guid",isPermaLink="false").text="urn:course-notes:"+row["id"]+":"+row["sha256"]
        for category in (row["course"],row["type"]):ET.SubElement(item,"category").text=category
    (docs/"feed.xml").write_bytes(ET.tostring(rss,encoding="utf-8",xml_declaration=True))
    categories='<section class="index-title"><h1>分类</h1></section>'
    for title,values,key in (("按资料类型",types,"type"),("按学科",by_subject,"subject")):
        categories+=f'<section class="course"><h2>{title}</h2><div class="linkgrid">'+''.join(linkrow(v,homefilter(**{key:v}),len(values[v])) for v in sorted(values))+'</div></section>'
    (docs/"categories.html").write_text(document("分类",categories),encoding="utf8")
    tag_index='<section class="index-title"><h1>概念标签</h1><p>按笔记和作业正文中出现的概念查找资料。</p></section><div class="linkgrid">'
    (docs/"tags").mkdir(exist_ok=True)
    for label,documents in sorted(topics.items()):
        tag_index+=linkrow(label,topic_url(label),len(documents))
        content=f'<a class="back" href="../tags.html">返回概念标签</a><section class="index-title"><h1>{esc(label)}</h1><p>{len(documents)} 份资料</p></section>'
        for row in documents:
            content+=f'<a class="listlink" href="../articles/{row["id"]}.html"><span>{esc(row["title"])}</span><small>{esc(row["course"])} · {esc(row["type"])}</small></a>'
        (docs/"tags"/(label+".html")).write_text(document(label,content,"../"),encoding="utf8")
    (docs/"tags.html").write_text(document("概念标签",tag_index+"</div>"),encoding="utf8")
    search_data=[dict(id=row["id"],sha256=row["sha256"],pdf_reader=not bool(row.get("web_reading")),
                     pages=discovery[row["id"]]["pages"])
                 for row in rows if row["id"] in discovery]
    (docs/"search-index.json").write_text(json.dumps(search_data,ensure_ascii=False,separators=(",",":")),encoding="utf8")

