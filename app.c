#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <signal.h>
#include <stdbool.h>
#include <time.h>
#include <sys/time.h>



#include "clk.h"
#include "gpio.h"
#include "dma.h"
#include "pwm.h"
#include "version.h"

#include "ws2811.h"
#include <math.h>


#include "potato.h"

DEFVAR(color_t, col);
DEFVAR(float, min_width);
DEFVAR(float, max_width);
DEFVAR(float, min_vel);
DEFVAR(float, max_vel);


#define TARGET_FREQ             WS2811_TARGET_FREQ
#define GPIO_PIN                21
#define STRIP_TYPE              WS2811_STRIP_GBR		// WS2812/SK6812RGB integrated chip+leds

#define LED_COUNT               138

ws2811_t ledstring =
{
    .freq = TARGET_FREQ,
    .channel =
    {
        [0] =
        {
            .gpionum = GPIO_PIN,
            .count = LED_COUNT,
            .invert = 0,
            .brightness = 255,
            .strip_type = STRIP_TYPE,
        },
        [1] =
        {
            .gpionum = 0,
            .count = 0,
            .invert = 0,
            .brightness = 0,
        },
    },
};

typedef struct
{
    float pos;
    float vel;
    float blue;
    float green;
    float red;
    int width;
} ball_t;

#define BALL_COUNT 10

#define LED_MAX 0x32

ball_t balls[BALL_COUNT];

static uint8_t running = 1;

float rand_float(float min, float max)
{
    int r = rand();
    float frac = (float)r / (float)RAND_MAX;
    return (min + (max-min) * frac);
}

void ball_init(ball_t *ball)
{
    ball->width = rand_float(min_width, max_width);

    ball->pos = -ball->width / 2;
		
    ball->vel = rand_float(min_vel, max_vel);
		
    if(rand() & 1)
    {
      ball->vel = -ball->vel;
      ball->pos = LED_COUNT + ball->width / 2;
    }

    ball->red = rand_float(0,1);
    ball->green = rand_float(0,1);
    ball->blue = rand_float(0,1);
}

void balls_init(void)
{
    for(int i = 0; i < BALL_COUNT; i++)
		ball_init(&balls[i]);
}


void balls_step(float t)
{
    for(int i = 0; i < BALL_COUNT; i++)
    {
      balls[i].pos += balls[i].vel * t;
      if(balls[i].pos > (LED_COUNT + balls[i].width) ||
         balls[i].pos < (0 - balls[i].width))
      {
          ball_init(&balls[i]);
      }
    }
}

float to_led(float v)
{
    return ((float)LED_MAX) * powf(v, 1.5f);
}

DEFVAR(int, tails);

DEFVAR(int, clock_pos);

void balls_render(ws2811_led_t *leds)
{
  
  struct timeval tv;
  gettimeofday(&tv, NULL);
  
  // 6 hits
  int secs = tv.tv_sec % 60;
  // 6 bits
  int mins = (tv.tv_sec/60) % 60;
  // 5 bits
  int hours = (tv.tv_sec/60/60) % 24;
  
  // total = 17 bits
  // + 4 separators = 21 bits
  
  
    for(int i = 0; i < LED_COUNT; i++)
    {
      float max_r = 0;
      float max_g = 0;
      float max_b = 0;

      for(int j = 0; j < BALL_COUNT; j++)
      {
          float half_width = balls[j].width/2;
          float ball_left = (float)balls[j].pos - half_width;
          float ball_right = (float)balls[j].pos + half_width;

          if(ball_left < i && ball_right > i)
          {
            float ball_frac = ((float)i - ball_left) / balls[j].width;
    		float x = sin(ball_frac * 3.14159f);
            
            if(tails) {
                if(balls[j].vel > 0) ball_frac = 1-ball_frac;
            	x = cos(ball_frac * 3.14159f / 2);
            }

            float r = x * balls[j].red;
            float g = x * balls[j].green;
            float b = x * balls[j].blue;

            if(r > max_r) max_r = r;
            if(g > max_g) max_g = g;
            if(b > max_b) max_b = b;
          }
      }

      int red  = to_led(max_r * col.r);
      int green = to_led(max_g * col.g);
      int blue = to_led(max_b * col.b);
  
      #define CLOCK_LEN 21
      if(i >= clock_pos && i < clock_pos + CLOCK_LEN)
      {
        int clock_bit = clock_pos + CLOCK_LEN - i - 1;//i - clock_pos;
        /* We're in the clock! */
        red = 0;
        green = 0;
        blue = 0;
        if(clock_bit == 0 || clock_bit == 7 || clock_bit == 14 || clock_bit == 20) {
          red = green = blue = to_led(1);
        } else if(clock_bit < 7) {
          /* Seconds */
          int bit = clock_bit - 1;
          green = to_led((secs >> bit) & 1 ? 1.f : 0.f);
        } else if (clock_bit < 14) {
          /* Minutes */
          int bit = clock_bit - 9;
          blue = to_led((mins >> bit) & 1 ? 1.f : 0.f);
        } else if (clock_bit < 20) {
          /* Hours */
          int bit = clock_bit - 17;
          red = to_led((hours >> bit) & 1 ? 1.f : 0.f);
        }
      }
      leds[i] = (blue << 16) | (green << 8) | red;
    }
}

static void ctrl_c_handler(int signum)
{
    (void)(signum);
    running = 0;
}

static void setup_handlers(void)
{
    struct sigaction sa =
	{
	    .sa_handler = ctrl_c_handler,
	};

    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);
}


void init()
{
  setup_handlers();

  ws2811_init(&ledstring);

  srand(time(0));

  balls_init();
}

DEFVAR(int, solid_mode);

void work(float dt)
{
  
  if(solid_mode)
  {
    for(int i = 0; i < LED_COUNT; i++)
    {
      int red  = to_led(col.r);
      int blue = to_led(col.b);
      int green = to_led(col.g);

      ledstring.channel[0].leds[i] = (blue << 16) | (green << 8) | red;
    }
    ws2811_render(&ledstring);
    return;
  }
  
  balls_step(dt/1000);
  balls_render(ledstring.channel[0].leds);
  ws2811_render(&ledstring);
}