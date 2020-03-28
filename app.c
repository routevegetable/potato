#include "kernel.h"
#include <stdio.h>


/* Live Coding Variables */
DEFVAR(float, position);
DEFVAR(float, velocity);
DEFVAR(int, haha2);
DEFVAR(color_t, col);


void init()
{
	printf("HELLO!\n");
}

void work(float dt)
{
    printf("position: %f velocity: %f haha2: %d\n", position, velocity, haha2);
  printf("Red: %d Green: %d Blue: %d\n", col.r, col.g, col.b);
}
