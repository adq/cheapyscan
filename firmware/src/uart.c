#include "config.h"
#include "uart.h"

#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/atomic.h>

#define RX_BUF_SIZE 64  /* must be a power of two */
#define RX_BUF_MASK (RX_BUF_SIZE - 1)

static volatile uint8_t rx_buf[RX_BUF_SIZE];
static volatile uint8_t rx_head;
static volatile uint8_t rx_tail;

/* State for uart_poll_line(), touched only by the main loop. */
static uint8_t line_len;
static uint8_t line_overflow;

void uart_init(void)
{
    /*
     * Double-speed mode, so UBRR = F_CPU / (8 * baud) - 1. At 16MHz and a
     * requested 115200 that is 16, which yields 117647 baud in practice. The
     * resulting 2.1 percent error is inside the tolerance for 8N1 framing and
     * is exactly what the Arduino core does on this board.
     */
    const uint16_t ubrr = (uint16_t)((F_CPU / (8UL * BAUD_RATE)) - 1UL);

    UBRR0H = (uint8_t)(ubrr >> 8);
    UBRR0L = (uint8_t)(ubrr & 0xFF);

    UCSR0A = (uint8_t)_BV(U2X0);
    UCSR0C = (uint8_t)(_BV(UCSZ01) | _BV(UCSZ00));   /* 8 data bits, no parity, 1 stop */
    UCSR0B = (uint8_t)(_BV(RXEN0) | _BV(TXEN0) | _BV(RXCIE0));

    rx_head = 0;
    rx_tail = 0;
    line_len = 0;
    line_overflow = 0;
}

ISR(USART0_RX_vect)
{
    const uint8_t c = UDR0;
    const uint8_t next = (uint8_t)((rx_head + 1) & RX_BUF_MASK);

    /* Drop the character rather than overwrite unread data. */
    if (next != rx_tail) {
        rx_buf[rx_head] = c;
        rx_head = next;
    }
}

/* Returns 1 and stores a character in *out, or returns 0 if none waiting. */
static uint8_t rx_take(uint8_t *out)
{
    uint8_t got = 0;

    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        if (rx_head != rx_tail) {
            *out = rx_buf[rx_tail];
            rx_tail = (uint8_t)((rx_tail + 1) & RX_BUF_MASK);
            got = 1;
        }
    }
    return got;
}

void uart_putc(char c)
{
    while (!(UCSR0A & _BV(UDRE0))) {
        /* wait for the transmit buffer to empty */
    }
    UDR0 = (uint8_t)c;
}

void uart_puts(const char *s)
{
    while (*s != '\0') {
        uart_putc(*s++);
    }
}

void uart_put_i32(int32_t v)
{
    char buf[12];
    uint8_t i = 0;
    uint32_t mag;

    if (v < 0) {
        uart_putc('-');
        /* Negate in unsigned space so INT32_MIN is handled correctly. */
        mag = (uint32_t)(-(v + 1)) + 1UL;
    } else {
        mag = (uint32_t)v;
    }

    do {
        buf[i++] = (char)('0' + (mag % 10UL));
        mag /= 10UL;
    } while (mag != 0UL);

    while (i > 0) {
        uart_putc(buf[--i]);
    }
}

void uart_kv(const char *key, int32_t v)
{
    uart_puts(key);
    uart_put_i32(v);
    uart_putc('\n');
}

uint8_t uart_poll_line(char *dst, uint8_t size)
{
    uint8_t c;

    while (rx_take(&c)) {
        if (c == '\r') {
            continue;  /* tolerate CRLF from terminal programs */
        }

        if (c == '\n') {
            const uint8_t overflowed = line_overflow;
            const uint8_t len = line_len;

            line_len = 0;
            line_overflow = 0;

            if (overflowed) {
                continue;  /* discard the truncated line entirely */
            }
            if (len == 0) {
                continue;  /* ignore blank lines */
            }

            dst[len] = '\0';
            return 1;
        }

        if (line_len < (uint8_t)(size - 1)) {
            dst[line_len++] = (char)c;
        } else {
            line_overflow = 1;
        }
    }

    return 0;
}
