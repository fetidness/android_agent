/* bindinc.c - server binder GENERAL pentru Debian (glibc, direct /dev/binder)
 *
 * Nu e legat de niciun serviciu anume: primeste APELURI INTRANTE pe obiecte
 * binder locale si le decodeaza generic, pe orice interfata AIDL.
 *
 *   bindinc listen <interfata>            - asculta, afiseaza orice tranzactie
 *   bindinc listen <interfata> --json     - output JSON Lines (pentru piping)
 *   bindinc raw <hex-parcel>              - decodeaza un parcel dat
 *   bindinc version                       - versiune
 *
 * Mecanism:
 *   1. creeaza un obiect binder local (BINDER_TYPE_BINDER + cookie)
 *   2. il poate trimite ca argument oricarui serviciu (setCallback pattern)
 *   3. ruleaza looper: BR_TRANSACTION -> decodeaza -> BC_REPLY
 *
 * Compilare: gcc -O2 -o bindinc bindinc.c -lpthread
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <stdint.h>
#include <pthread.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>

typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;
typedef uint64_t u64; typedef int32_t s32;

#define BWR_REQ              0xc0306201UL
#define BC_TRANSACTION       0x40406300
#define BC_REPLY             0x40406301
#define BC_FREE_BUFFER       0x40086303
#define BC_ACQUIRE           0x40046304
#define BC_INCREFS           0x40046305
#define BC_RELEASE           0x40046306
#define BC_DECREFS           0x40046307
#define BC_ENTER_LOOPER      0x630c
#define BC_EXIT_LOOPER       0x630d
#define BC_REGISTER_LOOPER   0x630b
#define BR_NOOP              0x720c
#define BR_TRANSACTION       0x7201
#define BR_REPLY             0x7206
#define BR_TRANSACTION_COMPLETE 0x7211
#define BR_DEAD_REPLY        0x7f47
#define BR_FAILED_REPLY      0x7f4b
#define BR_ACQUIRE           0x7205
#define BR_INCREFS           0x7204
#define BR_RELEASE           0x7207
#define BR_DECREFS           0x7208
#define BR_DEAD_BINDER       0x720f
#define BR_CLEAR_DEATH_NOTIFICATION_DONE 0x7210
#define BR_SPAWN_LOOPER      0x720d
#define BR_TRANSACTION_SEC_CTX 0x7202

#define TF_ACCEPT_FDS        0x10
#define TF_ONE_WAY           0x01
#define INTERFACE_TRANSACTION 0x5f4e5446
#define DUMP_PRIORITY_ALL    0x0F
#define BINDER_TYPE_BINDER   0x73626962  /* 'bisb' */

#define RDBUF  (256*1024)
#define MAPSZ  (1024*1024)

struct bwr { u64 write_size, write_consumed, write_buffer,
                 read_size, read_consumed, read_buffer; };

static int    g_fd=-1;
static u8    *g_map=NULL;
static u64    g_mapaddr=0;
static size_t g_mapsz=0;
static u8    *g_rd=NULL;
static u64    g_my_node=0;          /* pointer-ul obiectului nostru local */
static volatile int g_run=1;
static int    g_json=0;
static long   g_count=0;
static long   g_iocalls=0;
static long iocalls(void){ return g_iocalls; }

static u64 now_ms(void){
    struct timespec ts; clock_gettime(CLOCK_REALTIME,&ts);
    return (u64)ts.tv_sec*1000ULL + ts.tv_nsec/1000000ULL;
}

/* ---------- ioctl binder ---------- */
static int bwr_call(void *w,u64 ws,u64 *rc){
    g_iocalls++;
    struct bwr b; memset(&b,0,sizeof b);
    b.write_size=ws;
    b.write_consumed=0;
    b.write_buffer=(u64)(uintptr_t)w;
    b.read_size=RDBUF;
    b.read_consumed=0;
    b.read_buffer=(u64)(uintptr_t)g_rd;
    if(ioctl(g_fd,BWR_REQ,&b)<0){
        if(errno==EAGAIN||errno==EWOULDBLOCK){ if(rc) *rc=0; return 0; }
        return -errno;
    }
    if(rc) *rc=b.read_consumed;
    return 0;
}

static int bopen(void){
    g_fd=open("/dev/binder",O_RDWR|O_CLOEXEC);
    if(g_fd<0) return -errno;
    fcntl(g_fd,F_SETFL,fcntl(g_fd,F_GETFL,0)|O_NONBLOCK);
    size_t sz=MAPSZ;
    while(sz>=4096){
        g_map=mmap(NULL,sz,PROT_READ,MAP_SHARED,g_fd,0);
        if(g_map!=MAP_FAILED){ g_mapsz=sz; break; }
        sz/=2;
    }
    if(g_map==MAP_FAILED){ int e=-errno; close(g_fd); return e; }
    g_mapaddr=(u64)(uintptr_t)g_map;
    g_rd=malloc(RDBUF);
    if(!g_rd) return -ENOMEM;
    memset(g_rd,0,RDBUF);
    for(int i=0;i<8;i++){ u64 rc=0; if(bwr_call(NULL,0,&rc)<0) break; if(!rc) break; }
    return 0;
}

/* ---------- parcela helpers ---------- */
static void p_put32(u8*b,u64*o,u32 v){ *(u32*)(b+*o)=v; *o+=4; }
static void p_put64(u8*b,u64*o,u64 v){ *(u64*)(b+*o)=v; *o+=8; }
static void p_putstr(u8*b,u64*o,const char*s){
    int l=(int)strlen(s);
    p_put32(b,o,(u32)l);
    for(int i=0;i<l;i++){ *(u16*)(b+*o)=(u16)(unsigned char)s[i]; *o+=2; }
    while(*o & 3) b[(*o)++]=0;
}
static void p_header(u8*b,u64*o,const char*desc){
    p_put32(b,o,0x80000000u);
    p_put32(b,o,0xFFFFFFFFu);
    p_put32(b,o,0x53595354u);
    p_putstr(b,o,desc);
    *o+=4;   /* padding dupa descriptor - DOVEDIT +4 fix */
}

/* citeste String16 la offset, intoarce lungimea si avanseaza offsetul */
static int p_getstr(const u8*b,u64 len,u64*o,char*out,size_t outsz){
    if(*o+4>len) return -1;
    u32 L=*(u32*)(b+*o); *o+=4;
    if(L==0xFFFFFFFFu || L>8192) return -1;
    if(*o+(u64)L*2>len) return -1;
    size_t n=L<outsz-1?L:outsz-1;
    for(size_t i=0;i<n;i++) out[i]=(char)*(u16*)(b+*o+i*2);
    out[n]=0;
    *o+=(u64)L*2;
    while(*o & 3) (*o)++;
    return (int)L;
}

/* ---------- reply ---------- */
static int send_reply(u64 txn_data_ptr,u64 txn_data_size,u32 code,const u8*data,u64 dlen){
    u8 pkt[4+64]; memset(pkt,0,sizeof pkt);
    u32 c=BC_REPLY; memcpy(pkt,&c,4);
    u8*t=pkt+4;
    *(u32*)(t+0)=0;               /* target handle (ignorat la reply) */
    *(u32*)(t+16)=code;
    *(u32*)(t+20)=TF_ACCEPT_FDS;
    *(u64*)(t+32)=dlen;
    *(u64*)(t+40)=0;
    *(u64*)(t+48)=(u64)(uintptr_t)data;
    return bwr_call(pkt,sizeof pkt,NULL);
}

/* ---------- decodor generic de parcel AIDL ----------
 * Nu stie schema: arata tipul fiecarei valori si incearca sa recunoasca
 * string-uri (UTF-16 cu lungime plauzibila) si numere.
 */
static void dump_parcel(const u8*data,u64 len,u64 baseoff){
    printf("      parcel: %llu bytes\n",(unsigned long long)len);
    u64 o=0;
    while(o+4<=len){
        u32 raw=*(u32*)(data+o);
        /* incearca String16: lungime plauzibila + suficenti bytes */
        if(raw>0 && raw<512 && o+4+(u64)raw*2<=len){
            int printable=1; char tmp[512];
            for(u32 i=0;i<raw;i++){
                u16 ch=*(u16*)(data+o+4+i*2);
                if(ch<0x20 || ch>0xFFFD){ printable=0; break; }
                tmp[i]=(char)ch;
            }
            if(printable && raw>=2){
                tmp[raw]=0;
                /* verifica padding-ul de aliniere */
                u64 adv=4+(u64)raw*2;
                while(adv & 3) adv++;
                if(o+adv<=len){
                    printf("      [%04llx] str16  \"%s\"\n",(unsigned long long)(baseoff+o),tmp);
                    o+=adv; continue;
                }
            }
        }
        s32 as_i=*(s32*)(data+o);
        /* heuristica float: exponent plauzibil */
        u32 expo=(raw>>23)&0xFF;
        if(expo>0 && expo<0xFF && raw!=0){
            float f; memcpy(&f,&raw,4);
            if(f==f && (f>1e-9f||f<-1e-9f) && (f<1e9f||f>-1e9f) && (f-(int)f)!=0){
                printf("      [%04llx] f32    %.6f   (u32=0x%08x)\n",
                       (unsigned long long)(baseoff+o),f,raw);
                o+=4; continue;
            }
        }
        printf("      [%04llx] i32    %d   (0x%08x)\n",
               (unsigned long long)(baseoff+o),as_i,raw);
        o+=4;
    }
}

/* ---------- handler pentru o tranzactie intrantă ---------- */
static void handle_transaction(void){
    /* binder_transaction_data incepe dupa 4 bytes de cmd */
    u8 *b=g_rd;
    u32 cmd=*(u32*)b;
    u64 base=4;
    u32 target_handle=*(u32*)(b+base+0);
    u32 code          =*(u32*)(b+base+16);
    u32 flags         =*(u32*)(b+base+20);
    u64 dsz           =*(u64*)(b+base+32);
    u64 dptr          =*(u64*)(b+base+48);
    u64 osz           =*(u64*)(b+base+40);
    u64 optr          =*(u64*)(b+base+56);
    u32 sender_pid    =*(u32*)(b+base+8);

    g_count++;
    const u8 *td=(const u8*)(uintptr_t)dptr;

    if(g_json){
        printf("{\"n\":%ld,\"t\":%llu,\"pid\":%u,\"code\":%u,\"flags\":%u,\"dsize\":%llu,\"oshift\":%llu}\n",
            g_count,(unsigned long long)now_ms(),sender_pid,code,flags,
            (unsigned long long)dsz,(unsigned long long)osz);
    } else {
        printf("\n=== TRX #%ld  code=%u  pid=%u  size=%llu ===\n",
               g_count,code,sender_pid,(unsigned long long)dsz);
    }

    /* INTERFACE_TRANSACTION: raspunde cu descriptorul nostru */
    if(code==INTERFACE_TRANSACTION){
        u8 out[512]; memset(out,0,sizeof out);
        u64 o=0;
        const char *d="bindinc.generic.ICallback";
        p_putstr(out,&o,d);
        send_reply(dptr,dsz,0,out,o);
        printf("      -> INTERFACE_TRANSACTION: %s\n",d);
        goto done;
    }

    if(td && dsz){
        if(!g_json) dump_parcel(td,dsz,0);
        else {
            /* JSON: hex brut, ca sa nu pierdem informatie */
            printf("{\"hex\":\"");
            for(u64 i=0;i<dsz && i<4096;i++) printf("%02x",td[i]);
            printf("\"}\n");
        }
    }

    /* raspunde cu un parcel gol (inima: sa nu blocam apelantul) */
    if(!(flags & TF_ONE_WAY)){
        u8 out[8]; memset(out,0,sizeof out);
        u64 o=0; p_put32(out,&o,0);
        send_reply(dptr,dsz,0,out,o);
    }

done:
    if(dptr){
        u8 fb[12]; u32 fc=BC_FREE_BUFFER;
        memcpy(fb,&fc,4); memcpy(fb+8,&dptr,8);
        bwr_call(fb,12,NULL);
    }
}

/* ---------- looper ---------- */
static void run_looper(int seconds){
    u32 c=BC_ENTER_LOOPER;
    bwr_call(&c,4,NULL);
    time_t deadline=time(NULL)+seconds;
    if(!g_json) printf("[bindinc] looper pornit, %d s, obiect=%llx\n",
                       seconds,(unsigned long long)g_my_node);
    fflush(stdout);

    while(g_run && time(NULL)<deadline){
        u64 rc=0;
        int r=bwr_call(NULL,0,&rc);
        if(r<0){ if(r==-EINTR) continue; break; }
        if(!rc){ usleep(20000); continue; }
        u64 off=0;
        while(off+4<=rc){
            u32 w=*(u32*)(g_rd+off);
            if(w==BR_NOOP||w==BR_TRANSACTION_COMPLETE){ off+=4; continue; }
            if(w==BR_ACQUIRE||w==BR_INCREFS||w==BR_RELEASE||w==BR_DECREFS){ off+=12; continue; }
            if(w==BR_DEAD_BINDER||w==BR_CLEAR_DEATH_NOTIFICATION_DONE){ off+=12; continue; }
            if(w==BR_SPAWN_LOOPER){ off+=4; continue; }
            if(w==BR_TRANSACTION||w==BR_TRANSACTION_SEC_CTX){
                handle_transaction();
                off+=4+64;   /* cmd + binder_transaction_data */
                continue;
            }
            off+=4;
        }
        fflush(stdout);
    }
    u32 ce=BC_EXIT_LOOPER;
    bwr_call(&ce,4,NULL);
}



/* pregateste handle-ul pentru apel: ACQUIRE + INCREFS (ca libbinder) */
static void prepare_handle(u32 h){
    /* ACQUIRE + INCREFS; consumam reply-urile ca sa nu polueze coada */
    u8 a[8]; u64 rc=0;
    { u32 c=BC_ACQUIRE; memcpy(a,&c,4); memcpy(a+4,&h,4); bwr_call(a,8,&rc);
      if(rc){ bwr_call(NULL,0,NULL); } }
    { u32 c=BC_INCREFS; memcpy(a,&c,4); memcpy(a+4,&h,4); bwr_call(a,8,&rc);
      if(rc){ bwr_call(NULL,0,NULL); } }
    (void)h;
}

/* ---------- getService ---------- */
struct reply_s { u8 data[262144]; u64 dlen; u8 offs[65536]; u64 olen; u32 status; u32 pid; };

/* transact_raw copiat verbatim din debian_binder.c (dovedit functional) */
static int transact_raw(u32 handle,u32 code,const void*data,u64 dsize,
                        struct reply_s *rep,int do_free){
    u8 pkt[4+64]; memset(pkt,0,sizeof pkt);
    u32 c=BC_TRANSACTION; memcpy(pkt,&c,4);
    u8 *t=pkt+4;
    *(u32*)(t+0) = handle;
    *(u32*)(t+16)= code;
    *(u32*)(t+20)= TF_ACCEPT_FDS;
    *(u64*)(t+32)= dsize;
    *(u64*)(t+40)= 0;
    *(u64*)(t+48)= (u64)(uintptr_t)data;
    u64 rc=0;
    int r=bwr_call(pkt,sizeof pkt,&rc);
    if(getenv("BD")) fprintf(stderr,"[TR] h=%u code=%u send r=%d rc=%llu\n",handle,code,r,(unsigned long long)rc);
    if(r<0) return r;
    for(int a=0;a<800;a++){
        if(!rc){ r=bwr_call(NULL,0,&rc); if(r<0) return r; }
        if(getenv("BD")&&a<5) fprintf(stderr,"[TR] a=%d rc=%llu\n",a,(unsigned long long)rc);
        if(!rc){ usleep(2000); continue; }
        u64 used=rc; rc=0; u64 off=0;
        while(off+4<=used){
            u32 w=*(u32*)(g_rd+off); off+=4;
            if(getenv("BD")) fprintf(stderr,"[TR]   cmd=0x%x used=%llu\n",w,(unsigned long long)used);
            if(w==BR_NOOP||w==BR_TRANSACTION_COMPLETE) continue;
            if(w==BR_DEAD_REPLY)   return -EHOSTUNREACH;
            if(w==BR_FAILED_REPLY) return -EIO;
            if(w==BR_ACQUIRE||w==BR_INCREFS||w==BR_RELEASE||w==BR_DECREFS){ off+=8; continue; }
            if((w&0xffff)==BR_REPLY){
                if(used<76) return -EPROTO;
                u32 spid =*(u32*)(g_rd+40);
                u64 dsz  =*(u64*)(g_rd+44);
                u64 osz  =*(u64*)(g_rd+52);
                u64 dptr =*(u64*)(g_rd+60);
                u64 optr =*(u64*)(g_rd+68);
                if(rep){
                    rep->pid=spid; rep->dlen=0; rep->olen=0; rep->status=0;
                    if(dsz && dptr>=g_mapaddr && dptr+dsz<=g_mapaddr+g_mapsz){
                        u64 n=dsz<sizeof rep->data?dsz:sizeof rep->data;
                        memcpy(rep->data,(void*)(uintptr_t)dptr,n);
                        rep->dlen=dsz;
                        if(dsz>=4) rep->status=*(u32*)(uintptr_t)dptr;
                    }
                    if(osz && osz<=sizeof rep->offs && optr>=g_mapaddr && optr+osz<=g_mapaddr+g_mapsz){
                        memcpy(rep->offs,(void*)(uintptr_t)optr,osz);
                        rep->olen=osz;
                    }
                }
                if(do_free){
                    u8 fb[12]; u32 fc=BC_FREE_BUFFER;
                    memcpy(fb,&fc,4); memcpy(fb+4,&dptr,8);
                    bwr_call(fb,12,NULL);
                }
                return 0;
            }
            return -EPROTO;
        }
    }
    return -ETIMEDOUT;
}

static int transact_once(u32 handle,u32 code,const void*d,u64 ds,u32*outstatus){
    struct reply_s rep; memset(&rep,0,sizeof rep);
    int r=transact_raw(handle,code,d,ds,&rep,1);
    if(outstatus) *outstatus=rep.status;
    return r;
}

static int get_service_handle(const char*name,u32*out_h){
    u8 pl[512]; memset(pl,0,sizeof pl);
    u64 o=0;
    p_put32(pl,&o,0x80000000u);
    p_put32(pl,&o,0xFFFFFFFFu);
    p_put32(pl,&o,0x53595354u);
    p_putstr(pl,&o,"android.os.IServiceManager");
    o+=4;
    p_putstr(pl,&o,name);
    u32 st=0;
    /* trebuie sa citim reply-ul ca sa luam handle-ul */
    u8 pkt[4+64]; memset(pkt,0,sizeof pkt);
    u32 c=BC_TRANSACTION; memcpy(pkt,&c,4);
    u8*t=pkt+4;
    *(u32*)(t+0)=0;
    *(u32*)(t+16)=1;
    *(u32*)(t+20)=TF_ACCEPT_FDS;
    *(u64*)(t+32)=o;
    *(u64*)(t+40)=0;
    *(u64*)(t+48)=(u64)(uintptr_t)pl;
    u64 rc=0;
    int r=bwr_call(pkt,sizeof pkt,&rc);
    if(r<0) return r;
    for(int a=0;a<600;a++){
        if(!rc){ r=bwr_call(NULL,0,&rc); if(r<0) return r; }
        if(!rc){ usleep(2000); continue; }
        u64 used=rc; rc=0; u64 off=0;
        while(off+4<=used){
            u32 w=*(u32*)(g_rd+off); off+=4;
            if(w==BR_NOOP||w==BR_TRANSACTION_COMPLETE) continue;
            if(w==BR_DEAD_REPLY) return -EHOSTUNREACH;
            if(w==BR_FAILED_REPLY) return -EIO;
            if(w==BR_ACQUIRE||w==BR_INCREFS||w==BR_RELEASE||w==BR_DECREFS){ off+=8; continue; }
            if(w==BR_SPAWN_LOOPER) continue;
            if((w&0xffff)==BR_REPLY){
                if(used<76) return -EPROTO;
                u64 dsz=*(u64*)(g_rd+44);
                u64 osz=*(u64*)(g_rd+52);
                u64 dptr=*(u64*)(g_rd+60);
                u64 optr=*(u64*)(g_rd+68);
                st=(dsz>=4 && dptr)?*(u32*)(uintptr_t)dptr:0xFFFFFFFCu;
                if(st==0 && osz>=4 && optr){
                    u32 off0=*(u32*)(uintptr_t)optr;
                    if(off0+12<=dsz){
                        *out_h=*(u32*)(uintptr_t)(dptr+off0+8);
                    }
                }
                /* NU eliberam bufferul aici (ca originalul, do_free=0) */
                if(st!=0) return -(int)(st&0x7fffffff);
                return 0;
            }
            return -EPROTO;
        }
    }
    return -ETIMEDOUT;
}

/* ---------- trimite obiectul nostru binder catre un serviciu ----------
 * Construieste un parcel cu flat_binder_object local si il trimite
 * la <serviciu> code <code>. Asta este exact pattern-ul setCallback.
 */
static u64 put_local_binder(u8*b,u64*o){
    /* offsets_size = 4 (un singur offset) */
    u64 start=*o;
    p_put32(b,o,BINDER_TYPE_BINDER);   /* type */
    p_put32(b,o,0x7f);                 /* flags: priority ceiling (ca libbinder) */
    p_put64(b,o,g_my_node);            /* binder pointer local */
    p_put64(b,o,0x1234);               /* cookie */
    return start;
}

static int send_callback_h(const char*svc,u32 h,const char*desc,u32 code){
    (void)svc;
    u8 pl[1024]; memset(pl,0,sizeof pl);
    u64 o=0;
    p_header(pl,&o,desc);
    u8 offs[256]; memset(offs,0,sizeof offs);
    u64 boff=put_local_binder(pl,&o);
    *(u32*)offs=(u32)boff;

    u8 pkt[4+64]; memset(pkt,0,sizeof pkt);
    u32 c=BC_TRANSACTION; memcpy(pkt,&c,4);
    u8*t=pkt+4;
    *(u32*)(t+0)=h;
    *(u32*)(t+16)=code;
    *(u32*)(t+20)=TF_ACCEPT_FDS;
    *(u64*)(t+32)=o;
    *(u64*)(t+40)=4;
    *(u64*)(t+48)=(u64)(uintptr_t)pl;
    *(u64*)(t+56)=(u64)(uintptr_t)offs;

    u64 rc=0;
    int r=bwr_call(pkt,sizeof pkt,&rc);
    if(r<0) return r;
    struct reply_s rep; memset(&rep,0,sizeof rep);
    for(int a=0;a<400;a++){
        if(!rc){ r=bwr_call(NULL,0,&rc); if(r<0) return r; }
        if(!rc){ usleep(2000); continue; }
        u64 used=rc; rc=0; u64 off=0;
        while(off+4<=used){
            u32 w=*(u32*)(g_rd+off); off+=4;
            if(getenv("BD")) fprintf(stderr,"[SC] cmd=0x%x\n",w);
            if(w==BR_NOOP||w==BR_TRANSACTION_COMPLETE) continue;
            if(w==BR_DEAD_REPLY) return -EHOSTUNREACH;
            if(w==BR_FAILED_REPLY) return -EIO;
            if(w==BR_ACQUIRE||w==BR_INCREFS||w==BR_RELEASE||w==BR_DECREFS){ off+=8; continue; }
            if((w&0xffff)==BR_REPLY){
                u64 dsz=*(u64*)(g_rd+44), dptr=*(u64*)(g_rd+60);
                u32 st=(dsz>=4&&dptr)?*(u32*)(uintptr_t)dptr:0;
                printf("[bindinc] setCallback status=0x%x\n",st);
                if(dptr){ u8 fb[12]; u32 fc=BC_FREE_BUFFER; memcpy(fb,&fc,4); memcpy(fb+4,&dptr,8); bwr_call(fb,12,NULL); }
                return (st==0)?0:-(int)(st&0x7fffffff);
            }
            return -EPROTO;
        }
    }
    printf("[bindinc] setCallback: oneway (fara reply, normal)\n");
    return 0;
}

/* ---------- thread looper pentru a putea trimite in paralel ---------- */
struct lthr { int secs; };
static void *looper_thread(void *arg){
    struct lthr *a=(struct lthr*)arg;
    run_looper(a->secs);
    return NULL;
}

/* ---------- main ---------- */
static void on_sig(int s){ (void)s; g_run=0; }

int main(int argc,char**argv){
    const char*cmd=argc>1?argv[1]:"help";

    if(!strcmp(cmd,"version")){
        printf("bindinc 1.0 - server binder generic\n");
        return 0;
    }

    if(!strcmp(cmd,"call")){
        /* call <svc> <desc> <code> - apel simplu, fara obiect binder */
        if(argc<5){ fprintf(stderr,"usage: bindinc call <svc> <desc> <code>\n"); return 1; }
        if(bopen()<0){ fprintf(stderr,"binder open failed\n"); return 1; }
        u32 h=0;
        int r=get_service_handle(argv[2],&h);
        printf("getService(%s) -> r=%d h=%u\n",argv[2],r,h);
        if(r<0||!h) return 1;
        u8 pl[512]; memset(pl,0,sizeof pl);
        u64 o=0;
        p_header(pl,&o,argv[3]);
        if(getenv("BD")) fprintf(stderr,"[PL] dsize=%llu hex:",(unsigned long long)o);
        if(getenv("BD")){ for(u64 q=0;q<o;q++) fprintf(stderr,"%02x",pl[q]); fprintf(stderr,"\n"); }
        u32 st=0;
        int rr=transact_once(h,(u32)atoi(argv[4]),pl,o,&st);
        printf("call code=%s -> r=%d status=0x%x\n",argv[4],rr,st);
        return 0;
    }

    if(!strcmp(cmd,"raw")){
        /* decodeaza un parcel hex dat pe linia de comanda */
        if(argc<3){ fprintf(stderr,"usage: bindinc raw <hex>\n"); return 1; }
        const char*hx=argv[2];
        size_t n=strlen(hx)/2;
        u8*d=malloc(n?n:1);
        for(size_t i=0;i<n;i++){ unsigned v; sscanf(hx+i*2,"%2x",&v); d[i]=(u8)v; }
        dump_parcel(d,n,0);
        free(d);
        return 0;
    }

    if(!strcmp(cmd,"listen")){
        int secs=60;
        const char*svc=NULL,*desc=NULL; u32 cbcode=1, aftercode=0;
        for(int i=2;i<argc;i++){
            if(!strcmp(argv[i],"--json")) g_json=1;
            else if(!strcmp(argv[i],"--seconds") && i+1<argc) secs=atoi(argv[++i]);
            else if(!strcmp(argv[i],"--svc") && i+1<argc) svc=argv[++i];
            else if(!strcmp(argv[i],"--desc") && i+1<argc) desc=argv[++i];
            else if(!strcmp(argv[i],"--code") && i+1<argc) cbcode=(u32)atoi(argv[++i]);
            else if(!strcmp(argv[i],"--after") && i+1<argc) aftercode=(u32)atoi(argv[++i]);
        }
        if(bopen()<0){ fprintf(stderr,"binder open failed\n"); return 1; }
        /* obiectul nostru local: pointer catre o zona stabila */
        static u8 node[64];
        g_my_node=(u64)(uintptr_t)node;
        signal(SIGINT,on_sig); signal(SIGTERM,on_sig);

        if(svc && desc){
            /* ordine corecta: TOATE cererile sincrone intai, APOI looper.
               Un singur cititor pe fd - altfel reply-urile se pierd. */
            u32 h=0;
            int gr=get_service_handle(svc,&h);
            printf("[bindinc] getService(%s) -> r=%d h=%u\n",svc,gr,h);
            if(gr==0 && h){
                int cr=send_callback_h(svc,h,desc,cbcode);
                printf("[bindinc] setCallback(code=%u) -> r=%d\n",cbcode,cr);
                if(aftercode){
                    /* pornim looper-ul ACUM: HAL-ul poate apela callback-ul
                       in timpul lui start, deci trebuie sa fim pregatiti */
                    struct lthr *lt=malloc(sizeof *lt);
                    lt->secs=secs;
                    pthread_t th;
                    pthread_create(&th,NULL,looper_thread,lt);
                    usleep(80000);
                    u8 e[4]={0,0,0,0}; u32 st=0;
                    int rr=transact_once(h,aftercode,e,0,&st);
                    printf("[bindinc] after code=%u -> r=%d status=0x%x\n",aftercode,rr,st);
                }
            }
        } else if(!g_json){
            printf("[bindinc] atentie: fara --svc/--desc nu trimit callback,\n");
            printf("          ascult doar apeluri deja adresate acestui proces\n");
        }
        if(!(svc && desc)) run_looper(secs);
        else { sleep(secs); g_run=0; }
        if(!g_json) printf("[bindinc] oprit dupa %ld tranzactii\n",g_count);
        return 0;
    }

    fprintf(stderr,
        "bindinc - server binder generic\n\n"
        "  bindinc listen [--svc S --desc D --code N] [--seconds N] [--json]\n"
        "  bindinc raw <hex-parcel>\n"
        "  bindinc version\n\n"
        "listeaza orice apel binder INTRANT si il decodeaza generic.\n"
        "cu --svc/--desc trimite mai intai obiectul local ca callback.\n");
    return 1;
}
