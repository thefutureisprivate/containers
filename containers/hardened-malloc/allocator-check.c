#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Fail if a loader silently ignores LD_PRELOAD or selects another allocator. */
int main(void) {
    Dl_info provider;
    void *symbol = dlsym(RTLD_DEFAULT, "malloc");
    if (!symbol || !dladdr(symbol, &provider) || !provider.dli_fname ||
        !strstr(provider.dli_fname, "/libhardened_malloc.so")) {
        fputs("hardened_malloc is not the active malloc provider\n", stderr);
        return 1;
    }
    for (size_t n = 1; n < 65536; n *= 2) {
        unsigned char *p = calloc(n, 1);
        if (!p) return 2;
        for (size_t i = 0; i < n; ++i) if (p[i]) return 3;
        memset(p, 42, n);
        unsigned char *q = realloc(p, n * 2);
        if (!q) return 4;
        for (size_t i = 0; i < n; ++i) if (q[i] != 42) return 5;
        free(q);
    }
    puts("Active malloc provider: hardened_malloc; allocation checks passed");
    return 0;
}
