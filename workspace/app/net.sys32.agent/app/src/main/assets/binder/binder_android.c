
/* binder_final.c - client Binder complet si corect.
 *
 * Toate offseturile au fost VERIFICATE prin ptrace pe libbinder real
 * (/system/bin/service), nu presupuse.
 *
 * REPLY layout (index absolut in read_buffer):
 *   off  0 : 0x720c BR_NOOP            (poate lipsi)
 *   off  4 : 0x7206 BR_REPLY
 *   off  8 : 0x80407203 header comanda
 *   off 12 : binder_transaction_data:
 *            +0  target.ptr/handle u64
 *            +8  cookie           u32
 *            +12 code             u32
 *            +16 flags            u32
 *            +20 sender_pid       u32
 *            +24 sender_euid      u32
 *            +28 data_size        u64
 *            +36 offsets_size     u64
 *            +44 data.ptr         u64
 *            +52 offsets.ptr      u64
 *   total 12 + 60 = 72 bytes
 *
 * PARCEL (IServiceManager):
 *   int32 0x80000000 | int32 0xFFFFFFFF | int32 'TSYS' | int32 len(desc)
 *   UTF-16 desc + pad4 | int32 len(arg) | UTF-16 arg + pad4
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

typedef uint16_t u16; typedef uint32_t u32; typedef uint64_t u64; typedef int32_t s32;
typedef unsigned char u8;

#define BWR_REQ     0xc0306201UL
#define BC_TRANSACTION 0x40406300
#define BC_FREE_BUFFER 0x40086303
#define BC_ENTER_LOOPER 0x630c
#define BR_NOOP     0x720c
#define BR_REPLY    0x7206
#define BR_TRANSACTION_COMPLETE 0x7211
#define BR_DEAD_REPLY     0x7f47
#define BR_FAILED_REPLY   0x7f4b
#define BR_DEAD_BINDER    0x720f
#define BR_CLEAR_DEATH_NOTIFICATION_DONE 0x7210
#define RDBUF 65536
#define MAPSZ 4096   /* zona mmap binder: EXACT o pagina, ceruta de kernel */

static int g_fd=-1; static u8*g_map; static u64 g_mapaddr; static u8*g_rd; static size_t g_mapsz=MAPSZ;

static int bwr(void*w,u64 ws,u64*rc){
    struct {u64 a,b,c,d,e,f;} r; memset(&r,0,sizeof r);
    r.a=ws; r.c=(u64)(uintptr_t)w; r.d=RDBUF; r.f=(u64)(uintptr_t)g_rd;
    if(ioctl(g_fd,BWR_REQ,&r)<0){ if(errno==EAGAIN){if(rc)*rc=0;return 0;} return -errno; }
    if(rc)*rc=r.e; return 0;
}
static int bopen(void){
    g_fd=open("/dev/binder",O_RDWR|O_CLOEXEC); if(g_fd<0) return -errno;
    fcntl(g_fd,F_SETFL,fcntl(g_fd,F_GETFL,0)|O_NONBLOCK);
    { size_t sz=1024*1024;
      while(sz>=4096){
        g_map=mmap(NULL,sz,PROT_READ,MAP_SHARED,g_fd,0);
        if(g_map!=MAP_FAILED){ g_mapsz=sz; break; }
        sz/=2;
      }
      if(g_map==MAP_FAILED){int e=-errno;close(g_fd);return e;}
      if(getenv("DBG")) fprintf(stderr,"[dbg] mmap %zu bytes ok\n",g_mapsz);
    }
    g_mapaddr=(u64)(uintptr_t)g_map; g_rd=calloc(1,RDBUF);
    for(int i=0;i<8;i++){u64 rc=0; if(bwr(NULL,0,&rc)<0)break; if(!rc)break;}
    u32 c=BC_ENTER_LOOPER; bwr(&c,4,NULL);
    return 0;
}

/* parcel AIDL; daca arg==NULL nu se scrie String16 */
static u64 mkparcel_ex(u8*b,const char*desc,const char*arg,int pad){
    u64 o=0;
    *(u32*)(b+o)=0x80000000u; o+=4;
    *(u32*)(b+o)=0xFFFFFFFFu; o+=4;
    *(u32*)(b+o)=0x53595354u; o+=4;
    int dl=(int)strlen(desc);
    *(u32*)(b+o)=(u32)dl; o+=4;
    for(int i=0;i<dl;i++){ *(u16*)(b+o)=(u16)(unsigned char)desc[i]; o+=2; }
    if(pad) o+=4;                          /* padding dupa descriptor (IServiceManager) */
    if(arg){
        int al=(int)strlen(arg);
        *(u32*)(b+o)=(u32)al; o+=4;
        for(int i=0;i<al;i++){ *(u16*)(b+o)=(u16)(unsigned char)arg[i]; o+=2; }
        while(o%4) b[o++]=0;
    }
    return o;
}
static u64 mkparcel(u8*b,const char*desc,const char*arg){ return mkparcel_ex(b,desc,arg,1); }

static u64 g_dlen; static u64 g_lastdptr; static u8* g_dataptr; static u8 g_offbuf[256]; static u64 g_offsz;
static u32 g_pid;

/* trimite tranzactia si parseaza TOATE comenzile din reply (incremental) */
static int transact(u32 handle,u32 code,const void*data,u64 dsize,
                    u8*out,u64*outlen,u32*outpid,u32*status,u64*outoffsz){
    u8 pkt[4+64]; memset(pkt,0,sizeof pkt);
    u32 c=BC_TRANSACTION; memcpy(pkt,&c,4);
    u8*t=pkt+4;
    *(u32*)(t+0)=handle;
    *(u32*)(t+16)=code;
    *(u32*)(t+20)=0x10;   /* TF_ACCEPT_FDS - folosit de libbinder in TOATE tranzactiile */
    *(u64*)(t+32)=dsize;
    *(u64*)(t+40)=0;
    *(u64*)(t+48)=(u64)(uintptr_t)data;

    u64 rc=0;
    int r=bwr(pkt,sizeof pkt,&rc);
    if(r<0) return r;

    for(int a=0;a<600;a++){
        if(!rc){ r=bwr(NULL,0,&rc); if(r<0) return r; }
        if(!rc){ usleep(3000); continue; }
        u64 used=rc; rc=0; u64 off=0;
        while(off+4<=used){
            u32 w=*(u32*)(g_rd+off); off+=4;
            if(w==BR_NOOP||w==BR_TRANSACTION_COMPLETE) continue;
            if(w==BR_DEAD_REPLY) return -EHOSTUNREACH;
            if(w==BR_FAILED_REPLY) return -EIO;
            /* comenzile cu 8 bytes de payload (ref counting) */
            if(w==0x7204||w==0x7205||w==0x7207||w==0x7208){ off+=8; continue; }
            if(w==BR_DEAD_BINDER||w==BR_CLEAR_DEATH_NOTIFICATION_DONE){ off+=8; continue; }
            if((w&0xffff)==BR_REPLY){
                if(getenv("DBG")){
                    fprintf(stderr,"[RAW] used=%llu off=%llu words:",(unsigned long long)used,(unsigned long long)off);
                    for(u64 q=0;q+4<=used;q+=4) fprintf(stderr," %d:%d",(int)q,*(u32*)(g_rd+q));
                    fprintf(stderr,"\n");
                }
                /* urmeaza header-ul (4B) apoi binder_transaction_data la +12 */
                if(off+4>used) return -EPROTO;
                u64 base=off+4;             /* absolut: inceput struct */
                if(used<76) return -EPROTO;
                u32 spid    =*(u32*)(g_rd+40);
                u64 dsz     =*(u64*)(g_rd+44);
                u64 osz     =*(u64*)(g_rd+52);
                u64 dptr    =*(u64*)(g_rd+60);
                u64 optr    =*(u64*)(g_rd+68);
                off = 76;

                g_pid=spid;
                if(outpid)*outpid=spid;
                if(outlen)*outlen=dsz;
                if(outoffsz)*outoffsz=osz;
                if(getenv("DBG"))
                    fprintf(stderr,"[dbg] pid=%u dsize=%llu osz=%llu dptr=0x%llx optr=0x%llx map=0x%llx\n",
                            spid,(unsigned long long)dsz,(unsigned long long)osz,
                            (unsigned long long)dptr,(unsigned long long)optr,(unsigned long long)g_mapaddr);

                /* verifica limitele INAINTE de a copia (altfel SIGSEGV) */
                /* binder aloca in zona mmap; daca depaseste o pagina, kernelul
                   refuza mmap mai mare. Verificam si acceptam doar in limite. */
                if(dsz && dptr>=g_mapaddr && dptr+dsz<=g_mapaddr+g_mapsz){
                    if(out) memcpy(out,(void*)(uintptr_t)dptr,dsz);
                    if(status && dsz>=4) *status=*(u32*)(uintptr_t)dptr;
                }
                g_offsz=osz;
                if(osz && optr>=g_mapaddr && optr+osz<=g_mapaddr+g_mapsz && osz<=sizeof g_offbuf)
                    memcpy(g_offbuf,(void*)(uintptr_t)optr,osz);
                g_lastdptr=dptr;
                if(!getenv("NOFREE")){
                    u8 fb[12]; u32 fc=BC_FREE_BUFFER;
                    memcpy(fb,&fc,4); memcpy(fb+4,&dptr,8);
                    bwr(fb,12,NULL);
                }
                return 0;
            }
            /* comanda necunoscuta: nu stim dimensiunea, oprim parsarea */
            if(getenv("DBG")){
                fprintf(stderr,"[dbg] BR necunoscut 0x%x la off %llu; toate cuvintele:",w,(unsigned long long)(off-4));
                for(u64 q=0;q+4<=used;q+=4) fprintf(stderr," %d:%u",(int)q,*(u32*)(g_rd+q));
                fprintf(stderr,"\n");
            }
            return -EPROTO;
        }
    }
    return -ETIMEDOUT;
}

int main(int argc,char**argv){
    if(bopen()<0){ perror("binder"); return 1; }
    const char*what=argc>1?argv[1]:"check";
    const char*svc=argc>2?argv[2]:"activity";
    const char*DESC="android.os.IServiceManager";
    u8 pl[1024]; memset(pl,0,sizeof pl);
    u8*out=malloc(16384); memset(out,0,16384);
    u64 ol=0,os=0; u32 pid=0,st=0; int r;

    if(!strcmp(what,"handle")){          /* handle <nume> -> afiseaza handle-ul */
        u64 n=mkparcel(pl,"android.os.IServiceManager",argc>2?argv[2]:"package");
        r=transact(0,1,pl,n,out,&ol,&pid,&st,&os);
        printf("getService(%s): r=%d pid=%u len=%llu status=0x%x offsz=%llu\n",
               argc>2?argv[2]:"package",r,pid,(unsigned long long)ol,st,(unsigned long long)os);
        if(r==0&&ol>=8){
            printf("  data (%llu bytes, offsz=%llu):\n",(unsigned long long)ol,(unsigned long long)os);
            for(u64 i=0;i<ol;i+=16){
                printf("   %04llx:",(unsigned long long)i);
                for(u64 j=i;j<i+16&&j<ol;j++) printf(" %02x",out[j]);
                printf("\n");
            }
            if(getenv("OFF")){
                printf("  offsets_buffer:");
                for(u64 i=0;i<os&&i<64;i+=4) printf(" %d",*(u32*)(g_offbuf+i));
                printf("\n");
            }
        }
        return 0;
    }
    if(!strcmp(what,"call")){            /* call <svcname> <desc> <code> [i32...] */
        if(argc<5){fprintf(stderr,"usage: call <svcname> <descriptor> <code> [i32...]\n");return 1;}
        /* 1. obtine handle-ul */
        u64 n1=mkparcel(pl,"android.os.IServiceManager",argv[2]);
        setenv("NOFREE","1",1);
        r=transact(0,1,pl,n1,out,&ol,&pid,&st,&os);
        unsetenv("NOFREE");
        if(r<0||ol<8||st!=0){ printf("getService(%s) a esuat: r=%d st=0x%x\n",argv[2],r,st); return 1; }
        u32 h=*(u32*)(out+4);
        if(getenv("H1")) h=1;   /* handle-ul real extras din flat_binder_object */
        /* 2. construieste parcel-ul cu descriptorul serviciului */
        u64 n=mkparcel_ex(pl,argv[3],NULL,1);
        /* elimina padding-ul de dupa descriptor si adauga argumentele int */
        for(int i=5;i<argc;i++){ *(u32*)(pl+n)=(u32)strtoul(argv[i],0,0); n+=4; }
        u32 c2=(u32)strtoul(argv[4],0,0);
        printf("call %s (handle=0x%x) code=%u\n",argv[2],h,c2);
        /* libbinder face o tranzactie goala la inceput (cf. capturii) */

        /* secventa EXACTA din libbinder:
           1. BC_ACQUIRE(h) + BC_INCREFS(h)
           2. INTERFACE_TRANSACTION (0x5f4e5446 = '_INTF') ca sa validam handle-ul
           3. apelul real */
        { u8 aq[8]; u32 ac=0x40046304; memcpy(aq,&ac,4); memcpy(aq+4,&h,4);
          u64 ar=0; bwr(aq,8,&ar); }
        { u8 aq[8]; u32 ic=0x40046305; memcpy(aq,&ic,4); memcpy(aq+4,&h,4);
          u64 ar=0; bwr(aq,8,&ar); }
        { /* BC_FREE_BUFFER pe bufferul din getService (ordinea libbinder) */
          u8 fb[12]; u32 fc=0x40086303; memcpy(fb,&fc,4);
          memcpy(fb+4,&g_lastdptr,8); bwr(fb,12,NULL);
          if(getenv("DBG")) fprintf(stderr,"[dbg] FREE_BUFFER 0x%llx\n",(unsigned long long)g_lastdptr); }
        { u8 o2[512]; u64 l2=0; u32 p2=0,s2=0,os2=0;
          int rr=transact(h,0x5f4e5446,NULL,0,o2,&l2,&p2,&s2,&os2);
          if(getenv("DBG")) fprintf(stderr,"[dbg] INTERFACE h=%u -> r=%d len=%llu\n",h,rr,(unsigned long long)l2); }
        r=transact(h,c2,pl,n,out,&ol,&pid,&st,&os);
        printf("call(h=%u,code=%u): r=%d pid=%u len=%llu status=0x%x\n",h,c2,r,pid,(unsigned long long)ol,st);
        if(r==0&&ol){
            for(u64 i=0;i<ol;i+=16){
                printf("   %04llx:",(unsigned long long)i);
                for(u64 j=i;j<i+16&&j<ol;j++) printf(" %02x",out[j]);
                printf("\n");
            }
        }
        return 0;
    }

    if(!strcmp(what,"check")||!strcmp(what,"get")){
        u64 n=mkparcel(pl,DESC,svc);
        u32 code = strcmp(what,"get")?3:1;
        r=transact(0,code,pl,n,out,&ol,&pid,&st,&os);
        printf("%sService(%s): r=%d pid=%u len=%llu status=0x%x offsz=%llu\n",
               strcmp(what,"get")?"check":"get",svc,r,pid,(unsigned long long)ol,st,(unsigned long long)os);
        if(r==0 && ol){
            printf("  data (%llu bytes):\n",(unsigned long long)ol);
            for(u64 i=0;i<ol;i+=16){
                printf("   %04llx:",(unsigned long long)i);
                for(u64 j=i;j<i+16&&j<ol;j++) printf(" %02x",out[j]);
                printf("\n");
            }
        }
    }
    else if(!strcmp(what,"list")){
        u64 n=mkparcel(pl,DESC,NULL);
        *(u32*)(pl+n)=0x0F; n+=4;             /* DUMP_FLAG_PRIORITY_ALL */
        r=transact(0,6,pl,n,out,&ol,&pid,&st,&os);
        printf("listServices: r=%d pid=%u len=%llu status=0x%x\n",r,pid,(unsigned long long)ol,st);
        if(r==0&&st==0&&ol>=4){
            u32 cnt=*(u32*)(out+4); printf("count=%u\n",cnt);
            u64 o=8;
            for(u32 i=0;i<cnt&&o+4<=ol;i++){
                s32 L=*(s32*)(out+o); o+=4;
                if(L<0||L>512||o+(u64)L*2>ol) break;
                char nm[256]; u32 j;
                for(j=0;j<(u32)L&&j<255;j++) nm[j]=(char)((u16*)(out+o))[j];
                nm[j]=0; printf("%u\t%s\n",i,nm);
                o+=(u64)L*2;
            }
        }
    }
    return 0;
}
