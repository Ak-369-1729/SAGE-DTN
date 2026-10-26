// Minimal host stub of the Arduino API, used only to compile-check the sketches with g++.
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cmath>
#include <string>
#include <algorithm>
using std::min; using std::max;
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
inline unsigned long millis() { static unsigned long t = 0; return t += 100; }
inline int analogRead(int) { return 2048; }
inline void analogReadResolution(int) {}
inline int digitalRead(int) { return 1; }
inline void digitalWrite(int, int) {}
inline void pinMode(int, int) {}
inline void delay(unsigned long) {}
template <class T> T constrain(T x, T a, T b) { return x < a ? a : (x > b ? b : x); }
class String : public std::string { public: using std::string::string; String(const std::string& s) : std::string(s) {}
  bool startsWith(const char* p) const { return rfind(p, 0) == 0; } String substring(size_t a) const { return String(std::string::substr(a)); }
  long toInt() const { return atol(c_str()); } String& operator+=(char c) { push_back(c); return *this; } };
struct SerialStub { void begin(long) {} int available() { return 0; } int read() { return -1; } String readStringUntil(char) { return String(""); }
  void println(const char* s) { puts(s); } void print(const char* s) { fputs(s, stdout); }
  template <class... A> void printf(const char* f, A... a) { ::printf(f, a...); } };
static SerialStub Serial;
