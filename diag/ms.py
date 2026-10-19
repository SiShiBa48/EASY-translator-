import json, urllib.request, urllib.error
def req(url, data=None, headers=None, method=None):
    r = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 Edg/130.0", **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return -1, repr(e)
s, tok = req("https://edge.microsoft.com/translate/auth")
print("auth:", s, tok[:60])
body = json.dumps([{"Text": "Good morning"}]).encode()
for host in ("api-edge.cognitive.microsofttranslator.com", "api.cognitive.microsofttranslator.com"):
    for q in ("api-version=3.0&to=zh-Hans", "from=&to=zh-Hans&api-version=3.0&includeSentenceLength=true"):
        s2, b = req(f"https://{host}/translate?{q}", body, {"Authorization": "Bearer " + tok.strip(), "Content-Type": "application/json"})
        print(host, q, "->", s2, b[:200])
