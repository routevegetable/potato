#include "kernel.h"
#include <stdio.h>


/* Live Coding Variables */
DEFVAR(float, position, 0);
DEFVAR(float, velocity, 0);
DEFVAR(int, haha2, 0);




void init()
{
	printf("HELLO!\n");
}

void work(float dt)
{
    printf("dt: %f position: %f velocity: %f haha: %d\n", dt, position, velocity, haha2);
}
