# Reparatii toolchain Android (SM-A366B) - sesiune 2026-09-23

## Context

Prefix toolchain: /data/local/tmp/tpm/usr (1.3 GB, client openssh inclus)
Instalat prin repo Termux, dar mutat din /data/data/com.termux in /data/local/tmp/tpm.

## Incident: sed pe binare ELF

Simptom: dupa un sed -i global de inlocuire prefix in tot prefixul,
ls/cat/head/python/clang au inceput sa dea:

    "libcrypto.so.3" has invalid shdr offset/size: 5203808/1664

Cauza: grep -I NU a filtrat corect fisierele binare, deci sed a scris
in interiorul secțiunilor ELF si a corupt 10 fisiere:
  libcrypto.so.3, libxml2.so.16.1.4, libncursesw.so.6.5,
  libreadline.so.8.3, libsqlite3.so.3.53.4,
  libgio-2.0 / libgirepository-2.0 / libglib-2.0 .so,
  2 module numpy

Efect dublu: shell-ul are PATH in toolchain, deci ORICE comanda de baza
(ls, cat, head) a devenit inutilizabila.

## Reparatie fara root, fara rebuild

1. Descarcat pachetele .deb aarch64 de pe packages.termux.dev:
   openssl, libxml2, ncurses, readline, libsqlite, glib
2. Extras din .deb cu Python (format ar + lzma): se citeste headerul ar de
   60 bytes, se gaseste data.tar.xz, lzma.decompress, apoi tarfile pe BytesIO
3. Copiat .so-urile originale peste cele corupte
4. Ocolit PATH rupt: folosit /system/bin/ls etc. cu cai absolute

## Reparatie RUNPATH (rust)

rustc esua cu "library librustc_driver-*.so not found" desi libraria exista.
Cauza: libs din $PREFIX/lib/rustlib/aarch64-linux-android/lib aveau
RUNPATH vechi catre /data/data/com.termux/files/usr/lib si nu erau
prinse de toolchain.fix.

Fix:
  patchelf --set-rpath "$PREFIX/lib/rustlib/aarch64-linux-android/lib:$PREFIX/lib"
  pe librustc_driver-*.so SI pe binarul rustc

## Retentie

NICIODATA sed -i pe fisiere .so/.a/binar. Filtrarea cu grep -I NU e
suficienta. Dupa orice sed global: re-testeaza imediat
python3 --version, clang --version, ls.
