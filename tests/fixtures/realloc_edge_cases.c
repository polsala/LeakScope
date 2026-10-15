#include <stdlib.h>
#include <stdint.h>
#include <string.h>
int main(void){
    char *p=realloc(NULL,32);if(!p)return 1;memset(p,7,32);
    char *q=realloc(p,4096);if(!q){free(p);return 2;}p=q;
    volatile size_t impossible=SIZE_MAX-4096;
    q=realloc(p,impossible);if(q){free(q);return 3;}
    if(p[0]!=7){free(p);return 4;}free(p);free(NULL);
    p=malloc(12);if(!p)return 5;q=realloc(p,0);if(q)free(q);
    return 0;
}
