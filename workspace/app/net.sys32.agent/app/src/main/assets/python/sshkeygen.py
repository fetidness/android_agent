"""sshkeygen.py - genera chei SSH ed25519 in PYTHON PUR (fara cryptography).

Produce:
  - cheia privata in format OpenSSH (-----BEGIN OPENSSH PRIVATE KEY-----), cu comentariu
  - cheia publica in format OpenSSH (ssh-ed25519 AAAA... comment)
Nu are nevoie de pachete externe: doar hashlib/os/base64 (stdlib).

Implementare RFC 8032 (Ed25519): coada Edwards twisted, SHA-512, scalarmult.
"""
import os, hashlib, base64, struct

# --- Ed25519 in python pur (RFC 8032) ---
_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)

def _sha512(s):
    return hashlib.sha512(s).digest()

def _modp_inv(x):
    return pow(x, _P - 2, _P)

def _xrecover(y):
    xx = (y * y - 1) * _modp_inv(_D * y * y + 1)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x

_By = (4 * _modp_inv(5)) % _P
_Bx = _xrecover(_By)
_B = (_Bx % _P, _By % _P, 1, (_Bx * _By) % _P)

def _edwards_add(P1, P2):
    x1, y1, z1, t1 = P1
    x2, y2, z2, t2 = P2
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = t1 * 2 * _D * t2 % _P
    dd = z1 * 2 * z2 % _P
    e = b - a; f = dd - c; g = dd + c; h = b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)

def _scalarmult(P1, e):
    if e == 0:
        return (0, 1, 1, 0)
    Q = _scalarmult(P1, e // 2)
    Q = _edwards_add(Q, Q)
    if e & 1:
        Q = _edwards_add(Q, P1)
    return Q

def _encodepoint(Pt):
    x, y, z, t = Pt
    zi = _modp_inv(z)
    x = x * zi % _P
    y = y * zi % _P
    bits = [(y >> i) & 1 for i in range(255)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(32))

def _bit(h, i):
    return (h[i // 8] >> (i % 8)) & 1

def _clamp(h):
    a = 2 ** (254) + sum(2 ** i * _bit(h, i) for i in range(3, 254))
    return a

def ed25519_public(seed):
    """seed = 32 bytes -> cheia publica 32 bytes."""
    h = _sha512(seed)
    a = _clamp(h[:32])
    A = _scalarmult(_B, a)
    return _encodepoint(A)

def ed25519_sign(seed, msg):
    """Semnatura Ed25519 (RFC 8032) - util pentru teste."""
    h = _sha512(seed)
    a = _clamp(h[:32])
    prefix = h[32:]
    A = _encodepoint(_scalarmult(_B, a))
    r = int.from_bytes(_sha512(prefix + msg), "little") % _L
    R = _encodepoint(_scalarmult(_B, r))
    k = int.from_bytes(_sha512(R + A + msg), "little") % _L
    S = (r + k * a) % _L
    return R + S.to_bytes(32, "little")

# --- format OpenSSH ---
def _ssh_string(b):
    return struct.pack(">I", len(b)) + b

def public_openssh(pub, comment=""):
    blob = _ssh_string(b"ssh-ed25519") + _ssh_string(pub)
    return "ssh-ed25519 " + base64.b64encode(blob).decode() + (" " + comment if comment else "")

def private_openssh(seed, pub, comment=""):
    """Cheia privata in format openssh-key-v1 (necriptata)."""
    check = struct.unpack(">I", os.urandom(4))[0]
    priv_blob = (struct.pack(">II", check, check)
                 + _ssh_string(b"ssh-ed25519") + _ssh_string(pub)
                 + _ssh_string(seed + pub)          # 64 bytes: seed || pub
                 + _ssh_string(comment.encode()))
    # padding la multiplu de 8
    pad = 8 - (len(priv_blob) % 8)
    if pad != 8:
        priv_blob += bytes(range(1, pad + 1))
    pub_blob = _ssh_string(b"ssh-ed25519") + _ssh_string(pub)
    blob = (b"openssh-key-v1\x00" + _ssh_string(b"none") + _ssh_string(b"none")
            + _ssh_string(b"") + struct.pack(">I", 1)
            + _ssh_string(pub_blob)
            + _ssh_string(priv_blob))
    b64 = base64.b64encode(blob).decode()
    lines = [b64[i:i + 70] for i in range(0, len(b64), 70)]
    return ("-----BEGIN OPENSSH PRIVATE KEY-----\n" + "\n".join(lines)
            + "\n-----END OPENSSH PRIVATE KEY-----\n")

def generate(comment="agent@device"):
    """Genereaza o pereche noua. Returneaza (seed, pub, priv_openssh, pub_openssh)."""
    seed = os.urandom(32)
    pub = ed25519_public(seed)
    return seed, pub, private_openssh(seed, pub, comment), public_openssh(pub, comment)
