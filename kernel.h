#pragma once

void init();

void work(float dt);

void __var_set_ptr(char *name, char* type, void *ptr);

typedef struct {
    char r;
    char g;
    char b;
} color_t;


#define DEFVAR(type, name, def)                                         \
    static type name;                                                   \
    void __setup_##name(void) __attribute__((constructor));             \
    void __setup_##name()                                               \
    {                                                                   \
        name = def;                                                     \
        __var_set_ptr(#name, #type, &name);                             \
    }
