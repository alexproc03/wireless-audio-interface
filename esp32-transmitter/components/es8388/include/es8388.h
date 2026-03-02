#ifndef ES8388_H
#define ES8388_H

#include "driver/i2c_master.h"
#include "esp_err.h"

esp_err_t es8388_init(void);
esp_err_t es8388_write_reg(uint8_t reg, uint8_t data);
esp_err_t es8388_read_reg(uint8_t reg, uint8_t *data);

#endif