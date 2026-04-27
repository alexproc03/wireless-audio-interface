#include "es8388.h"
#include "es8388_regs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "i2c_handles.h"

#define ES8388_WRITE_MAX_RETRIES 50

// TODO: Actually tune this. This was ripped from official es8388 examples/docs
esp_err_t es8388_init(void) {
    int res = 0;

    // Match M5Stack reference exactly
    res |= es8388_write_reg(0x08, 0x00);  // Slave mode
    res |= es8388_write_reg(0x02, 0xFF);  // Power down all
    res |= es8388_write_reg(0x2B, 0x80);  // DACCONTROL21: shared LRCK
    res |= es8388_write_reg(0x00, 0x05);  // CONTROL1: EnRef, VMIDSEL=01
    res |= es8388_write_reg(0x01, 0x40);  // CONTROL2: LPVcmMod

    // ADC
    res |= es8388_write_reg(0x03, 0x00);  // ADC power up all
    res |= es8388_write_reg(0x0A, 0x00);  // LIN1/RIN1
    res |= es8388_write_reg(0x0B, 0x00);  // Stereo
    res |= es8388_write_reg(0x09, 0x00);  // PGA +24dB
    res |= es8388_write_reg(0x0C, 0x2C);  // I2S 16-bit, ADCLRP=1
    res |= es8388_write_reg(0x0D, 0x02);  // MCLK/256
    res |= es8388_write_reg(0x0F, 0x28);  // ADC soft ramp
    res |= es8388_write_reg(0x10, 0x00);  // LADCVOL 0dB
    res |= es8388_write_reg(0x11, 0x00);  // RADCVOL 0dB

    // ALC
    res |= es8388_write_reg(0x12, 0xEA);  // ALC stereo, max/min gain
    res |= es8388_write_reg(0x13, 0xC0);  // ALC level/hold
    res |= es8388_write_reg(0x14, 0x12);  // ALC decay/attack
    res |= es8388_write_reg(0x15, 0x00);  // ALC mode
    res |= es8388_write_reg(0x16, 0xC3);  // Noise gate

    // Start
    res |= es8388_write_reg(0x02, 0x00);  // Power up all

    vTaskDelay(pdMS_TO_TICKS(100));
    return (res == 0) ? ESP_OK : ESP_FAIL;
}

esp_err_t es8388_read_reg(uint8_t reg, uint8_t *data) {
    return i2c_master_transmit_receive(es8388_handle, &reg, 1, data, 1, 1000);
}

esp_err_t es8388_write_reg(uint8_t reg, uint8_t data) {
    uint8_t frame[2] = {reg, data};
    esp_err_t status = ESP_FAIL;

    // Retries because I2C writes NACK after I2S init for some reason
    for (int i = 0; i < ES8388_WRITE_MAX_RETRIES; i++) {
        i2c_master_bus_reset(bus_handle);
        status = i2c_master_transmit(es8388_handle, frame, 2, 5000);
        if (status == ESP_OK) break;
        vTaskDelay(pdMS_TO_TICKS(100));
    }

    if (status != ESP_OK) {
        printf("I2C write failed: reg=0x%02X data=0x%02X err=%d\n",
               reg, data, status);
    }

    return status;
}