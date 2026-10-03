# Reteta: git + SSH pe device (reconstructie de la zero)

Se foloseste DACA `files/toolchain/git/bin/git` lipseste. Rulat prin `python`/`bg` (procesul aplicatiei).
Mediu: `toolchain action=env`.
RETETA VERIFICATA integral pe device (2026-10-03): build -> install -> HTTPS -> SSH = OK.

## REGULI CARE NU SE NEGOCIAZA (fiecare a costat pasi intr-o sesiune reala)

1. **Toate caile in filesDir** (`files/tmp/...`): pe `/sdcard` NU se pot crea symlink-uri (FUSE) si
   nu se executa nimic (noexec) - `make install`/cmake cad acolo.
2. **git NU se configureaza** (`./configure` cere 3 cache-uri pentru teste runtime de cross-compilare).
   Se compileaza DIRECT cu `make`, flag-urile fiind variabile de make.
3. **`CC`/`AR`/`RANLIB` explicite**: altfel make foloseste `cc` -> shim-ul `cc-rust` ->
   "cc-rust: exec clang: No such file or directory".
4. **Flag-uri COMPLETE in CFLAGS** (`--target=aarch64-linux-android<api> --sysroot=<TC>/sysroot
   -resource-dir=<TC>/lib/clang/21`): fara `--target`, lansatorul clang adauga singur setul lui de
   `-I`, inclusiv `<TC>/pyinc` -> git isi ia headerele Python ("object.h: unknown type name
   'Py_ssize_t'").
5. **NU pune `NO_CURL`**: in make, `NO_CURL=0` inseamna "este definit" -> git fara helper-ele curl ->
   "git: 'remote-https' is not a git command". Foloseste `CURL_CONFIG` catre scriptul fals + `CURL_LDFLAGS`.
6. **`NO_PTHREADS=YesPlease`**: Bionic nu are `pthread_setcancelstate` / `pthread_cancel`.
7. **Dezarhivare cu Python** (toybox `tar` nu are xz). NU sterge arhivele pana nu confirmi directoarele.
8. **`make install` cu ACELEASI variabile** (altfel recompileaza cu `cc` si cade).
9. In locul durabil (`files/toolchain/git/`) intra si **`libexec/git-core/*`** (helper-ele
   `git-remote-https`! fara ele clone HTTPS esueaza) + `share/git-core/templates`.

## 1. Surse (descarca in files/tmp/gitbuild)
- git:      https://mirrors.edge.kernel.org/pub/software/scm/git/git-2.47.1.tar.xz
- libssh2:  https://www.libssh2.org/download/libssh2-1.11.1.tar.gz
- nghttp2:  https://github.com/nghttp2/nghttp2/releases/download/v1.64.0/nghttp2-1.64.0.tar.gz
- dropbear: https://matt.ucc.asn.au/dropbear/releases/dropbear-2024.86.tar.bz2

## 2. nghttp2 (pentru https) si libssh2 (pentru ssh), prefix comun
    cmake -S nghttp2-1.64.0 -B b_ng -G Ninja -DCMAKE_INSTALL_PREFIX=$B/prefix \
          -DBUILD_STATIC_LIBS=OFF -DENABLE_LIB_ONLY=ON && ninja -C b_ng install
    cmake -S libssh2-1.11.1 -B b_ss -G Ninja -DCMAKE_INSTALL_PREFIX=$B/prefix \
          -DCRYPTO_BACKEND=OpenSSL -DBUILD_SHARED_LIBS=ON -DBUILD_STATIC_LIBS=OFF \
          -DCMAKE_PREFIX_PATH=$TC/deps && ninja -C b_ss install

### 2b. Shim MD5 (libcurl.a cere MD5_Init/Update/Final, dar libcrypto.a e construit fara MD5)
    files/tmp/md5shim.c: implementeaza MD5_Init/Update/Final peste EVP (EVP_md5) si se compileaza
    cu clang-ul nostru; se adauga la link prin variabila `LIBS=<...>/md5shim.o`.
    Fara el: "ld.lld: error: undefined symbol: MD5_Init" la linkarea git-remote-http.

## 3. git: DIRECT cu make (NU ./configure)
    make -j4 -C src/git-2.47.1 \
      CC=$F/tmp/clang AR=$F/tmp/ar RANLIB=$F/tmp/ranlib \
      NO_GETTEXT=1 NO_TCLTK=1 NO_PYTHON=1 NO_PERL=1 NO_RUST=1 NO_EXPAT=1 NO_ICONV=1 \
      NO_INSTALL_HARDLINKS=1 NO_MMAP=1 NO_PTHREADS=YesPlease \
      CFLAGS="-O2 -fPIC --target=aarch64-linux-android<api> --sysroot=$TC/sysroot \
              -resource-dir=$TC/lib/clang/21 -I$TC/deps/include -I$INS/include" \
      LDFLAGS="--target=aarch64-linux-android<api> --sysroot=$TC/sysroot -L$INS/lib -L$TC/deps/lib \
               -L$TC/lib/clang/21/lib/linux -Wl,-rpath,$INS/lib" \
      CURL_CONFIG="sh $F/tmp/curl-config" CURL_CFLAGS="-I$TC/deps/include" \
      CURL_LDFLAGS="-L$INS/lib -lcurl -lnghttp2 -lssh2 -lssl -lcrypto -lz -lzstd" \
      CURL_LIBCURL="-lcurl" LIBSSH2_LIBRARY="-lssh2" \
      prefix=$INS gitexecdir=$INS/libexec/git-core all
    # apoi ACELASI comando cu "install" in loc de "all" (aceleasi variabile!)

## 4. dropbear: clientul SSH (dbclient) + convertorul de chei
    cd dropbear-2024.86
    sh ./configure --prefix=$INS --disable-zlib --disable-syslog
    # Android nu are crypt(): fara linia urmatoare build-ul cade cu
    #   "DROPBEAR_SVR_PASSWORD_AUTH requires `crypt()'" (libtomcrypt/sysoptions.h)
    echo '#define DROPBEAR_SVR_PASSWORD_AUTH 0' >> localoptions.h
    # Bionic nu are getpass(): pune la inceputul src/cli-auth.c o implementare proprie
    #   (citeste de la /dev/tty) + "#define getpass getpass_shim"
    make -j4 dbclient dropbearconvert && cp dbclient dropbearconvert $INS/bin/
    # download: matt.ucc.asn.au da 403 la urllib fara User-Agent -> foloseste mirror-ul GitHub
    # (mkj/dropbear/releases) sau pune un UA de curl.
    # IMPORTANT: copiaza binarele in locul durabil DUPA acest pas (sau re-copiaza la final).

## 5. Esentialul in locul DURABIL (asta face si _ensure_git_toolchain() automat)
    mkdir -p files/toolchain/git/bin files/toolchain/git/lib
    cp $B/prefix/bin/git $B/prefix/bin/dbclient dropbearconvert files/toolchain/git/bin/
    cp $B/prefix/lib/*.so* files/toolchain/git/lib/

## 6. Cheia SSH (NU se pune NICIODATA in APK / assets / git!)
    # cheia operatorului (format OpenSSH) -> files/home/.ssh/id_ed25519_github   (chmod 600)
    files/toolchain/git/bin/dropbearconvert openssh dropbear \
        files/home/.ssh/id_ed25519_github files/home/.ssh/id_ed25519_github.db
    chmod 600 files/home/.ssh/id_ed25519_github.db
    # known_hosts cu cheile GitHub (verifica fingerprint-ul ed25519:
    #   SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU)
    ssh-keyscan -t rsa,ecdsa,ed25519 github.com ssh.github.com >> files/home/.ssh/known_hosts

## 7. Lansatorul se reface SINGUR
`_ensure_git_launcher()` (toolchain.py) scrie la fiecare pornire `files/tmp/git.sh` + symlink
`files/tmp/git`, cu `GIT_SSH_COMMAND` catre dbclient + cheia `.db` (nu se face manual).

## Verificare finala (toate rc=0)
    files/tmp/git --version
    files/tmp/git ls-remote git@github.com:<user>/<repo>.git
    files/tmp/git clone --depth 1 https://github.com/octocat/Hello-World.git
