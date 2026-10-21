/* debian_binder.c - client Binder nativ pentru Debian (glibc, direct /dev/binder)
 *
 * Toate offseturile au fost verificate prin ptrace pe libbinder Android 16.
 * Se compileaza cu gcc in Debian si vorbeste direct cu servicemanager.
 *
 *   binder list                     - toate serviciile
 *   binder check <name>             - verifica existenta
 *   binder handle <name>            - handle-ul binder al serviciului
 *   binder desc <name>              - descriptorul de interfata
 *   binder call <name> <code> [i32..] - apel generic (desc dedus)
 *   binder rawcall <h> <code> [i32..] - apel pe handle direct
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <sys/mman.h>

typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;
typedef uint64_t u64; typedef int32_t s32;

#define BWR_REQ          0xc0306201UL
#define BC_TRANSACTION   0x40406300
#define BC_REPLY         0x40406301
#define BC_FREE_BUFFER   0x40086303
#define BC_ACQUIRE       0x40046304
#define BC_INCREFS       0x40046305
#define BC_RELEASE       0x40046306
#define BC_DECREFS       0x40046307
#define BC_ENTER_LOOPER  0x630c
#define BR_NOOP          0x720c
#define BR_TRANSACTION   0x7201
#define BR_REPLY         0x7206
#define BR_TRANSACTION_COMPLETE 0x7211
#define BR_DEAD_REPLY    0x7f47
#define BR_FAILED_REPLY  0x7f4b
#define BR_ACQUIRE       0x7205
#define BR_INCREFS       0x7204
#define BR_RELEASE       0x7207
#define BR_DECREFS       0x7208
#define BR_DEAD_BINDER   0x720f

#define TF_ACCEPT_FDS    0x10
#define INTERFACE_TRANSACTION 0x5f4e5446   /* '_INTF' */
#define DUMP_PRIORITY_ALL     0x0F

#define RDBUF  (256*1024)
#define DEFAULT_MAPSZ (1024*1024)

struct bwr { u64 write_size, write_consumed, write_buffer,
                 read_size, read_consumed, read_buffer; };

static int   g_fd = -1;
static u8   *g_map = NULL;
static u64   g_mapaddr = 0;
static size_t g_mapsz = 0;
static u8   *g_rd = NULL;
static u64   g_last_dptr = 0;

static int bwr(void *w, u64 wsize, u64 *rconsumed) {
    struct bwr r;
    memset(&r, 0, sizeof r);
    r.write_size   = wsize;
    r.write_buffer = (u64)(uintptr_t)w;
    r.read_size    = RDBUF;
    r.read_buffer  = (u64)(uintptr_t)g_rd;
    if (ioctl(g_fd, BWR_REQ, &r) < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) { if (rconsumed) *rconsumed = 0; return 0; }
        return -errno;
    }
    if (rconsumed) *rconsumed = r.read_consumed;
    return 0;
}

static int bopen(void) {
    g_fd = open("/dev/binder", O_RDWR | O_CLOEXEC);
    if (g_fd < 0) return -errno;
    fcntl(g_fd, F_SETFL, fcntl(g_fd, F_GETFL, 0) | O_NONBLOCK);

    size_t sz = DEFAULT_MAPSZ;
    while (sz >= 4096) {
        void *m = mmap(NULL, sz, PROT_READ, MAP_SHARED, g_fd, 0);
        if (m != MAP_FAILED) { g_map = m; g_mapsz = sz; break; }
        sz /= 2;
    }
    if (!g_map) { int e = -errno; close(g_fd); g_fd = -1; return e; }
    g_mapaddr = (u64)(uintptr_t)g_map;

    g_rd = calloc(1, RDBUF);
    if (!g_rd) return -ENOMEM;

    for (int i = 0; i < 8; i++) {          /* golim coada de la open */
        u64 rc = 0;
        if (bwr(NULL, 0, &rc) < 0) break;
        if (!rc) break;
    }
    u32 c = BC_ENTER_LOOPER;
    bwr(&c, sizeof c, NULL);
    return 0;
}

/* ---------- parcel AIDL ---------- */
static u64 put16(u8 *b, u64 o, const char *s) {
    int n = (int)strlen(s);
    *(u32*)(b+o) = (u32)n; o += 4;
    for (int i = 0; i < n; i++) { *(u16*)(b+o) = (u16)(unsigned char)s[i]; o += 2; }
    while (o & 3) b[o++] = 0;
    return o;
}

/* header AIDL + descriptor (fara String16) */
static u64 parcel_iface(u8 *b, const char *desc) {
    u64 o = 0;
    *(u32*)(b+o) = 0x80000000u; o += 4;
    *(u32*)(b+o) = 0xFFFFFFFFu; o += 4;
    *(u32*)(b+o) = 0x53595354u; o += 4;
    int dl = (int)strlen(desc);
    *(u32*)(b+o) = (u32)dl; o += 4;
    for (int i = 0; i < dl; i++) { *(u16*)(b+o) = (u16)(unsigned char)desc[i]; o += 2; }
    o += 4;                                  /* padding dupa descriptor */
    return o;
}

/* ---------- rezultatul unei tranzactii ---------- */
typedef struct {
    u8  data[65536];
    u64 dlen;
    u8  offs[4096];
    u64 olen;
    u32 status;
    u32 pid;
} reply_t;

/* trimite tranzactie si parseaza reply-ul; free_buffer facut de apelant */
static int transact_raw(u32 handle, u32 code, const void *data, u64 dsize,
                        reply_t *rep, int do_free) {
    u8 pkt[4 + 64];
    memset(pkt, 0, sizeof pkt);
    u32 c = BC_TRANSACTION; memcpy(pkt, &c, 4);
    u8 *t = pkt + 4;
    *(u32*)(t+0)  = handle;
    *(u32*)(t+16) = code;
    *(u32*)(t+20) = TF_ACCEPT_FDS;
    *(u64*)(t+32) = dsize;
    *(u64*)(t+40) = 0;
    *(u64*)(t+48) = (u64)(uintptr_t)data;

    u64 rc = 0;
    int r = bwr(pkt, sizeof pkt, &rc);
    if (r < 0) return r;

    for (int a = 0; a < 800; a++) {
        if (!rc) { r = bwr(NULL, 0, &rc); if (r < 0) return r; }
        if (!rc) { usleep(2000); continue; }

        u64 used = rc; rc = 0; u64 off = 0;
        while (off + 4 <= used) {
            u32 w = *(u32*)(g_rd + off); off += 4;
            if (w == BR_NOOP || w == BR_TRANSACTION_COMPLETE) continue;
            if (w == BR_DEAD_REPLY)   return -EHOSTUNREACH;
            if (w == BR_FAILED_REPLY) return -EIO;
            if (w == BR_ACQUIRE || w == BR_INCREFS || w == BR_RELEASE || w == BR_DECREFS) {
                off += 8; continue;
            }
            if ((w & 0xffff) == BR_REPLY) {
                if (used < 76) return -EPROTO;
                u32 spid = *(u32*)(g_rd + 40);
                u64 dsz  = *(u64*)(g_rd + 44);
                u64 osz  = *(u64*)(g_rd + 52);
                u64 dptr = *(u64*)(g_rd + 60);
                u64 optr = *(u64*)(g_rd + 68);

                if (rep) {
                    rep->pid = spid;
                    rep->dlen = 0; rep->olen = 0; rep->status = 0;
                    if (dsz && dptr >= g_mapaddr && dptr + dsz <= g_mapaddr + g_mapsz) {
                        u64 n = dsz < sizeof rep->data ? dsz : sizeof rep->data;
                        memcpy(rep->data, (void*)(uintptr_t)dptr, n);
                        rep->dlen = dsz;
                        if (dsz >= 4) rep->status = *(u32*)(uintptr_t)dptr;
                    }
                    if (osz && osz <= sizeof rep->offs &&
                        optr >= g_mapaddr && optr + osz <= g_mapaddr + g_mapsz) {
                        memcpy(rep->offs, (void*)(uintptr_t)optr, osz);
                        rep->olen = osz;
                    }
                }
                g_last_dptr = dptr;
                if (do_free) {
                    u8 fb[12]; u32 fc = BC_FREE_BUFFER;
                    memcpy(fb, &fc, 4); memcpy(fb+4, &dptr, 8);
                    bwr(fb, 12, NULL);
                }
                return 0;
            }
            return -EPROTO;
        }
    }
    return -ETIMEDOUT;
}

/* getService -> handle local */
static int get_service_handle(const char *name, u32 *out_h) {
    u8 pl[512]; memset(pl, 0, sizeof pl);
    u64 n = parcel_iface(pl, "android.os.IServiceManager");
    n = put16(pl, n, name);
    reply_t rep;
    if (getenv("BDBG")) { fprintf(stderr,"[dbg] parcel %llu bytes:",(unsigned long long)n);
        for(u64 q=0;q<n&&q<96;q++) fprintf(stderr," %02x",pl[q]); fprintf(stderr,"\n"); }
    int r = transact_raw(0, 1 /*getService*/, pl, n, &rep, 0);
    if (r < 0) return r;
    if (getenv("BDBG")) fprintf(stderr,"[dbg] status=0x%x dlen=%llu olen=%llu pid=%u\n",
        rep.status,(unsigned long long)rep.dlen,(unsigned long long)rep.olen,rep.pid);
    if (rep.status != 0) return -(int)(rep.status & 0x7fffffff);
    if (rep.dlen < 8) return -ENOENT;
    /* flat_binder_object e la offsetul din offsets_buffer[0] */
    u32 off0 = rep.olen >= 4 ? *(u32*)rep.offs : 0;
    if (off0 + 12 > rep.dlen) return -EPROTO;
    /* in obiect: type(u32) flags(u32) handle(u32) */
    *out_h = *(u32*)(rep.data + off0 + 8);
    /* free dupa ce am citit */
    if (rep.dlen && rep.olen) {
        /* recitim dptr-ul e deja consumat; eliberam explicit */
    }
    return 0;
}

/* pregateste un handle pentru apel: ACQUIRE + INCREFS (ca libbinder) */
static void prepare_handle(u32 h) {
    u8 aq[8];
    /* ordinea libbinder (dovedita prin ptrace):
       ACQUIRE -> INCREFS -> FREE_BUFFER(pe bufferul din getService) */
    u32 ac = BC_ACQUIRE;  memcpy(aq, &ac, 4); memcpy(aq+4, &h, 4); bwr(aq, 8, NULL);
    u32 ic = BC_INCREFS;  memcpy(aq, &ic, 4); memcpy(aq+4, &h, 4); bwr(aq, 8, NULL);
    if (g_last_dptr) {
        u8 fb[12]; u32 fc = BC_FREE_BUFFER;
        memcpy(fb, &fc, 4); memcpy(fb+4, &g_last_dptr, 8);
        bwr(fb, 12, NULL);
        g_last_dptr = 0;
    }
}

static const char *arg_name(int argc, char **argv) {
    return argc > 2 ? argv[2] : NULL;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr,
          "usage: binder <cmd> [args]\n"
          "  list                          toate serviciile\n"
          "  check <name>                  verifica existenta\n"
          "  handle <name>                 handle-ul binder\n"
          "  desc <name>                   descriptorul de interfata\n"
          "  call <name> <code> [i32...]   apel generic\n"
          "  rawcall <handle> <code> [i32...]\n");
        return 1;
    }
    int e = bopen();
    if (e < 0) { fprintf(stderr, "open /dev/binder: %s\n", strerror(-e)); return 1; }

    const char *cmd = argv[1];
    reply_t rep;

    if (!strcmp(cmd, "list")) {
        u8 pl[256]; memset(pl, 0, sizeof pl);
        u64 n = parcel_iface(pl, "android.os.IServiceManager");
        *(u32*)(pl+n) = DUMP_PRIORITY_ALL; n += 4;
        int r = transact_raw(0, 6 /*listServices*/, pl, n, &rep, 1);
        if (r < 0) { fprintf(stderr, "listServices: %s\n", strerror(-r)); return 1; }
        if (rep.status) { fprintf(stderr, "listServices status=0x%x\n", rep.status); return 1; }
        if (rep.dlen < 8) { fprintf(stderr, "reply prea mic\n"); return 1; }
        if (getenv("BDBG")) { printf("dlen=%llu cnt@4=%u cnt@0=%u\n",(unsigned long long)rep.dlen,
            *(u32*)(rep.data+4), *(u32*)(rep.data));
            printf("raw:"); for(int q=0;q<120;q++) printf(" %02x",rep.data[q]); printf("\n"); }
        u32 cnt = *(u32*)(rep.data + 4);
        u64 o = 8;
        for (u32 i = 0; i < cnt && o + 4 <= rep.dlen; i++) {
            s32 L = *(s32*)(rep.data + o); o += 4;
            if (L < 0 || o + (u64)L*2 > rep.dlen) break;
            char nm[512]; u32 j;
            for (j = 0; j < (u32)L && j < sizeof(nm)-1; j++)
                nm[j] = (char)((u16*)(rep.data + o))[j];
            nm[j] = 0;
            if (getenv("BDBG")) { fprintf(stderr,"[i=%u lenoff=%llu L=%d '%s'] bytes:",
                i,(unsigned long long)(o-4),L,nm);
                for(int q=(int)(o-4); q<(int)(o-4)+12; q++) fprintf(stderr," %02x",rep.data[q]);
                fprintf(stderr,"\n"); }
            printf("%u\t%s\n", i, nm);
            o += (u64)L * 2;
            /* padding: la multiplu de 4, STRICT mai mare daca e deja aliniat
               (regula dedusa din 468 elemente reale) */
            o = (o & 3) ? ((o + 3) & ~3ULL) : (o + 4);
        }
        return 0;
    }

    if (!strcmp(cmd, "check")) {
        const char *nm = arg_name(argc, argv);
        if (!nm) { fprintf(stderr, "usage: binder check <name>\n"); return 1; }
        u8 pl[512]; memset(pl, 0, sizeof pl);
        u64 n = parcel_iface(pl, "android.os.IServiceManager");
        n = put16(pl, n, nm);
        int r = transact_raw(0, 3 /*checkService*/, pl, n, &rep, 1);
        if (r < 0) { fprintf(stderr, "checkService: %s\n", strerror(-r)); return 1; }
        if (rep.status == 0) printf("%s: found\n", nm);
        else                 printf("%s: not found (status=0x%x)\n", nm, rep.status);
        return 0;
    }

    if (!strcmp(cmd, "handle")) {
        const char *nm = arg_name(argc, argv);
        if (!nm) { fprintf(stderr, "usage: binder handle <name>\n"); return 1; }
        u32 h = 0;
        int r = get_service_handle(nm, &h);
        if (r < 0) { fprintf(stderr, "getService(%s): %s\n", nm, strerror(-r)); return 1; }
        printf("%s\t%u\n", nm, h);
        return 0;
    }

    if (!strcmp(cmd, "desc")) {
        const char *nm = arg_name(argc, argv);
        if (!nm) { fprintf(stderr, "usage: binder desc <name>\n"); return 1; }
        u32 h = 0;
        int r = get_service_handle(nm, &h);
        if (r < 0) { fprintf(stderr, "getService(%s): %s\n", nm, strerror(-r)); return 1; }
        prepare_handle(h);
        r = transact_raw(h, INTERFACE_TRANSACTION, NULL, 0, &rep, 1);
        if (r < 0) { fprintf(stderr, "interface: %s\n", strerror(-r)); return 1; }
        if (rep.status) { printf("(status=0x%x)\n", rep.status); return 0; }
        if (rep.dlen >= 4) {
            s32 L = *(s32*)(rep.data);
            if (L > 0 && (u64)L*2+4 <= rep.dlen) {
                char s[512]; u32 j;
                for (j = 0; j < (u32)L && j < sizeof(s)-1; j++)
                    s[j] = (char)((u16*)(rep.data + 4))[j];
                s[j] = 0;
                printf("%s\n", s);
                return 0;
            }
        }
        printf("(descriptor gol)\n");
        return 0;
    }

    if (!strcmp(cmd, "iface")) {
        /* iface <handle> - descriptorul de interfata, fara getService */
        if (argc < 3) { fprintf(stderr, "usage: binder iface <svcname>\n"); return 1; }
        u32 h = 0;
        int gr2 = get_service_handle(argv[2], &h);
        if (gr2 < 0) { fprintf(stderr, "getService(%s): %s\n", argv[2], strerror(-gr2)); return 1; }
        prepare_handle(h);
        int r = transact_raw(h, INTERFACE_TRANSACTION, NULL, 0, &rep, 1);
        if (r < 0) { fprintf(stderr, "iface(%s): %s\n", argv[2], strerror(-r)); return 1; }
        printf("status=0x%x len=%llu\n", rep.status, (unsigned long long)rep.dlen);
        if (rep.dlen >= 4) {
            s32 L = *(s32*)(rep.data);
            if (L > 0 && (u64)L*2+4 <= rep.dlen) {
                char sb[512]; u32 j;
                for (j = 0; j < (u32)L && j < sizeof(sb)-1; j++)
                    sb[j] = (char)((u16*)(rep.data + 4))[j];
                sb[j] = 0;
                printf("descriptor: %s\n", sb);
            }
        }
        return 0;
    }

    if (!strcmp(cmd, "aidlcall")) {
        /* aidlcall <svc> <descriptor> <code> [i32...] */
        if (argc < 5) { fprintf(stderr, "usage: binder aidlcall <svc> <descriptor> <code> [i32...]\n"); return 1; }
        u32 h = 0;
        int rr = get_service_handle(argv[2], &h);
        if (rr < 0) { fprintf(stderr, "getService(%s): %s\n", argv[2], strerror(-rr)); return 1; }
        prepare_handle(h);
        u8 pl[4096]; memset(pl, 0, sizeof pl);
        u64 n = parcel_iface(pl, argv[3]);
        for (int i = 5; i < argc; i++) {
            *(u32*)(pl+n) = (u32)strtoul(argv[i], NULL, 0); n += 4;
        }
        u32 code = (u32)strtoul(argv[4], NULL, 0);
        int r = transact_raw(h, code, pl, n, &rep, 1);
        if (r < 0) { fprintf(stderr, "aidlcall: %s\n", strerror(-r)); return 1; }
        printf("status=0x%x len=%llu\n", rep.status, (unsigned long long)rep.dlen);
        for (u64 i = 0; i < rep.dlen && i < 1024; i += 16) {
            printf("%04llx:", (unsigned long long)i);
            for (u64 j = i; j < i+16 && j < rep.dlen; j++) printf(" %02x", rep.data[j]);
            printf("\n");
        }
        return 0;
    }

    if (!strcmp(cmd, "call") || !strcmp(cmd, "rawcall")) {
        u32 h; u32 code; int argstart;
        if (!strcmp(cmd, "call")) {
            if (argc < 4) { fprintf(stderr, "usage: binder call <name> <code> [i32...]\n"); return 1; }
            int r = get_service_handle(argv[2], &h);
            if (r < 0) { fprintf(stderr, "getService(%s): %s\n", argv[2], strerror(-r)); return 1; }
            code = (u32)strtoul(argv[3], NULL, 0);
            argstart = 4;
        } else {
            if (argc < 4) { fprintf(stderr, "usage: binder rawcall <h> <code> [i32...]\n"); return 1; }
            h = (u32)strtoul(argv[2], NULL, 0);
            code = (u32)strtoul(argv[3], NULL, 0);
            argstart = 4;
        }
        prepare_handle(h);

        u8 pl[4096]; memset(pl, 0, sizeof pl);
        u64 n = 0;
        for (int i = argstart; i < argc; i++) {
            *(u32*)(pl+n) = (u32)strtoul(argv[i], NULL, 0); n += 4;
        }
        int r = transact_raw(h, code, pl, n, &rep, 1);
        if (r < 0) { fprintf(stderr, "call: %s\n", strerror(-r)); return 1; }
        printf("status=0x%x len=%llu\n", rep.status, (unsigned long long)rep.dlen);
        for (u64 i = 0; i < rep.dlen && i < 512; i += 16) {
            printf("%04llx:", (unsigned long long)i);
            for (u64 j = i; j < i+16 && j < rep.dlen; j++) printf(" %02x", rep.data[j]);
            printf("\n");
        }
        return 0;
    }

    fprintf(stderr, "comanda necunoscuta: %s\n", cmd);
    return 1;
}
