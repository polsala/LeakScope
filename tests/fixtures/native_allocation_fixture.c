#include <stdlib.h>
#include <string.h>
#include <stdio.h>
/* Ground truth is maintained by the fixture, never inferred from RSS. */
int main(void) {
    void *blocks[1000]; size_t retained=0;
    for(size_t i=0;i<1000;i++){blocks[i]=malloc(4096);if(!blocks[i])return 2;memset(blocks[i],1,4096);}
    for(size_t i=0;i<1000;i++){if(i%10==0)retained+=4096;else free(blocks[i]);}
    printf("{\"fixture_retained_bytes\":%zu,\"fixture_retained_blocks\":100}\n",retained);
    for(size_t i=0;i<1000;i+=10)free(blocks[i]);
    return retained==409600?0:1;
}
