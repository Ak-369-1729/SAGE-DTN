// Host build of the SAGE-DTN testbed node, for testing the IoT-LAB pipeline without hardware.
// Each process is one node. "Radio" = UDP datagrams on 127.0.0.1 to every other node's port,
// with optional random loss. Commands arrive on stdin, output goes to stdout (one line each).
//
//   host_node <index> <num_nodes> [base_port=47000] [loss=0.0]
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <string>
#include "../sage_app/sage_app.h"

static int g_sock = -1, g_idx = 0, g_n = 1, g_base = 47000;
static double g_loss = 0.0;
static std::mt19937 g_rng;
static const auto g_t0 = std::chrono::steady_clock::now();

extern "C" void plat_send(const uint8_t* buf, size_t len) {
  std::uniform_real_distribution<double> u(0, 1);
  for (int k = 0; k < g_n; k++) {
    if (k == g_idx || u(g_rng) < g_loss) continue;
    sockaddr_in a{}; a.sin_family = AF_INET; a.sin_port = htons(g_base + k); a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    sendto(g_sock, buf, len, 0, (sockaddr*)&a, sizeof a);
  }
}
extern "C" void plat_out(const char* line) { fputs(line, stdout); fputc('\n', stdout); fflush(stdout); }
extern "C" uint32_t plat_us(void) {
  return (uint32_t)std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - g_t0).count();
}
extern "C" uint32_t plat_ms(void) {
  return (uint32_t)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - g_t0).count();
}

// Minimal SHA-256 (FIPS 180-4) so the host build has no dependencies; RIOT uses its hashes module.
namespace {
const uint32_t K[64] = {
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
inline uint32_t ror(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
void block(uint32_t h[8], const uint8_t* p) {
  uint32_t w[64];
  for (int i = 0; i < 16; i++) w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 | (uint32_t)p[4 * i + 2] << 8 | p[4 * i + 3];
  for (int i = 16; i < 64; i++) {
    uint32_t s0 = ror(w[i - 15], 7) ^ ror(w[i - 15], 18) ^ (w[i - 15] >> 3), s1 = ror(w[i - 2], 17) ^ ror(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
  for (int i = 0; i < 64; i++) {
    uint32_t t1 = hh + (ror(e, 6) ^ ror(e, 11) ^ ror(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i];
    uint32_t t2 = (ror(a, 2) ^ ror(a, 13) ^ ror(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
    hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
  }
  h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
}
}  // namespace

extern "C" void plat_sha256(const void* data, size_t len, uint8_t out[32]) {
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  const uint8_t* p = (const uint8_t*)data; size_t n = len;
  while (n >= 64) { block(h, p); p += 64; n -= 64; }
  uint8_t last[128] = {0}; memcpy(last, p, n); last[n] = 0x80;
  size_t tot = n + 9 <= 64 ? 64 : 128; uint64_t bits = (uint64_t)len * 8;
  for (int i = 0; i < 8; i++) last[tot - 1 - i] = (uint8_t)(bits >> (8 * i));
  block(h, last); if (tot == 128) block(h, last + 64);
  for (int i = 0; i < 8; i++) for (int j = 0; j < 4; j++) out[4 * i + j] = (uint8_t)(h[i] >> (24 - 8 * j));
}

int main(int argc, char** argv) {
  if (argc < 3) { fprintf(stderr, "usage: %s <index> <num_nodes> [base_port] [loss]\n", argv[0]); return 2; }
  g_idx = atoi(argv[1]); g_n = atoi(argv[2]);
  if (argc > 3) g_base = atoi(argv[3]);
  if (argc > 4) g_loss = atof(argv[4]);
  g_rng.seed(1000 + g_idx);
  if (getenv("SAGE_SHA_SELFTEST")) {   // FIPS 180-2 test vector "abc"
    uint8_t d[32]; plat_sha256("abc", 3, d);
    for (int i = 0; i < 32; i++) printf("%02x", d[i]);
    printf("\n"); return 0;
  }
  g_sock = socket(AF_INET, SOCK_DGRAM, 0);
  sockaddr_in a{}; a.sin_family = AF_INET; a.sin_port = htons(g_base + g_idx); a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (bind(g_sock, (sockaddr*)&a, sizeof a) < 0) { perror("bind"); return 1; }
  app_init();
  std::string acc; uint32_t lastTick = 0; bool eof = false;
  for (;;) {
    fd_set rf; FD_ZERO(&rf); FD_SET(g_sock, &rf); if (!eof) FD_SET(0, &rf);
    timeval tv{0, 20000};
    if (select(g_sock + 1, &rf, nullptr, nullptr, &tv) > 0) {
      if (FD_ISSET(g_sock, &rf)) { uint8_t buf[256]; ssize_t n = recv(g_sock, buf, sizeof buf, 0); if (n > 0) app_rx(buf, (size_t)n); }
      if (!eof && FD_ISSET(0, &rf)) {
        char buf[512]; ssize_t n = read(0, buf, sizeof buf);
        if (n <= 0) { eof = true; break; }
        for (ssize_t i = 0; i < n; i++) { if (buf[i] == '\n') { app_cmd(acc.c_str()); acc.clear(); } else acc += buf[i]; }
      }
    }
    if (plat_ms() - lastTick >= 100) { lastTick = plat_ms(); app_tick(); }
  }
  return 0;
}
