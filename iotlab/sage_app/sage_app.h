/* SAGE-DTN testbed node application (one binary for every role).
 *
 * The same logic runs on FIT IoT-LAB M3 nodes (RIOT OS, IEEE 802.15.4 radio) and on the host
 * (UDP on localhost) so the whole experiment pipeline can be tested without hardware.
 * The platform glue (riot/main.c, host/host_main.cpp) provides the plat_* functions and calls
 * app_cmd() for every input line, app_rx() for every received datagram and app_tick() every 100 ms.
 */
#ifndef SAGE_APP_H
#define SAGE_APP_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* provided by the platform */
void plat_send(const uint8_t *buf, size_t len);   /* one-hop broadcast */
void plat_out(const char *line);                  /* print one line (newline added) */
uint32_t plat_ms(void);
uint32_t plat_us(void);
void plat_sha256(const void *data, size_t len, uint8_t out[32]);

/* provided by the app */
void app_init(void);
void app_cmd(const char *line);
void app_rx(const uint8_t *buf, size_t len);
void app_tick(void);

#ifdef __cplusplus
}
#endif

#endif /* SAGE_APP_H */
