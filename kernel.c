#include "kernel.h"

#include <stdlib.h>
#include <stdio.h>
#include <sys/time.h>
#include <sys/types.h>
#include <unistd.h>
#include <assert.h>
#include <string.h>
#include <stdbool.h>
#include <time.h>

#define VARS_MAX 256


typedef void (*var_decoder_t)(void *target, char *new_value);

struct var_t
{
    char *name;
    void *ptr;
    var_decoder_t decoder;

} vars[VARS_MAX];

static int n_vars = 0;

static struct var_t* s_get_var(char *name)
{
    for(int i = 0; i < n_vars; i++)
    {
        if(!strcmp(name, vars[i].name))
        {
            return &vars[i];
        }
    }

    return NULL;
}

static void s_float_decoder(void *target, char *new_value) { *(float*)target = atof(new_value); }
static void s_int_decoder(void *target, char *new_value) { *(int*)target = atof(new_value); }
static void s_long_decoder(void *target, char *new_value) { *(long*)target = atol(new_value); }
static void s_double_decoder(void *target, char *new_value) { *(double*)target = atof(new_value); }
static void s_string_decoder(void *target, char *new_value)
{
    char **target_s = target;
    if(*target_s) free(*target_s);
    *target_s = strdup(new_value);
}

static void s_color_decoder(void *target, char *new_value)
{
    color_t *target_c = target;

    int cint = atoi(new_value);
    target_c->r = (cint >> 0) & 0xFF;
    target_c->g = (cint >> 8) & 0xFF;
    target_c->b = (cint >> 16) & 0xFF;
}

void __var_set_ptr(char *name, char *type, void *ptr)
{
    printf("Setup var: %s, type: %s\n", name, type);
    struct var_t *var = &vars[n_vars++];
    var->name = name;
    var->ptr = ptr;
    if(!strcmp(type, "float"))
        var->decoder = s_float_decoder;
    else if(!strcmp(type, "int"))
        var->decoder = s_int_decoder;
    else if(!strcmp(type, "long"))
        var->decoder = s_long_decoder;
    else if(!strcmp(type, "double"))
        var->decoder = s_double_decoder;
    else if(!strcmp(type, "char*"))
        var->decoder = s_string_decoder;
    else if(!strcmp(type, "color_t"))
        var->decoder = s_color_decoder;
    else
        var->decoder = NULL;
}

/**
 * Handle any waiting command blocks.
 * Message format: name\nvalue\nname\nvalue\n\n
 */
static void s_handle_commands(bool block)
{
    FILE* fp = stdin;
    int fd = fileno(stdin);

    fd_set fds;
    FD_ZERO(&fds);
    FD_SET(fd, &fds);

    struct timeval timeout;
    timeout.tv_sec = 0;
    timeout.tv_usec = 0;
    int ret;
    while((ret = select(1, &fds, NULL, NULL, block ? NULL : &timeout)) == 1)
    {
        /* Incomming command block */

        size_t len = 0;
        char *name = NULL;
        ssize_t line_ret;
        while((line_ret = getline(&name, &len, stdin)) > 1)
        {
            /* Got name line */
            /* Remove newline */
            name[strlen(name)-1] = '\0';

            /* Snip type off of name */
            struct var_t *var = s_get_var(&name[0]);

            /* Read value line */
            char *value = NULL;
            len = 0;
            assert(getline(&value, &len, stdin) >= 1);

            value[strlen(value)-1] = '\0';

            if(var && var->decoder)
            {
                var->decoder(var->ptr, value);
            }

            free(name);
            free(value);
            len = 0;
        }

        /* Got empty line - finished command block */
        free(name);

        if(block)
            break;
    }

    if(ret == -1)
    {
        perror("Error waiting for command block");
        exit(1);
    }
}

DEFVAR(float, fps);


static long s_get_time_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC,&ts);
    return (ts.tv_sec * 1000) + (ts.tv_nsec / 1000000L);
}

int main()
{
    s_handle_commands(true);

    init();

    long last_time = s_get_time_ms();
    long time_left = 0;
    while(1)
    {
        float period_ms = 1000.0f / fps;

        long current_time = s_get_time_ms();
        time_left += current_time - last_time;
        last_time = current_time;

        /* Wait until another period has passed */
        while(time_left < period_ms)
        {
            /* Wait a tenth of the period */
            usleep(period_ms*100);

            current_time = s_get_time_ms();
            time_left += current_time - last_time;
            last_time = current_time;
        }

        /* Do the work for this period */
        work(period_ms);
        time_left -= period_ms;

        s_handle_commands(false);
    }
}
