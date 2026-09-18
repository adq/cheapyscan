/*
 * uart.h - UART0 on the Mega 2560, which is the port wired to the on-board
 * ATmega16U2 USB interface.
 *
 * Receive is interrupt-driven into a ring buffer so that characters arriving
 * while a move is running are not lost. Transmit is blocking, which is fine
 * for the short replies this firmware sends; stepping continues regardless
 * because it runs from timer interrupts.
 */

#ifndef UART_H
#define UART_H

#include <stdint.h>

void uart_init(void);

void uart_putc(char c);
void uart_puts(const char *s);

/* Print a signed 32-bit value in decimal. */
void uart_put_i32(int32_t v);

/* Print a string, then a value, then a newline. */
void uart_kv(const char *key, int32_t v);

/*
 * Collect received characters into dst. Returns 1 when a complete line is
 * available, with dst holding a NUL-terminated string and the line terminator
 * stripped. Returns 0 otherwise. Non-blocking, so call it from the main loop.
 *
 * A line longer than size - 1 is truncated; the remainder is discarded up to
 * the next line terminator so the parser never sees a split command.
 */
uint8_t uart_poll_line(char *dst, uint8_t size);

#endif /* UART_H */
