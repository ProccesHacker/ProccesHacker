import argparse
import ast
import dis
import marshal
import os
import re
import sys
import zipfile
from types import CodeType


abc = "abcdefghijklmnopqrstuvwxyz0123456789"


class Deob:
    def __init__(self, path, key=49348):
        self.path = path
        self.key = key

    def run(self):
        data, name = self.read(self.path)
        code = self.unpack(data, name)
        out = self.walk(code)
        if out is None:
            text = self.text(data)
            out = self.from_text(text)
        if out is None:
            raise SystemExit("nothing found")
        return self.clean(out)

    def read(self, path):
        if os.path.isdir(path):
            for x in ("src/_run.py", "_run.py", "launch.py"):
                p = os.path.join(path, x)
                if os.path.isfile(p):
                    return open(p, "rb").read(), p
            for root, _, files in os.walk(path):
                for file in files:
                    if file.endswith((".py", ".pyc")):
                        p = os.path.join(root, file)
                        return open(p, "rb").read(), p
            raise SystemExit("no python files")
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                pick = None
                for x in ("src/_run.py", "_run.py", "launch.py"):
                    if x in names:
                        pick = x
                        break
                if pick is None:
                    for x in names:
                        if x.endswith((".py", ".pyc")):
                            pick = x
                            break
                if pick is None:
                    raise SystemExit("no python files")
                return z.read(pick), pick
        return open(path, "rb").read(), path

    def text(self, data):
        for enc in ("utf-8", "utf-16", "cp1251", "latin1"):
            try:
                return data.decode(enc)
            except Exception:
                pass
        return data.decode("utf-8", "ignore")

    def unpack(self, data, name=""):
        if name.endswith(".pyc") or data[:4] in (b"\xa7\r\r\n", b"\x42\x0d\x0d\x0a"):
            for i in (16, 12, 8, 0):
                try:
                    return marshal.loads(data[i:])
                except Exception:
                    pass
        text = self.text(data)
        for b in self.bytes_from_ast(text):
            try:
                return marshal.loads(b)
            except Exception:
                pass
        for b in self.bytes_from_regex(text):
            try:
                return marshal.loads(b)
            except Exception:
                pass
        return None

    def bytes_from_ast(self, text):
        try:
            tree = ast.parse(text)
        except Exception:
            return []
        arr = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            ok = False
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "loads":
                ok = True
            if isinstance(f, ast.Name) and f.id == "loads":
                ok = True
            if not ok:
                continue
            try:
                v = ast.literal_eval(node.args[0])
            except Exception:
                continue
            if isinstance(v, bytes):
                arr.append(v)
        return arr

    def bytes_from_regex(self, text):
        arr = []
        for m in re.finditer(r"loads\s*\(\s*(b(['\"]).*?\2)\s*\)", text, re.S):
            try:
                v = ast.literal_eval(m.group(1))
            except Exception:
                continue
            if isinstance(v, bytes):
                arr.append(v)
        return arr

    def walk(self, code):
        if code is None:
            return None
        items = []
        self.collect(code, items)
        best = None
        bestn = -999
        for s in items:
            for k in self.keys(items):
                try:
                    d = self.dec(s, k)
                except Exception:
                    continue
                n = self.score(d)
                if n > bestn:
                    best = d
                    bestn = n
        if best is not None and bestn > 1:
            return best
        return None

    def collect(self, code, arr):
        if not isinstance(code, CodeType):
            return
        for c in code.co_consts:
            if isinstance(c, CodeType):
                self.collect(c, arr)
            elif isinstance(c, str) and len(c) > 3:
                arr.append(c)

    def keys(self, items):
        got = {self.key}
        for s in items:
            for n in re.findall(r"key\s*=\s*(-?\d+)", s):
                try:
                    got.add(int(n))
                except Exception:
                    pass
        return list(got)

    def dec(self, text, key):
        tmp = []
        for ch in text:
            if ch == "ζ":
                tmp.append("\n")
            else:
                o = ord(ch) - key
                if o < 0 or o > 0x10ffff:
                    return ""
                tmp.append(chr(o))
        tmp = "".join(tmp)
        res = []
        for ch in tmp:
            if ch in abc:
                res.append(abc[(abc.index(ch) + 1) % len(abc)])
            else:
                res.append(ch)
        return "".join(res)

    def from_text(self, text):
        q = re.findall(r"script\s*=\s*r?(['\"]{3})(.*?)\1", text, re.S)
        if not q:
            q = re.findall(r"script\s*=\s*r?(['\"])(.*?)\1", text, re.S)
        best = None
        bestn = -999
        for _, s in q:
            for k in (self.key,):
                d = self.dec(s, k)
                n = self.score(d)
                if n > bestn:
                    best = d
                    bestn = n
        if best is not None and bestn > 1:
            return best
        return None

    def score(self, s):
        if not s:
            return -999
        n = 0
        z = s[:5000]
        words = ("import ", "from ", "def ", "class ", "print(", "if ", "for ", "while ", "=", "\n")
        for w in words:
            n += z.count(w)
        bad = sum(1 for c in z if ord(c) < 9 or (13 < ord(c) < 32))
        high = sum(1 for c in z if ord(c) > 127 and c not in "абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")
        return n - bad * 5 - high

    def clean(self, s):
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        return s.rstrip() + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("-k", "--key", type=int, default=49348)
    a = p.parse_args()
    out = Deob(a.input, a.key).run()
    if a.output:
        with open(a.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
