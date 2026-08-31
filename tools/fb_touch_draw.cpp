// Touch-trace tool for calibrating the trapezoidal dashboard screen.
//
// Shows a pure white screen on /dev/fb0 and leaves black brush strokes
// wherever the gt9xx touch panel is touched, so the user can trace the
// physical screen edge. Only stroke deltas are written (no full-screen
// redraws), so the image does not flicker.
//
// Usage:
//   fb_touch_draw [--device /dev/input/event0] [--brush N] [--clear]
//     [--touch-rotate 0|90|180|270]
//
// Touch coordinates are appended to /tmp/touch_log.txt for mapping debug.

#include <cstdint>
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <linux/input.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

namespace {

constexpr int kFbW = 480;
constexpr int kFbH = 3840;
constexpr int kPageH = 1920;
constexpr int kLogW = 1920;
constexpr int kLogH = 480;

int g_brush = 9;
int g_touch_rotate = 0;
int g_abs_x_min = 0;
int g_abs_x_max = 0;
int g_abs_y_min = 0;
int g_abs_y_max = 0;
bool g_has_ranges = false;

// Logical (1920x480, physical view) -> framebuffer pixel (rotate=180 panel).
void logicalToFb(int lx, int ly, int& fx, int& fy) {
    fx = ly;
    fy = 1919 - lx;
}

void setFbPixel(std::uint8_t* base, int fx, int fy, bool black) {
    if (fx < 0 || fx >= kFbW || fy < 0 || fy >= kFbH) {
        return;
    }
    std::uint8_t* p = base + (static_cast<std::uint64_t>(fy) * kFbW + fx) * 4;
    if (black) {
        p[0] = p[1] = p[2] = 0;
        p[3] = 255;
    } else {
        p[0] = p[1] = p[2] = 235;
        p[3] = 255;
    }
}

void setLogicalPixel(std::uint8_t* base, int lx, int ly, bool black) {
    int fx, fy;
    logicalToFb(lx, ly, fx, fy);
    setFbPixel(base, fx, fy, black);
    setFbPixel(base, fx, fy + kPageH, black);
}

void fillWhite(std::uint8_t* base) {
    for (int y = 0; y < kFbH; ++y) {
        for (int x = 0; x < kFbW; ++x) {
            setFbPixel(base, x, y, false);
        }
    }
}

// Draws a filled circle at (cx,cy) in logical coords.
void brushCircle(std::uint8_t* base, int cx, int cy, bool black) {
    const int r2 = g_brush * g_brush;
    for (int dy = -g_brush; dy <= g_brush; ++dy) {
        for (int dx = -g_brush; dx <= g_brush; ++dx) {
            if (dx * dx + dy * dy <= r2) {
                setLogicalPixel(base, cx + dx, cy + dy, black);
            }
        }
    }
}

// Draws a line from (x0,y0) to (x1,y1) with the brush.
void brushLine(std::uint8_t* base, int x0, int y0, int x1, int y1) {
    const int steps = std::max(std::abs(x1 - x0), std::abs(y1 - y0)) + 1;
    for (int i = 0; i <= steps; ++i) {
        const int x = x0 + (x1 - x0) * i / steps;
        const int y = y0 + (y1 - y0) * i / steps;
        brushCircle(base, x, y, true);
    }
}

// Maps raw touch coordinates to logical 1920x480.
void touchToLogical(int tx, int ty, int& lx, int& ly) {
    const int xr = g_abs_x_max - g_abs_x_min + 1;
    const int yr = g_abs_y_max - g_abs_y_min + 1;
    const int nx = xr > 0 ? (tx - g_abs_x_min) * kLogW / xr : tx;
    const int ny = yr > 0 ? (ty - g_abs_y_min) * kLogH / yr : ty;
    switch (g_touch_rotate % 360) {
        case 90:
            lx = kLogH - 1 - ny;
            ly = nx;
            break;
        case 180:
            lx = kLogW - 1 - nx;
            ly = kLogH - 1 - ny;
            break;
        case 270:
            lx = ny;
            ly = kLogW - 1 - nx;
            break;
        case 0:
        default:
            lx = nx;
            ly = ny;
            break;
    }
}

void logTouch(int tx, int ty, int lx, int ly) {
    FILE* f = fopen("/tmp/touch_log.txt", "a");
    if (f != nullptr) {
        std::fprintf(f, "%d,%d -> %d,%d\n", tx, ty, lx, ly);
        std::fclose(f);
    }
}

}  // namespace

int main(int argc, char** argv) {
    const char* dev_path = "/dev/input/event0";
    bool clear_only = false;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--device") == 0 && i + 1 < argc) {
            dev_path = argv[++i];
        } else if (std::strcmp(argv[i], "--brush") == 0 && i + 1 < argc) {
            g_brush = std::atoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--clear") == 0) {
            clear_only = true;
        } else if (std::strcmp(argv[i], "--touch-rotate") == 0 &&
                   i + 1 < argc) {
            g_touch_rotate = std::atoi(argv[++i]);
        }
    }

    const int fb = open("/dev/fb0", O_RDWR);
    if (fb < 0) {
        std::perror("open fb0");
        return 1;
    }
    std::uint8_t* base = static_cast<std::uint8_t*>(
        mmap(nullptr, kFbW * kFbH * 4, PROT_READ | PROT_WRITE, MAP_SHARED, fb, 0));
    if (base == MAP_FAILED) {
        std::perror("mmap fb0");
        close(fb);
        return 1;
    }
    fillWhite(base);

    const int in = open(dev_path, O_RDONLY | O_NONBLOCK);
    if (in < 0) {
        std::perror("open input");
        munmap(base, kFbW * kFbH * 4);
        close(fb);
        return 1;
    }

    struct input_absinfo absx{};
    struct input_absinfo absy{};
    // MT protocol B devices report ABS_MT_POSITION_X/Y; fall back to
    // legacy ABS_X/Y if those are not populated.
    if (ioctl(in, EVIOCGABS(ABS_MT_POSITION_X), &absx) == 0 &&
        absx.maximum > absx.minimum) {
        g_abs_x_min = absx.minimum;
        g_abs_x_max = absx.maximum;
        std::printf("ABS_MT_POSITION_X range %d..%d\n",
                    absx.minimum, absx.maximum);
    } else if (ioctl(in, EVIOCGABS(ABS_X), &absx) == 0 &&
               absx.maximum > absx.minimum) {
        g_abs_x_min = absx.minimum;
        g_abs_x_max = absx.maximum;
        std::printf("ABS_X range %d..%d\n", absx.minimum, absx.maximum);
    }
    if (ioctl(in, EVIOCGABS(ABS_MT_POSITION_Y), &absy) == 0 &&
        absy.maximum > absy.minimum) {
        g_abs_y_min = absy.minimum;
        g_abs_y_max = absy.maximum;
        std::printf("ABS_MT_POSITION_Y range %d..%d\n",
                    absy.minimum, absy.maximum);
    } else if (ioctl(in, EVIOCGABS(ABS_Y), &absy) == 0 &&
               absy.maximum > absy.minimum) {
        g_abs_y_min = absy.minimum;
        g_abs_y_max = absy.maximum;
        std::printf("ABS_Y range %d..%d\n", absy.minimum, absy.maximum);
    }
    g_has_ranges = g_abs_x_max > g_abs_x_min && g_abs_y_max > g_abs_y_min;
    if (!g_has_ranges) {
        // Unknown ranges: assume the panel matches 1920x480 logical.
        g_abs_x_max = kLogW - 1;
        g_abs_y_max = kLogH - 1;
        std::printf("no ABS ranges reported; assuming %dx%d\n",
                    kLogW, kLogH);
    }

    if (clear_only) {
        std::printf("screen cleared\n");
        return 0;
    }

    std::printf("drawing... touch the screen (brush=%d, rotate=%d)\n",
                g_brush, g_touch_rotate);

    bool touching = false;
    int mt_tracking = -2;
    int cur_tx = 0;
    int cur_ty = 0;
    int last_lx = 0;
    int last_ly = 0;

    // 16-byte input_event on 32-bit ARM.
    std::uint8_t buf[64];
    while (true) {
        const ssize_t n = read(in, buf, sizeof(buf));
        if (n < 0) {
            if (errno == EAGAIN || errno == EINTR) {
                usleep(5000);
                continue;
            }
            break;
        }
        for (ssize_t off = 0; off + 16 <= n; off += 16) {
            std::uint16_t type;
            std::uint16_t code;
            std::int32_t value;
            std::memcpy(&type, buf + off + 8, 2);
            std::memcpy(&code, buf + off + 10, 2);
            std::memcpy(&value, buf + off + 12, 4);

            if (type == EV_ABS) {
                if (code == ABS_MT_POSITION_X || code == ABS_X) {
                    cur_tx = value;
                } else if (code == ABS_MT_POSITION_Y || code == ABS_Y) {
                    cur_ty = value;
                } else if (code == ABS_MT_TRACKING_ID) {
                    mt_tracking = value;
                }
            } else if (type == EV_KEY && code == BTN_TOUCH) {
                if (value == 1 && !touching) {
                    touching = true;
                    int lx, ly;
                    touchToLogical(cur_tx, cur_ty, lx, ly);
                    last_lx = lx;
                    last_ly = ly;
                    brushCircle(base, lx, ly, true);
                    logTouch(cur_tx, cur_ty, lx, ly);
                } else if (value == 0) {
                    touching = false;
                }
            } else if (type == EV_SYN) {
                const bool mt_down = mt_tracking >= 0;
                if (mt_down && !touching) {
                    touching = true;
                    int lx, ly;
                    touchToLogical(cur_tx, cur_ty, lx, ly);
                    last_lx = lx;
                    last_ly = ly;
                    brushCircle(base, lx, ly, true);
                    logTouch(cur_tx, cur_ty, lx, ly);
                } else if (!mt_down) {
                    touching = false;
                }
                if (touching) {
                    int lx, ly;
                    touchToLogical(cur_tx, cur_ty, lx, ly);
                    if (lx != last_lx || ly != last_ly) {
                        brushLine(base, last_lx, last_ly, lx, ly);
                        last_lx = lx;
                        last_ly = ly;
                    }
                }
            }
        }
    }

    munmap(base, kFbW * kFbH * 4);
    close(fb);
    close(in);
    return 0;
}
