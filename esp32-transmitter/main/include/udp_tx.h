#ifndef UDP_TX_H
#define UDP_TX_H

#include "freertos/ringbuf.h"
#include "esp_err.h"
#include <stdint.h>

esp_err_t udp_tx_start(RingbufHandle_t rb, const char *dest_ip, uint16_t dest_port);

#endif