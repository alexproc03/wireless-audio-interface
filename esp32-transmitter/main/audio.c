#include "audio.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "driver/i2s_std.h"
#include "driver/uart.h"
#include "esp_err.h"
#include <string.h>

extern i2s_chan_handle_t rx_handle;

static uint8_t buffer[2048];

static void audio_task(void *arg)
{
    RingbufHandle_t rb = (RingbufHandle_t)arg;

    size_t bytes_read;
    static int16_t mono_buf[1024];
    static uint8_t packet_buf[4 + sizeof(mono_buf)];
    static uint32_t sequence = 0;

    while (1) {
        if (i2s_channel_read(rx_handle, buffer, sizeof(buffer),
                             &bytes_read, portMAX_DELAY) == ESP_OK) {
            int16_t *samples = (int16_t *)buffer;
            int n = bytes_read / 2;
            int mono_n = 0;

            for (int i = 1; i < n; i += 2) {
                mono_buf[mono_n++] = samples[i];
            }

            uart_write_bytes(UART_NUM_0, (char *)mono_buf, mono_n * 2);

            uint32_t seq = sequence++;
            size_t payload_bytes = mono_n * sizeof(int16_t);
            size_t packet_len = 4 + payload_bytes;

            packet_buf[0] = (seq >> 24) & 0xFF;
            packet_buf[1] = (seq >> 16) & 0xFF;
            packet_buf[2] = (seq >> 8) & 0xFF;
            packet_buf[3] = seq & 0xFF;

            memcpy(packet_buf + 4, mono_buf, payload_bytes);

            xRingbufferSend(rb, packet_buf, packet_len, 0);
        }
    }
}

esp_err_t audio_start(RingbufHandle_t rb)
{
    if (rb == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    BaseType_t ok = xTaskCreate(
        audio_task,
        "audio",
        4096,
        (void *)rb,
        5,
        NULL
    );

    return (ok == pdPASS) ? ESP_OK : ESP_FAIL;
}