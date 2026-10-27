#pragma once
inline int mbedtls_sha256(const unsigned char*, size_t, unsigned char* out, int) { for (int i = 0; i < 32; i++) out[i] = (unsigned char)i; return 0; }
