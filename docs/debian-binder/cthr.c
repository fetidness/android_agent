
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
static double now(){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static void* w(void*a){volatile long s=0;for(long i=0;i<20000000L;i++)s+=i%7;(void)s;return 0;}
int main(){int ns[3]={1,4,8};for(int k=0;k<3;k++){int n=ns[k];pthread_t*p=malloc(sizeof(pthread_t)*n);double s=now();for(int i=0;i<n;i++)pthread_create(&p[i],0,w,0);for(int i=0;i<n;i++)pthread_join(p[i],0);printf("C_thr%d %.3f\n",n,now()-s);free(p);}return 0;}
