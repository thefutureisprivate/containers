#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Fail if a loader silently ignores LD_PRELOAD or selects another allocator. */
int main(int argc, char **argv) {
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
    if (argc == 2 && strcmp(argv[1], "--pid1") == 0) {
        FILE *maps = fopen("/proc/1/maps", "r");
        char line[4096];
        int found = 0;
        if (!maps) return 6;
        while (fgets(line, sizeof(line), maps))
            if (strstr(line, "/libhardened_malloc.so")) found = 1;
        fclose(maps);
        if (!found) {
            fputs("PID 1 has not loaded hardened_malloc\n", stderr);
            return 7;
        }
        puts("PID 1 has loaded hardened_malloc");
    }
    return 0;
}
