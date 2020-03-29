#pragma once

void init();

void work(float dt);

void __var_set_ptr(char *name, char* type, void *ptr);

typedef struct {
    float r;
    float g;
    float b;
} color_t;


#define DEFVAR(type, name)                                              \
    static type name;                                                   \
    void __setup_##name(void) __attribute__((constructor));             \
    void __setup_##name()                                               \
    {                                                                   \
        __var_set_ptr(#name, #type, &name);                             \
    }
