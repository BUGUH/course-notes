"""Make review drafts of the site's public handwritten pages with an offline model."""
import base64, concurrent.futures, hashlib, io, json, os, re, secrets, shutil, subprocess, tempfile, time, urllib.request, zlib
from pathlib import Path
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SITE="https://buguh.github.io/course-notes/"
CWD=Path(__file__).resolve().parent
def download(url,dest,digest=None,*,skip_removed=False):
    response=subprocess.run(["curl","--fail","--location","--retry","3","--connect-timeout","15","--max-time","420","--silent","--show-error","--write-out","%{http_code}","-o",str(dest),url],stdout=subprocess.PIPE,text=True)
    if skip_removed and response.returncode==22 and response.stdout.strip()=="404":
        dest.unlink(missing_ok=True)
        return False
    response.check_returncode()
    if digest:
        h=hashlib.sha256()
        with dest.open("rb") as f:
            for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
        if h.hexdigest()!=digest:raise ValueError("Download digest mismatch")
    return True
def extract(shard):
    plan=json.loads((CWD/"transcription-pages.json").read_text())
    assigned=[r for r in plan if r["shard"]==shard]
    if not assigned:return
    pub=serialization.load_pem_public_key(base64.b64decode(os.environ["REVIEW_PUBLIC_KEY"]))
    key=secrets.token_bytes(32)
    wrapped=pub.encrypt(key,padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    print("REVIEW_KEY "+base64.b64encode(wrapped).decode(),flush=True)
    aes=AESGCM(key)
    def emit(r):
        iv=secrets.token_bytes(12)
        raw=zlib.compress(json.dumps(r,ensure_ascii=False).encode(),9)
        encrypted=iv+aes.encrypt(iv,raw,None)
        print("REVIEW_PAGE "+base64.b64encode(encrypted).decode(),flush=True)
    with tempfile.TemporaryDirectory() as name:
        work=Path(name);engine=work/"engine.tar.gz"
        engine_url="https://github.com/ggml-org/llama.cpp/releases/download/b12627/llama-b12627-bin-ubuntu-x64.tar.gz"
        models={"GLM-OCR-Q8_0.gguf":"45bc244a6446aff850521dc41f18bc8d7105ad5f0c2c8c28af04e7cc4f4d50b1","mmproj-GLM-OCR-Q8_0.gguf":"9c4b58e33e316ed142eb5dcb41abec3844d3e6e5dc361ffb782c3fa9d175141f"}
        todo=[(engine_url,engine,"7a00a31eb63c4a5411d74517e7967f386d8b7da077ea0a7bedacb89c664c28b2")]
        todo += [("https://huggingface.co/ggml-org/GLM-OCR-GGUF/resolve/main/"+n,work/n,d) for n,d in models.items()]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda x:download(*x),todo))
        subprocess.run(["tar","-xzf",str(engine),"-C",str(work)],check=True)
        exe=next(work.rglob("llama-server"))
        env=dict(os.environ,LD_LIBRARY_PATH=str(exe.parent)+":"+os.environ.get("LD_LIBRARY_PATH",""))
        cmd=[str(exe),"-m",str(work/"GLM-OCR-Q8_0.gguf"),"--mmproj",str(work/"mmproj-GLM-OCR-Q8_0.gguf"),"--host","127.0.0.1","--port","19384","--parallel","1","-c","6144","-ngl","0","--threads","4","--threads-batch","4","--no-webui","--no-warmup"]
        with (work/"engine.log").open("wb") as log:server=subprocess.Popen(cmd,env=env,stdout=log,stderr=log)
        try:
            for _ in range(120):
                if server.poll() is not None:raise RuntimeError("Engine startup failure "+str(server.returncode))
                try:
                    if json.load(urllib.request.urlopen("http://127.0.0.1:19384/health",timeout=1))["status"]=="ok":break
                except OSError:pass
                time.sleep(1)
            else:raise TimeoutError("Engine startup timeout")
            print("Engine ready",flush=True)
            for row in assigned:
                assert re.fullmatch(r"files/[0-9a-f]{64}\.pdf",row["url"])
                pdf=work/"public.pdf"
                if not download(SITE+row["url"],pdf,row["sha256"],skip_removed=True):
                    print("REVIEW_SKIP "+json.dumps({"id":row["id"],"pages":row["pages"],"reason":"public PDF removed (HTTP 404)"},separators=(",",":")),flush=True)
                    continue
                for pn in row["pages"]:
                    assert type(pn)==int and pn>=1
                    out=work/"page"
                    subprocess.run(["pdftoppm","-jpeg","-jpegopt","quality=92","-scale-to","1430","-singlefile","-f",str(pn),"-l",str(pn),str(pdf),str(out)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
                    image=base64.b64encode(out.with_suffix(".jpg").read_bytes()).decode()
                    parts=[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+image}},{"type":"text","text":"Text Recognition:"}]
                    body=json.dumps({"messages":[{"role":"user","content":parts}],"temperature":0,"repeat_penalty":1.08,"max_tokens":2300}).encode()
                    response=None
                    for retry in range(2):
                        try:
                            rq=urllib.request.Request("http://127.0.0.1:19384/v1/chat/completions",data=body,headers={"Content-Type":"application/json"})
                            with urllib.request.urlopen(rq,timeout=220) as c:response=json.load(c)
                            break
                        except (OSError,ValueError):time.sleep(1)
                    if response is None:raise RuntimeError("Recognition did not complete")
                    msg=response["choices"][0];text=msg["message"]["content"] or ""
                    repeated=bool(re.search(r"(.{8,60})\1{5,}",text,re.S))
                    record=dict(id=row["id"],page=pn,text=text,ok=bool(text.strip()) and not repeated and msg["finish_reason"]!="length",repeat=repeated,finish=msg["finish_reason"],source_sha256=row["sha256"],model="GLM-OCR-Q8_0")
                    emit(record)
                print("Finished public document",row["id"],"pages",len(row["pages"]),flush=True)
        finally:
            server.terminate();server.wait(timeout=20)
if __name__=="__main__":extract(int(os.environ["SHARD"]))

