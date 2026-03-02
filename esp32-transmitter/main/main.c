#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "driver/uart.h"
#include "esp_timer.h"

#include "es8388.h"
#include "i2c_handles.h"
                            // M5 BUS PIN
#define SDA_PIN         9   // 17idf.
#define SCL_PIN         10   // 18
                        
#define I2S_LRCK_PIN    7   // 21
#define I2S_SCLK_PIN    5   // 22
#define I2S_MCLK_PIN    4   // 24
#define I2S_DIN_PIN     24  // 26

#define I2S_SAMPLE_RATE 44100
#define I2C_SCL_SPEED   100000

#define ES8388_ADDR     0x10
#define STM32_ADDR      0x33

i2c_master_bus_handle_t bus_handle;
i2c_master_dev_handle_t es8388_handle;
i2c_master_dev_handle_t stm32_handle;
i2s_chan_handle_t rx_handle;

static uint8_t buffer[2048];

void i2c_init(void) {
    // Master
    i2c_master_bus_config_t i2c_mst_config = {
        .clk_source = I2C_CLK_SRC_XTAL,
        .i2c_port = I2C_NUM_0,
        .scl_io_num = SCL_PIN,
        .sda_io_num = SDA_PIN,
        .glitch_ignore_cnt = 7,
        // Keep this false and provide pull up resistors on the line
        .flags.enable_internal_pullup = false, 
    };

    // ES8388
    i2c_device_config_t es8388_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = ES8388_ADDR,
        .scl_speed_hz = I2C_SCL_SPEED,
    };

    // STM32
    i2c_device_config_t stm32_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = STM32_ADDR,
        .scl_speed_hz = I2C_SCL_SPEED,
    };

    ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_mst_config, &bus_handle));
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus_handle, &es8388_cfg, &es8388_handle));
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus_handle, &stm32_cfg, &stm32_handle));
}

void i2s_init(void) {

    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_AUTO, I2S_ROLE_MASTER);
    i2s_new_channel(&chan_cfg, NULL, &rx_handle);

    i2s_std_config_t std_cfg = {
        .clk_cfg = {
            .sample_rate_hz = I2S_SAMPLE_RATE,
            .clk_src = I2S_CLK_SRC_DEFAULT,
            .mclk_multiple = I2S_MCLK_MULTIPLE_256,
        },
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_MCLK_PIN,
            .bclk = I2S_SCLK_PIN,
            .ws = I2S_LRCK_PIN,
            .dout = I2S_GPIO_UNUSED,
            .din = I2S_DIN_PIN,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv = false,
            },
        },
    };

    i2s_channel_init_std_mode(rx_handle, &std_cfg);
    i2s_channel_enable(rx_handle);
}

void app_main(void)
{
    esp_log_level_set("*", ESP_LOG_NONE);
    uart_driver_install(UART_NUM_0, 2048, 8192, 0, NULL, 0);
    uart_set_baudrate(UART_NUM_0, 2000000);

    // Initialize all peripherals
    i2c_init();
    ESP_ERROR_CHECK(i2c_master_probe(bus_handle, ES8388_ADDR, -1));
    i2s_init();
    vTaskDelay(pdMS_TO_TICKS(500));
    es8388_init();

    // Stream
    size_t bytes_read;
    static int16_t mono_buf[1024];

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
        }
    }
}