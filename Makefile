app: kernel.h kernel.c app.c
	gcc -Og -g3 kernel.c app.c -o app
