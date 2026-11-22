"""Restore only screened public documents and render the static Pages site."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile

from render_pages import make

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT/"docs"
CAT = json.loads((ROOT/"catalog.json").read_text(encoding="utf-8"))
BASE = "https://github.com/BUGUH/course-notes/releases/download/"
def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()

def restore(pack):
    url = BASE + CAT["tag"] + "/" + pack["name"]
    with tempfile.TemporaryDirectory() as folder:
        archive = Path(folder)/"pack.zip"
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=180) as source, archive.open("wb") as out:
                    shutil.copyfileobj(source,out)
                if sha(archive) != pack["sha"]: raise ValueError("Bundle digest mismatch")
                break
            except OSError:
                if attempt==3: raise
                time.sleep(2**attempt)
        with zipfile.ZipFile(archive) as z:
            if set(z.namelist())!=set(pack["members"]): raise ValueError("Unexpected bundle contents")
            for name, expected in pack["members"].items():
                if not re.fullmatch(r"[0-9a-f]{64}\.(pdf|zip|tex|goodnotes)",name): raise ValueError("Invalid asset name")
                dst=DOCS/"files"/name
                with z.open(name) as src,dst.open("wb") as out: shutil.copyfileobj(src,out)
                if sha(dst)!=expected: raise ValueError("Asset digest mismatch")

def compile_preview(row, folder):
    input_file = DOCS/row["url"]
    if not input_file.is_file(): return None
    job = Path(folder)/row["id"]
    job.mkdir()
    if input_file.suffix == ".zip":
        with zipfile.ZipFile(input_file) as z:
            seen=set()
            for member in z.infolist():
                key=PurePosixPath(member.filename)
                if key.is_absolute() or ".." in key.parts or "\\" in member.filename or key in seen:
                    raise ValueError("Invalid source path")
                seen.add(key)
                z.extract(member,job)
        main = (job/row["main"]).resolve()
    else:
        main = job/"main.tex"
        shutil.copyfile(input_file,main)
    if not main.is_relative_to(job) or not main.is_file(): return None
    commands=[]
    if shutil.which("tectonic"):
        commands.append(["tectonic","-X","compile","--untrusted","--keep-logs",main.name])
    if shutil.which("latexmk"):
        commands.append(["latexmk","-xelatex","-no-shell-escape","-interaction=nonstopmode","-halt-on-error",main.name])
    pdf=main.with_suffix(".pdf")
    for cmd in commands:
        try:
            result=subprocess.run(cmd,cwd=main.parent,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,timeout=140,env=dict(os.environ,openin_any="p",openout_any="p"))
        except (OSError,subprocess.TimeoutExpired):
            continue
        if result.returncode==0 and pdf.is_file():break
    else:
        print("Source download available, local compiler required:",row["id"],flush=True)
        return None
    if pdf.stat().st_size > 32_000_000:return None
    info = subprocess.run(["pdfinfo",str(pdf)],capture_output=True,text=True,check=True)
    pages = re.search(r"(?m)^Pages:\s+(\d+)",info.stdout)
    if not pages or row["pages"] and int(pages[1])!=row["pages"]:
        print("Preview omitted due to page count:",row["id"],flush=True)
        return None
    log = main.with_suffix(".log").read_text(encoding="utf-8",errors="replace")
    if row["id"] in {"ddc2bf87293bc0a505e9","752869f83016bb29fce4"}:
        log="\n".join(line for line in log.splitlines() if not ("Missing character:" in line and "in font nullfont!" in line))
    if re.search(r"Missing character:|There were undefined references|Citation .* undefined",log):
        print("Preview omitted due to typesetting warnings:",row["id"],flush=True)
        return None
    name="previews/"+row["id"]+".pdf"
    shutil.copyfile(pdf,DOCS/name)
    return name

def reference_previews(rows, folder, target):
    seed = os.environ.get("PREVIEW_SEED", "")
    if seed and not re.fullmatch(r"reading-copies-[0-9a-f]{16}\.zip",seed):
        raise ValueError("Invalid reference bundle")
    archive = None
    fallback = Path(folder)/"reference.zip"
    for row in rows:
        if row["id"] in target: continue
        label=row["id"]+".pdf"
        rel="previews/"+label
        dst=DOCS/rel
        expected=row["preview_sha256"]
        try:
            uri="https://buguh.github.io/course-notes/"+rel
            with urllib.request.urlopen(uri,timeout=10) as src,dst.open("wb") as out:
                shutil.copyfileobj(src,out)
            if sha(dst)==expected:
                target[row["id"]]=rel
                continue
        except OSError:
            pass
        if dst.exists():dst.unlink()
        if not seed: continue
        if archive is None:
            with urllib.request.urlopen(BASE+CAT["tag"]+"/"+seed,timeout=120) as src,fallback.open("wb") as out:
                shutil.copyfileobj(src,out)
            archive=zipfile.ZipFile(fallback)
        with archive.open(label) as src,dst.open("wb") as out:shutil.copyfileobj(src,out)
        if sha(dst)!=expected:raise ValueError("Reference digest mismatch "+label)
        target[row["id"]]=rel
    if archive: archive.close()

def run():
    for directory in ("files","previews"):
        (DOCS/directory).mkdir(exist_ok=True,parents=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(restore,CAT["packs"]))
    previews = {r["id"]:r["existing_preview"] for r in CAT["items"] if r.get("existing_preview")}
    tasks = [r for r in CAT["items"] if r["format"]=="LaTeX" and r["id"] not in previews]
    if shutil.which("latexmk") and tasks:
        with tempfile.TemporaryDirectory() as folder, concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            for r, path in zip(tasks,pool.map(lambda r:compile_preview(r,folder),tasks)):
                if path: previews[r["id"]]=path
    with tempfile.TemporaryDirectory() as folder:
        reference_previews(tasks,folder,previews)
    make(DOCS,CAT,previews)
    for row in CAT["items"]:
        if not row["url"].startswith("https://") and (not (DOCS/row["url"]).is_file() or sha(DOCS/row["url"])!=row["sha256"]):
            raise ValueError("Broken download "+row["id"])
    total=sum(f.stat().st_size for f in DOCS.rglob("*") if f.is_file())
    if total>=1_000_000_000: raise RuntimeError("Published site exceeds Pages capacity")
    summary=dict(items=len(CAT["items"]),archive_bytes=sum(r["bytes"] for r in CAT["items"]),site_bytes=total,previews=previews)
    (DOCS/"publication.json").write_text(json.dumps(summary,ensure_ascii=False),encoding="utf-8")
    print(f"Published {len(CAT['items'])} items, {len(previews)} additional PDF readers, {total} bytes")
if __name__=="__main__": run()

