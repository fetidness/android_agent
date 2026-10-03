# Reteta: git + SSH pe device (reconstructie de la zero)

Se foloseste DOAR daca `files/toolchain/git/bin/git` lipseste (curatare completa / uninstall).
Se construieste in `files/tmp` (NICIODATA pe /sdcard - e noexec), prin unealta `bg` (joburi lungi).
Mediul de compilare: `toolchain action=env` (CC/CXX/CFLAGS/LDFLAGS/PATH);
`clang`/`clang++` isi completeaza singure flag-urile lipsa.

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

## 3. git (config dovedit in build_git.sh din sesiunea originala)
    cd git-2.47.1
    make -j4 NO_GETTEXT=1 NO_TCLTK=1 NO_PYTHON=1 NO_PERL=1 NO_RUST=1 NO_EXPAT=1 NO_ICONV=1 \
      NO_OPENSSL=0 NO_CURL=1 NO_INSTALL_HARDLINKS=1 NO_MMAP=1 NO_IPV6=1 \
      CURL_LDFLAGS="-lcurl -lnghttp2 -lssh2 -lz -lssl -lcrypto" LIBSSH2_LIBRARY="-lssh2" \
      prefix=$B/prefix all && make prefix=$B/prefix install

## 4. dropbear: clientul SSH (dbclient) + convertorul de chei
    cd dropbear-2024.86 && ./configure --prefix=$B/prefix && make dropbearconvert dbclient
    cp dbclient dropbearconvert $B/prefix/bin/

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
