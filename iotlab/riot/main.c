/* RIOT glue for the SAGE-DTN testbed node: shell commands from the IoT-LAB serial port,
 * link-local multicast UDP over the 802.15.4 radio, a 100 ms tick thread. */
#include <stdio.h>
#include <string.h>

#include "hashes/sha256.h"
#include "mutex.h"
#include "net/gnrc/netif.h"
#include "net/ipv6/addr.h"
#include "net/sock/udp.h"
#include "shell.h"
#include "thread.h"
#include "ztimer.h"

#include "sage_app.h"

#define SAGE_PORT (61616U)   /* 0xF0B0: compressible by 6LoWPAN NHC */

static sock_udp_t sock;
static mutex_t lock = MUTEX_INIT;
static char rx_stack[THREAD_STACKSIZE_DEFAULT + 1024];
static char tick_stack[THREAD_STACKSIZE_DEFAULT + 2048];

void plat_send(const uint8_t *buf, size_t len)
{
    sock_udp_ep_t remote = { .family = AF_INET6, .port = SAGE_PORT };
    gnrc_netif_t *netif = gnrc_netif_iter(NULL);
    if (netif) {
        remote.netif = netif->pid;
    }
    ipv6_addr_set_all_nodes_multicast((ipv6_addr_t *)&remote.addr.ipv6, IPV6_ADDR_MCAST_SCP_LINK_LOCAL);
    sock_udp_send(&sock, buf, len, &remote);
}

void plat_out(const char *line)
{
    puts(line);
}

uint32_t plat_ms(void)
{
    return ztimer_now(ZTIMER_MSEC);
}

uint32_t plat_us(void)
{
    return ztimer_now(ZTIMER_USEC);
}

void plat_sha256(const void *data, size_t len, uint8_t out[32])
{
    sha256(data, len, out);
}

static void *rx_thread(void *arg)
{
    (void)arg;
    static uint8_t buf[160];
    for (;;) {
        ssize_t n = sock_udp_recv(&sock, buf, sizeof(buf), SOCK_NO_TIMEOUT, NULL);
        if (n > 0) {
            mutex_lock(&lock);
            app_rx(buf, (size_t)n);
            mutex_unlock(&lock);
        }
    }
    return NULL;
}

static void *tick_thread(void *arg)
{
    (void)arg;
    for (;;) {
        ztimer_sleep(ZTIMER_MSEC, 100);
        mutex_lock(&lock);
        app_tick();
        mutex_unlock(&lock);
    }
    return NULL;
}

/* every SAGE command is forwarded to the app as one line */
static int cmd_any(int argc, char **argv)
{
    char line[192];
    size_t n = 0;
    line[0] = '\0';
    for (int i = 0; i < argc && n < sizeof(line); i++) {
        n += snprintf(line + n, sizeof(line) - n, "%s%s", i ? " " : "", argv[i]);
    }
    mutex_lock(&lock);
    app_cmd(line);
    mutex_unlock(&lock);
    return 0;
}

static const shell_command_t commands[] = {
    { "cfg", "configure role/mode: cfg id=<n> role=F|S|X|R grp=<g> mode=A|E|F|H|I ...", cmd_any },
    { "reset", "clear node state", cmd_any },
    { "ph", "set contact phase: ph <phase> <trial_time_s>", cmd_any },
    { "r", "human report: r <TYPE> <key> <urgency>", cmd_any },
    { "s", "sensor sample: s <TYPE> <value_x100>", cmd_any },
    { "st", "print stats", cmd_any },
    { "dump", "print state digest and aggregates", cmd_any },
    { "selftest", "E1 SPL property test: selftest <iterations>", cmd_any },
    { "die", "destroy this node (source loss, E4)", cmd_any },
    { "ping", "liveness", cmd_any },
    { NULL, NULL, NULL }
};

int main(void)
{
    sock_udp_ep_t local = SOCK_IPV6_EP_ANY;
    local.port = SAGE_PORT;
    if (sock_udp_create(&sock, &local, NULL, 0) < 0) {
        puts("@error sock_udp_create");
    }
    app_init();
    thread_create(rx_stack, sizeof(rx_stack), THREAD_PRIORITY_MAIN - 2, 0, rx_thread, NULL, "sage_rx");
    thread_create(tick_stack, sizeof(tick_stack), THREAD_PRIORITY_MAIN - 1, 0, tick_thread, NULL, "sage_tick");

    static char line_buf[SHELL_DEFAULT_BUFSIZE * 2];
    shell_run(commands, line_buf, sizeof(line_buf));
    return 0;
}
