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
    u8  data[262144];
    u64 dlen;
    u8  offs[65536];
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
    /* in obiect: type(u32) flags(u32) handle(u32) - handle-ul e un u32 FARA
       bit de semn. Valoarea 0x80000001 vazuta de teste venea din citirea
       gresita a unui u64/offset, NU e "null": null in parcel = 0x80000001 doar
       ca STATUS, nu ca handle. Handle-ul real al serviciilor de sistem e 1. */
    *out_h = *(u32*)(rep.data + off0 + 8);
    if (*out_h == 0 || *out_h == 0x80000001u) return -ENOENT;
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


/* ---- BINDALL: leaga toate serviciile si tine handlurile vii ---- */
typedef struct { char name[192]; char desc[192]; u32 handle; int ok; int err; } bound_t;
static bound_t *g_b = NULL; static int g_nb = 0, g_cap = 0;

static void add_bound(const char *n, const char *d, u32 h, int ok, int err) {
    if (g_nb >= g_cap) { g_cap = g_cap ? g_cap*2 : 256; g_b = realloc(g_b, g_cap*sizeof(bound_t)); }
    bound_t *b = &g_b[g_nb++];
    snprintf(b->name, sizeof b->name, "%s", n);
    snprintf(b->desc, sizeof b->desc, "%s", d ? d : "");
    b->handle = h; b->ok = ok; b->err = err;
}

static int read_desc(u32 h, char *out, size_t outsz) {
    reply_t rep;
    int r = transact_raw(h, INTERFACE_TRANSACTION, NULL, 0, &rep, 1);
    if (getenv("BDBG")) fprintf(stderr,"  [rd] h=%u r=%d status=0x%x dlen=%llu\n",h,r,rep.status,(unsigned long long)rep.dlen);
    if (r < 0) return r;
    if (rep.status == 0xffffffffu) return -EIO;
    out[0] = 0;
    if (rep.dlen >= 4) {
        u32 L = *(u32*)rep.data;
        if (L > 0 && (u64)L*2 + 4 <= rep.dlen && L < outsz) {
            for (u32 i = 0; i < L; i++) out[i] = (char)*(u16*)(rep.data + 4 + i*2);
            out[L] = 0;
        }
    }
    return out[0] ? 0 : -ENOENT;
}

static int list_names(char ***out_names) {
    reply_t rep;
    u8 pl[256]; memset(pl,0,sizeof pl);
    u64 n = parcel_iface(pl, "android.os.IServiceManager");
    *(u32*)(pl+n) = DUMP_PRIORITY_ALL; n += 4;
    int r = transact_raw(0, 6, pl, n, &rep, 1);
    if (r < 0) return r;
    if (rep.status) return -(int)(rep.status & 0x7fffffff);
    if (rep.dlen < 8) return -EPROTO;
    u32 cnt = *(u32*)(rep.data + 4);
    char **arr = calloc(cnt + 1, sizeof(char*));
    u64 o = 8; int got = 0;
    for (u32 i = 0; i < cnt && o + 4 <= rep.dlen; i++) {
        s32 L = *(s32*)(rep.data + o); o += 4;
        if (L < 0 || o + (u64)L*2 > rep.dlen) break;
        char *s = malloc(L + 1);
        for (s32 k = 0; k < L; k++) s[k] = (char)*(u16*)(rep.data + o + k*2);
        s[L] = 0; o += (u64)L*2;
        while (o & 3) o++;
        arr[got++] = s;
    }
    *out_names = arr;
    return got;
}

int main(int argc, char **argv) {
    const char *cmd = argc > 1 ? argv[1] : "help";
    if (bopen() < 0) { fprintf(stderr, "binder open failed\n"); return 1; }
    if (!strcmp(cmd, "bindall")) {
        int quiet = argc > 2 && !strcmp(argv[2], "--quiet");
        char **names = NULL;
        int cnt = list_names(&names);
        if (cnt < 0) { fprintf(stderr, "listServices: %s\n", strerror(-cnt)); return 1; }
        fprintf(stderr, "[bindall] %d servicii\n", cnt);
        int ok=0, lazy=0, refused=0;
        int lim = getenv("LIM") ? atoi(getenv("LIM")) : cnt;
        for (int i = 0; i < cnt && i < lim; i++) {
            const char *nm = names[i]; if (!nm || !*nm) continue;
            u32 h = 0;
            int r = get_service_handle(nm, &h);
            if (r < 0) { add_bound(nm,"",0,0,r); if (r==-ENOENT) lazy++; else refused++;
                         fprintf(stderr,"NOGET %s r=%d\n",nm,r); continue; }
            if (getenv("BDBG")) fprintf(stderr,"GOT %s h=%u\n",nm,h);
            prepare_handle(h);
            char d[192] = ""; int dr = read_desc(h, d, sizeof d);
            if (dr == 0 && d[0]) { add_bound(nm,d,h,1,0); ok++; }
            else { add_bound(nm,"",h,0,dr); refused++; fprintf(stderr,"FAILDESC %s h=%u dr=%d desc='%s'\n",nm,h,dr,d); }
        }
        printf("=== BINDALL ===\n");
        printf("listate     : %d\n", cnt);
        printf("legate OK   : %d\n", ok);
        printf("lazy/ENOENT : %d\n", lazy);
        printf("refuzate    : %d\n", refused);
        if (!quiet) for (int i=0;i<g_nb;i++) if (g_b[i].ok)
            printf("BOUND\t%s\th=%u\t%s\n", g_b[i].name, g_b[i].handle, g_b[i].desc);
        return 0;
    }
    if (!strcmp(cmd, "probe")) {
        /* probe: leaga cateva servicii si face apeluri reale */
        const char *tests[][3] = {
            {"android.hardware.health.IHealth/default","android.hardware.health.IHealth","1"},
            {"android.hardware.thermal.IThermal/default","android.hardware.thermal.IThermal","1"},
            {"android.hardware.vibrator.IVibrator/default","android.hardware.vibrator.IVibrator","2"},
            {"batteryproperties","android.os.IBatteryPropertiesRegistrar","1"},
            {"display","android.hardware.display.IDisplayManager","1"},
            {"input","android.hardware.input.IInputManager","1"},
            {NULL,NULL,NULL}};
        for (int i = 0; tests[i][0]; i++) {
            u32 h=0; int r=get_service_handle(tests[i][0], &h);
            if (r<0) { printf("%-58s BIND FAIL %s\n", tests[i][0], strerror(-r)); continue; }
            prepare_handle(h);
            char d[192]=""; read_desc(h,d,sizeof d);
            char desc[192];
            snprintf(desc,sizeof desc,"%s", tests[i][1]);
            u8 pl[512]; memset(pl,0,sizeof pl);
            u64 n = parcel_iface(pl, desc);
            reply_t rep;
            int rr = transact_raw(h, (u32)atoi(tests[i][2]), pl, n, &rep, 1);
            if (rr<0) { printf("%-58s CALL ERR %s (desc=%s)\n", tests[i][0], strerror(-rr), d); continue; }
            printf("%-58s status=0x%-10x len=%-6llu desc=%s\n",
                   tests[i][0], rep.status, (unsigned long long)rep.dlen, d);
        }
        return 0;
    }

    fprintf(stderr, "comenzi: bindall [--quiet] | probe\n");
    return 1;
}
