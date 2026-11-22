"""Install the site's pinned reader on the same origin as the course materials."""
import base64
import hashlib
import io
from pathlib import PurePosixPath
import shutil
import tarfile
import urllib.request

URL="https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-6.5.438.tgz"
INTEGRITY="vg8Pw1x+AFKy4AMDvhuWl5cOYV8d698UoEANoFFhc79hqXDnZQqnOXoxw3HG907WHOg1JYOvLhP756boddFxpA=="

def install(docs):
    out=docs/"pdfjs"
    with urllib.request.urlopen(URL,timeout=75) as response:raw=response.read(32_000_000)
    if base64.b64encode(hashlib.sha512(raw).digest()).decode()!=INTEGRITY:raise ValueError("Reader download did not match pinned release")
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as archive:
        for m in archive:
            p=PurePosixPath(m.name)
            if not m.isfile() or p.is_absolute() or ".." in p.parts or p.parts[0]!="package":continue
            rel=PurePosixPath(*p.parts[1:])
            if str(rel) not in {"LICENSE","build/pdf.min.mjs","build/pdf.worker.min.mjs"} and rel.parts[0] not in {"cmaps","standard_fonts","wasm","iccs","image_decoders"}:continue
            path=out.joinpath(*rel.parts);path.parent.mkdir(parents=True,exist_ok=True)
            with archive.extractfile(m) as src,path.open("wb") as dest:shutil.copyfileobj(src,dest)
    assert (out/"build/pdf.worker.min.mjs").is_file() and (out/"build/pdf.min.mjs").is_file()

