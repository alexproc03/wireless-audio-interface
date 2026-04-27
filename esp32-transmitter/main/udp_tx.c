#include "udp_tx.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "lwip/sockets.h"
#include "lwip/inet.h"

#include "esp_log.h"
#include "string.h"
#include "stdlib.h"
#include "errno.h"

#define UDP_TX_TASK_STACK_SIZE 4096
#define UDP_TX_TASK_PRIORITY   4

typedef struct {
    RingbufHandle_t rb;
    char dest_ip[16];
    uint16_t dest_port;
} udp_tx_ctx_t;

static const char *TAG = "udp_tx";

static void udp_tx_task(void *arg)
{
    udp_tx_ctx_t *ctx = (udp_tx_ctx_t *)arg;

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "socket creation failed: errno=%d", errno);
        free(ctx);
        vTaskDelete(NULL);
        return;
    }

    struct sockaddr_in dest_addr = {
        .sin_family = AF_INET,
        .sin_port = htons(ctx->dest_port),
        .sin_addr.s_addr = inet_addr(ctx->dest_ip),
    };

    while (1) {
        size_t item_size = 0;
        void *item = xRingbufferReceive(ctx->rb, &item_size, portMAX_DELAY);

        if (item != NULL) {
            int err = sendto(
                sock,
                item,
                item_size,
                0,
                (struct sockaddr *)&dest_addr,
                sizeof(dest_addr)
            );

            if (err < 0) {
                ESP_LOGE(TAG, "sendto failed: errno=%d", errno);
            }

            vRingbufferReturnItem(ctx->rb, item);
        }
    }
}

esp_err_t udp_tx_start(RingbufHandle_t rb, const char *dest_ip, uint16_t dest_port)
{
    if (rb == NULL || dest_ip == NULL || dest_port == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    udp_tx_ctx_t *ctx = malloc(sizeof(udp_tx_ctx_t));
    if (ctx == NULL) {
        return ESP_ERR_NO_MEM;
    }

    ctx->rb = rb;
    ctx->dest_port = dest_port;

    strncpy(ctx->dest_ip, dest_ip, sizeof(ctx->dest_ip) - 1);
    ctx->dest_ip[sizeof(ctx->dest_ip) - 1] = '\0';

    BaseType_t ok = xTaskCreate(
        udp_tx_task,
        "udp_tx",
        UDP_TX_TASK_STACK_SIZE,
        ctx,
        UDP_TX_TASK_PRIORITY,
        NULL
    );

    if (ok != pdPASS) {
        free(ctx);
        return ESP_FAIL;
    }

    return ESP_OK;
}