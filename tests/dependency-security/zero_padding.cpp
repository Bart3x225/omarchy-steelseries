// Compile against the REAL upstream production header and result types.
// Only HIDAPI is stubbed; the stub copies every requested byte (ASan checks reads).
#include "lib/devices/hid_interface.hpp"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdio>
#include <vector>

static std::vector<unsigned char> packet;
static bool fail_write = false;
static int calls = 0;
int hid_write(hid_device*, const unsigned char* data, size_t size) {
    ++calls;
    packet.clear();
    for (size_t i = 0; i < size; ++i) packet.push_back(data[i]);
    return fail_write ? -1 : static_cast<int>(size);
}
int hid_send_feature_report(hid_device* h, const unsigned char* d, size_t n) {
    return hid_write(h, d, n);
}
int hid_read_timeout(hid_device*, unsigned char*, size_t, int) { return -1; }
int hid_get_feature_report(hid_device*, unsigned char*, size_t) { return -1; }
int hid_get_input_report(hid_device*, unsigned char*, size_t) { return -1; }

int main() {
    headsetcontrol::RealHIDInterface real;
    headsetcontrol::HIDInterface& hid = real; // production virtual overload
    for (bool feature : {false, true}) {
        auto write = [&](std::span<const uint8_t> data, size_t size) {
            return feature ? hid.sendFeatureReport(nullptr, data, size)
                           : hid.write(nullptr, data, size);
        };
        // Adjacent canary makes padding failure deterministic even without ASan.
        std::array<uint8_t, 64> adjacent;
        adjacent.fill(0xa5);
        adjacent[0] = 0x06; adjacent[1] = 0x39; adjacent[2] = 0x01;
        for (size_t n : {2u, 3u}) {
            assert(write(std::span<const uint8_t>(adjacent.data(), n), 64));
            assert(packet.size() == 64);
            assert(std::equal(packet.begin(), packet.begin() + n, adjacent.begin()));
            for (size_t i = n; i < 64; ++i) assert(packet[i] == 0);
        }
        // Exact short allocation: an unfixed overload reads beyond its extent.
        const auto short_data = std::vector<uint8_t>{0x06, 0x39, 0x01};
        assert(write(short_data, 64));
        assert(packet[0] == 0x06 && packet[1] == 0x39 && packet[2] == 0x01);
        for (size_t i = 3; i < 64; ++i) assert(packet[i] == 0);
        assert(write(short_data, 3));
        assert(packet == short_data);
        assert(write(short_data, 2)); // preserve explicit truncation semantics
        assert((packet == std::vector<uint8_t>{0x06, 0x39}));
        assert(write({}, 64));
        assert(packet == std::vector<uint8_t>(64, 0));
        assert(write({}, 0));
        assert(packet.empty());
        fail_write = true;
        assert(write(short_data, 64).hasError());
        fail_write = false;
    }
    const std::array<uint8_t, 3> normal{1, 2, 3};
    assert(hid.write(nullptr, normal));
    assert((packet == std::vector<uint8_t>{1, 2, 3}));
    assert(hid.sendFeatureReport(nullptr, normal));
    assert((packet == std::vector<uint8_t>{1, 2, 3}));
    assert(calls > 0);
    std::puts("PASS: real HID overloads preserve payload, zero-pad, handle errors; no hardware");
}
