#!/usr/bin/env python3
"""adbkey_pub.py - fisierul .pub in formatul adb dintr-o cheie privata PEM (fara parola).

Formatul cerut de adbd (AndroidKey): "QAAAA" + base64( >I 7 + "ssh-rsa" + mpint(e) + mpint(n) )
+ " adbkey@agent". Blob-ul incepe mereu cu 00 00 00 07 (lungimea sirului "ssh-rsa").
"""
import sys, base64, struct, subprocess, re

def grab(txt, name):
    out, on = [], False
    for line in txt.splitlines():
        if line.startswith(name + ":"):
            on = True
            rest = line.split(":", 1)[1].strip()
            if rest:
                out.append(rest)
            continue
        if on:
            if not line.startswith(" "):
                break
            out.append(line.strip())
    raw = "".join(out).replace(":", "").replace(" ", "")
    m = re.match(r"^([0-9a-fA-F]+)", raw)          # publicExponent are si "(0x10001)"
    return int(m.group(1), 16)

def mpint(i):
    b = i.to_bytes((i.bit_length() + 7) // 8, "big")
    if b[0] & 0x80:
        b = b"\x00" + b
    return struct.pack(">I", len(b)) + b

def main(priv, pub):
    txt = subprocess.run(["openssl", "rsa", "-in", priv, "-noout", "-text"],
                         capture_output=True, text=True).stdout
    n, e = grab(txt, "modulus"), grab(txt, "publicExponent")
    blob = struct.pack(">I", 7) + b"ssh-rsa" + mpint(e) + mpint(n)
    open(pub, "w").write("QAAAA" + base64.b64encode(blob).decode() + " adbkey@agent\n")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
