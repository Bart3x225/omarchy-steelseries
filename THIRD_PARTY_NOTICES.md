# Third-party dependencies and protocol references

The plugin's own source is MIT licensed. That license does not relicense any third-party dependency or trademark.

## HeadsetControl

https://github.com/Sapd/HeadsetControl

The optional headset backend is a separate GPLv3 program. Its complete license is at https://github.com/Sapd/HeadsetControl/blob/master/license. The setup tool builds an immutable source revision locally and retains its source/license and provenance outside the plugin repository. This repository and its GitHub release do not redistribute a compiled HeadsetControl binary. Anyone redistributing their own compiled dependency must meet its applicable license obligations; the plugin's MIT license does not waive them.

## rivalcfg

https://github.com/flozz/rivalcfg

Optional experimental Aerox controls use rivalcfg 4.17.0 as an installed dependency, not a vendored copy. That distribution declares WTFPL; see https://github.com/flozz/rivalcfg/blob/master/LICENSE. Its Aerox wired/wireless profiles and battery implementation are protocol references. Installing dependencies preserves their distribution metadata and license files in the isolated environment.

## HIDAPI and Python bindings

https://github.com/libusb/hidapi
https://github.com/trezor/cython-hidapi

The installed system library and Python binding have their own upstream license notices. Consult those distributions for complete terms. They are not relicensed by this project and are not checked into this repository.

## Desktop services

Quickshell, Omarchy, Qt, BlueZ, UPower and Python are external runtime components under their respective licenses. No copies are included here.

SteelSeries, Arctis, Nova and Aerox are product names belonging to their respective owners. This community project is not affiliated with or endorsed by SteelSeries.
