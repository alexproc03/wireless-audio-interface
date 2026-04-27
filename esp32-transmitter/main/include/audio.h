#ifndef AUDIO_H
#define AUDIO_H

#include "freertos/FreeRTOS.h"
#include "freertos/ringbuf.h"
#include "esp_err.h"

esp_err_t audio_start(RingbufHandle_t rb);

#endif