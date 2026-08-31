#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>

namespace {

constexpr char kAlphabet[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

bool writeAll(const char* data, std::size_t size) {
    while (size != 0) {
        const ssize_t written = write(STDOUT_FILENO, data, size);
        if (written < 0) {
            if (errno == EINTR) {
                continue;
            }
            return false;
        }
        data += written;
        size -= static_cast<std::size_t>(written);
    }
    return true;
}

bool encodeFile(const char* path, std::uint8_t carry[3], std::size_t& carry_size) {
    const int input = open(path, O_RDONLY);
    if (input < 0) {
        std::fprintf(stderr, "open %s: %s\n", path, std::strerror(errno));
        return false;
    }

    std::uint8_t input_buffer[3072];
    char output_buffer[4096];
    while (true) {
        const ssize_t count = read(input, input_buffer, sizeof(input_buffer));
        if (count == 0) {
            break;
        }
        if (count < 0) {
            if (errno == EINTR) {
                continue;
            }
            std::fprintf(stderr, "read %s: %s\n", path, std::strerror(errno));
            close(input);
            return false;
        }

        std::size_t input_index = 0;
        std::size_t output_size = 0;
        while (input_index < static_cast<std::size_t>(count)) {
            carry[carry_size++] = input_buffer[input_index++];
            if (carry_size != 3) {
                continue;
            }
            output_buffer[output_size++] = kAlphabet[carry[0] >> 2U];
            output_buffer[output_size++] =
                kAlphabet[((carry[0] & 0x03U) << 4U) | (carry[1] >> 4U)];
            output_buffer[output_size++] =
                kAlphabet[((carry[1] & 0x0fU) << 2U) | (carry[2] >> 6U)];
            output_buffer[output_size++] = kAlphabet[carry[2] & 0x3fU];
            carry_size = 0;
        }
        if (!writeAll(output_buffer, output_size)) {
            close(input);
            return false;
        }
    }
    close(input);
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: %s FILE [FILE...]\n", argv[0]);
        return 2;
    }

    std::uint8_t carry[3] = {0, 0, 0};
    std::size_t carry_size = 0;
    for (int index = 1; index < argc; ++index) {
        if (!encodeFile(argv[index], carry, carry_size)) {
            return 1;
        }
    }

    if (carry_size != 0) {
        char tail[4];
        tail[0] = kAlphabet[carry[0] >> 2U];
        tail[1] = kAlphabet[
            ((carry[0] & 0x03U) << 4U) |
            (carry_size > 1 ? carry[1] >> 4U : 0U)];
        tail[2] = carry_size > 1
            ? kAlphabet[(carry[1] & 0x0fU) << 2U]
            : '=';
        tail[3] = '=';
        if (!writeAll(tail, sizeof(tail))) {
            return 1;
        }
    }
    return 0;
}
