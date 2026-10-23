
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/wait.h>
static double now(){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
int main(){
  double s;
  volatile long acc=0;
  s=now(); for(long i=0;i<400000000L;i++) acc+=i%7; printf("C int_loop_400M %.4f\n",now()-s);
  s=now(); volatile double d=0; for(long i=0;i<100000000L;i++) d+=(double)i*0.5; printf("C float_loop_100M %.4f\n",now()-s);
  size_t N=256u<<20; char*a=malloc(N),*b=malloc(N); memset(a,1,N); memset(b,2,N);
  s=now(); for(size_t i=0;i<N;i++) a[i]+=b[i]; printf("C memcpy_add_256MB %.4f\n",now()-s);
  s=now(); for(int r=0;r<2000;r++){int p[2];socketpair(AF_UNIX,SOCK_STREAM,0,p);write(p[1],"x",1);read(p[0],a,1);close(p[0]);close(p[1]);} printf("C socketpair_2000 %.4f\n",now()-s);
  s=now(); for(int i=0;i<500;i++){pid_t p=fork(); if(p==0)_exit(0); waitpid(p,0,0);} printf("C fork_wait_500 %.4f\n",now()-s);
  s=now(); for(int i=0;i<200000;i++) (void)getpid(); printf("C getpid_200k %.4f\n",now()-s);
  FILE*f=fopen("./cbench.bin","wb"); for(int i=0;i<256;i++) fwrite(a,1<<20,1,f); fclose(f);
  s=now(); f=fopen("./cbench.bin","rb"); size_t t=0; while(fread(b,65536,1,f)==1) t++; fclose(f); unlink("./cbench.bin");
  printf("C read_256MB %.4f\n",now()-s);
  free(a);free(b); return 0;}
