// Diagnostic helper for hardware stale-handling verification.
//
// Temporarily disables / re-enables the receiver on /dev/ttyS5 by clearing
// / setting CREAD in the shared termios. This simulates an interrupted UART
// reception WITHOUT transmitting anything to the vehicle. The original
// termios is restored on exit.
//
// Usage (on device):
//   uart_rx_toggle disable   # clear CREAD, wait, restore
//   uart_rx_toggle enable    # ensure CREAD set
//   uart_rx_toggle status    # print CREAD state

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>

namespace {
constexpr const char* kUart = "/dev/ttyS5";

bool applyCreard(bool enable) {
    const int fd = open(kUart, O_RDONLY | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) {
        std::perror("open");
        return false;
    }
    termios tio{};
    if (tcgetattr(fd, &tio) != 0) {
        std::perror("tcgetattr");
        close(fd);
        return false;
    }
    const bool was_enabled = (tio.c_cflag & CREAD) != 0;
    if (enable) {
        tio.c_cflag |= static_cast<tcflag_t>(CREAD);
    } else {
        tio.c_cflag &= static_cast<tcflag_t>(~CREAD);
    }
    if (tcsetattr(fd, TCSANOW, &tio) != 0) {
        std::perror("tcsetattr");
        close(fd);
        return false;
    }
    std::printf("CREAD was %s, now %s\n",
                was_enabled ? "enabled" : "disabled",
                enable ? "enabled" : "disabled");
    close(fd);
    return true;
}

bool printStatus() {
    const int fd = open(kUart, O_RDONLY | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) {
        std::perror("open");
        return false;
    }
    termios tio{};
    if (tcgetattr(fd, &tio) != 0) {
        std::perror("tcgetattr");
        close(fd);
        return false;
    }
    std::printf("CREAD %s\n", (tio.c_cflag & CREAD) ? "enabled" : "disabled");
    close(fd);
    return true;
}
}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "usage: %s {disable|enable|status}\n", argv[0]);
        return 2;
    }
    if (std::strcmp(argv[1], "disable") == 0) {
        return applyCreard(false) ? 0 : 1;
    }
    if (std::strcmp(argv[1], "enable") == 0) {
        return applyCreard(true) ? 0 : 1;
    }
    if (std::strcmp(argv[1], "status") == 0) {
        return printStatus() ? 0 : 1;
    }
    std::fprintf(stderr, "unknown command: %s\n", argv[1]);
    return 2;
}
