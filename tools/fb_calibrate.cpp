// Screen-shape calibration helper for the trapezoidal dashboard.
//
// Writes a test pattern directly to /dev/fb0 (480x3840, 32bpp, two
// 480x1920 pages). Use with zkswe stopped so nothing redraws over it.
//
// Modes:
//   markers            white bg + colored squares at the four physical corners
//   mask tl,tr,bl,br   white bg + black trapezoid corner cuts (logical px)
//   poll               same as mask, but re-reads /tmp/screen_shape.txt
//                      every 100ms for live remote calibration
//
// Rotation: the panel is a rearview-mirror screen mounted 180deg rotated.
//   --rotate 0  physical == decoded framebuffer (no extra flip)
//   --rotate 180 physical == decoded framebuffer rotated 180 (default)

#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

namespace {

constexpr int kFbW = 480;
constexpr int kFbH = 3840;
constexpr int kPageH = 1920;
constexpr int kLogW = 1920;
constexpr int kLogH = 480;

int g_rotate = 180;

struct Color {
    std::uint8_t b, g, r, a;
};

Color makeColor(std::uint8_t r, std::uint8_t g, std::uint8_t b) {
    Color c{b, g, r, 255};
    return c;
}

// Maps logical (physical-view) coordinates to a framebuffer pixel.
// Assumes the app renders with rotateScreen=270 (decode ROTATE_270), and
// optionally applies a 180-degree panel flip on top.
void logicalToFb(int lx, int ly, int& fx, int& fy) {
    if (g_rotate == 180) {
        // decode: logical(LX,LY) = page[479-LY][LX]
        // physical(PX,PY) = logical(1919-PX, 479-PY)
        // => page[fy=1919-PX][fx=PY]
        fx = ly;
        fy = 1919 - lx;
    } else {
        // physical = decoded as-is => page[479-LY][LX]
        fx = 479 - ly;
        fy = lx;
    }
}

void setPixel(std::uint8_t* base, int fx, int fy, const Color& c) {
    if (fx < 0 || fx >= kFbW || fy < 0 || fy >= kFbH) {
        return;
    }
    std::uint8_t* p = base + (static_cast<std::uint64_t>(fy) * kFbW + fx) * 4;
    p[0] = c.b;
    p[1] = c.g;
    p[2] = c.r;
    p[3] = c.a;
}

void fillScreen(std::uint8_t* base, const Color& c) {
    for (int y = 0; y < kFbH; ++y) {
        for (int x = 0; x < kFbW; ++x) {
            setPixel(base, x, y, c);
        }
    }
}

void fillLogicalRect(
    std::uint8_t* base,
    int x0,
    int y0,
    int w,
    int h,
    const Color& c) {
    for (int ly = y0; ly < y0 + h && ly < kLogH; ++ly) {
        for (int lx = x0; lx < x0 + w && lx < kLogW; ++lx) {
            int fx, fy;
            logicalToFb(lx, ly, fx, fy);
            setPixel(base, fx, fy, c);
            setPixel(base, fx, fy + kPageH, c);
        }
    }
}

// Fills the four corner triangles (in logical coords) with the mask color.
void fillMask(
    std::uint8_t* base,
    int tl,
    int tr,
    int bl,
    int br,
    const Color& c) {
    // top-left: from (0,0) to (tl,0) and (bl,H)
    for (int ly = 0; ly < kLogH; ++ly) {
        const int x_limit = tl + (bl - tl) * ly / kLogH;
        for (int lx = 0; lx < x_limit; ++lx) {
            int fx, fy;
            logicalToFb(lx, ly, fx, fy);
            setPixel(base, fx, fy, c);
            setPixel(base, fx, fy + kPageH, c);
        }
    }
    // top-right
    for (int ly = 0; ly < kLogH; ++ly) {
        const int x_limit =
            kLogW - tr - (br - tr) * ly / kLogH;
        for (int lx = x_limit; lx < kLogW; ++lx) {
            int fx, fy;
            logicalToFb(lx, ly, fx, fy);
            setPixel(base, fx, fy, c);
            setPixel(base, fx, fy + kPageH, c);
        }
    }
}

bool readShapeFile(int& tl, int& tr, int& bl, int& br) {
    FILE* f = fopen("/tmp/screen_shape.txt", "r");
    if (f == nullptr) {
        return false;
    }
    const int n = std::fscanf(f, "%d,%d,%d,%d", &tl, &tr, &bl, &br);
    std::fclose(f);
    return n == 4;
}

int runPattern(std::uint8_t* base, int tl, int tr, int bl, int br) {
    const Color white = makeColor(240, 240, 240);
    const Color black = makeColor(0, 0, 0);
    fillScreen(base, white);
    fillMask(base, tl, tr, bl, br, black);
    return 0;
}

int runMarkers(std::uint8_t* base) {
    const Color white = makeColor(240, 240, 240);
    const Color red = makeColor(255, 0, 0);
    const Color green = makeColor(0, 255, 0);
    const Color blue = makeColor(0, 0, 255);
    const Color yellow = makeColor(255, 255, 0);
    fillScreen(base, white);
    fillLogicalRect(base, 40, 40, 120, 120, red);
    fillLogicalRect(base, kLogW - 160, 40, 120, 120, green);
    fillLogicalRect(base, 40, kLogH - 160, 120, 120, blue);
    fillLogicalRect(base, kLogW - 160, kLogH - 160, 120, 120, yellow);
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--rotate") == 0 && i + 1 < argc) {
            g_rotate = std::atoi(argv[++i]);
        }
    }

    const int fd = open("/dev/fb0", O_RDWR);
    if (fd < 0) {
        std::perror("open /dev/fb0");
        return 1;
    }
    std::uint8_t* base = static_cast<std::uint8_t*>(
        mmap(nullptr, kFbW * kFbH * 4, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0));
    if (base == MAP_FAILED) {
        std::perror("mmap");
        close(fd);
        return 1;
    }

    int result = 0;
    if (argc >= 2 && std::strcmp(argv[1], "markers") == 0) {
        result = runMarkers(base);
        std::printf("markers written (rotate=%d)\n", g_rotate);
    } else if (argc >= 6 && std::strcmp(argv[1], "mask") == 0) {
        result = runPattern(
            base,
            std::atoi(argv[2]),
            std::atoi(argv[3]),
            std::atoi(argv[4]),
            std::atoi(argv[5]));
        std::printf("mask written\n");
    } else if (argc >= 2 && std::strcmp(argv[1], "poll") == 0) {
        int tl = 120, tr = 120, bl = 260, br = 260;
        std::printf("polling /tmp/screen_shape.txt (rotate=%d)\n", g_rotate);
        while (true) {
            if (readShapeFile(tl, tr, bl, br)) {
                runPattern(base, tl, tr, bl, br);
                std::printf("shape %d,%d,%d,%d\n", tl, tr, bl, br);
            }
            usleep(100000);
        }
    } else {
        std::fprintf(
            stderr,
            "usage: %s {markers|mask tl,tr,bl,br|poll} [--rotate 0|180]\n",
            argv[0]);
        result = 2;
    }

    munmap(base, kFbW * kFbH * 4);
    close(fd);
    return result;
}
