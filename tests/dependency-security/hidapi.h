// Test-only HIDAPI boundary: no implementation can access hardware.
#pragma once
#include <cstddef>
struct hid_device_;
using hid_device = hid_device_;
int hid_write(hid_device*, const unsigned char*, size_t);
int hid_read_timeout(hid_device*, unsigned char*, size_t, int);
int hid_send_feature_report(hid_device*, const unsigned char*, size_t);
int hid_get_feature_report(hid_device*, unsigned char*, size_t);
int hid_get_input_report(hid_device*, unsigned char*, size_t);
