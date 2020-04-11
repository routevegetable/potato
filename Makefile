app: potato.h potato.c app.c
	gcc -Og -g3 potato.c app.c libws2811.a -lm -o app
