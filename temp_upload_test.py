import pathlib
import urllib.error
import urllib.request
import mimetypes
import uuid

path = pathlib.Path("sample_resume.txt")
url = "http://127.0.0.1:8001/ranking"
boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
body = []

def add_field(name, value):
    body.extend([
        f"--{boundary}\r\n".encode("utf-8"),
        f"Content-Disposition: form-data; name=\"{name}\"\r\n\r\n".encode("utf-8"),
        value.encode("utf-8"),
        b"\r\n",
    ])


def add_file(fieldname, filepath):
    ctype = mimetypes.guess_type(str(filepath))[0] or "text/plain"
    body.extend([
        f"--{boundary}\r\n".encode("utf-8"),
        f"Content-Disposition: form-data; name=\"{fieldname}\"; filename=\"{filepath.name}\"\r\n".encode("utf-8"),
        f"Content-Type: {ctype}\r\n\r\n".encode("utf-8"),
        filepath.read_bytes(),
        b"\r\n",
    ])


add_field("user_level", "beginner")
add_field("target_pathways", "Analytics, Data Science")
add_field("top_n", "5")
add_file("resume_file", path)
body.append(f"--{boundary}--\r\n".encode("utf-8"))
data = b"".join(body)
req = urllib.request.Request(
    url,
    data=data,
    headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
    },
)

try:
    resp = urllib.request.urlopen(req, timeout=120)
    print("STATUS", resp.status)
    print(resp.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print("HTTP ERROR", e.code)
    print(e.read().decode("utf-8"))
except Exception:
    import traceback
    traceback.print_exc()
