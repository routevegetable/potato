#include "potato.h"
#include <stdio.h>


/* Live Coding Variables */
DEFVAR(float, position);
DEFVAR(float, velocity);
DEFVAR(int, haha2);


void init()
{
	printf("HELLO!\n");
}

void work(float dt)
{
    printf("dt: %f position: %f velocity: %f haha: %d\n", dt, position, velocity, haha2);
}
