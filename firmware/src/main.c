/*
 * main.c - command loop for the two-axis photogrammetry rig.
 *
 * One command per line over USB serial at 115200 baud. See help_text() below,
 * or the README, for the protocol.
 *
 * The "done" reply is what a PC-side capture application waits for before
 * firing the shutter. It is emitted from here rather than from the timer
 * interrupt, so that transmitting it never delays the other axis.
 */

#include "config.h"
#include "stepper.h"
#include "uart.h"

#include <avr/interrupt.h>
#include <stdint.h>

#define LINE_MAX 48

static uint8_t was_busy[AXIS_COUNT];

static void help_text(void)
{
    uart_puts(
        "commands:\n"
        "  M <axis> <steps> [rate]  move, signed steps, rate in steps/s\n"
        "  S                        status\n"
        "  Z [axis]                 zero position, both axes if omitted\n"
        "  H <axis> <0|1>           driver holding off or on\n"
        "  A                        abort all motion\n"
        "  ?                        this help\n"
        "axis is X or Y. replies: ok, err <reason>, done <axis>\n");
}

static void reply_ok(void)
{
    uart_puts("ok\n");
}

static void reply_err(const char *reason)
{
    uart_puts("err ");
    uart_puts(reason);
    uart_putc('\n');
}

static char axis_name(axis_t a)
{
    return (a == AXIS_X) ? 'X' : 'Y';
}

/* ------------------------------------------------------------- parsing --- */

static void skip_spaces(const char **p)
{
    while (**p == ' ' || **p == '\t') {
        (*p)++;
    }
}

static uint8_t to_upper(char c)
{
    if (c >= 'a' && c <= 'z') {
        return (uint8_t)(c - 'a' + 'A');
    }
    return (uint8_t)c;
}

/* Returns 1 on success and stores the axis in *out. */
static uint8_t parse_axis(const char **p, axis_t *out)
{
    skip_spaces(p);

    switch (to_upper(**p)) {
    case 'X':
        *out = AXIS_X;
        break;
    case 'Y':
        *out = AXIS_Y;
        break;
    default:
        return 0;
    }

    (*p)++;

    /* The axis letter must stand alone, so "XY" is rejected rather than read as X. */
    if (**p != '\0' && **p != ' ' && **p != '\t') {
        return 0;
    }
    return 1;
}

/*
 * Returns 1 on success and stores the value in *out. Rejects anything that is
 * not a complete signed decimal number, and rejects magnitudes that would not
 * fit a move, so a typo cannot silently become a huge rotation.
 */
static uint8_t parse_i32(const char **p, int32_t *out)
{
    uint8_t negative = 0;
    uint8_t digits = 0;
    uint32_t mag = 0;

    skip_spaces(p);

    if (**p == '-') {
        negative = 1;
        (*p)++;
    } else if (**p == '+') {
        (*p)++;
    }

    while (**p >= '0' && **p <= '9') {
        mag = (mag * 10UL) + (uint32_t)(**p - '0');
        if (mag > (uint32_t)STEP_COUNT_MAX) {
            return 0;
        }
        digits++;
        (*p)++;
    }

    if (digits == 0) {
        return 0;
    }
    if (**p != '\0' && **p != ' ' && **p != '\t') {
        return 0;
    }

    *out = negative ? -(int32_t)mag : (int32_t)mag;
    return 1;
}

static uint8_t at_end(const char *p)
{
    skip_spaces(&p);
    return (*p == '\0') ? 1 : 0;
}

/* ------------------------------------------------------------ commands --- */

static void cmd_move(const char *p)
{
    axis_t axis;
    int32_t steps;
    int32_t rate = (int32_t)STEP_RATE_DEFAULT;

    if (!parse_axis(&p, &axis)) {
        reply_err("axis");
        return;
    }
    if (!parse_i32(&p, &steps)) {
        reply_err("steps");
        return;
    }
    if (!at_end(p)) {
        if (!parse_i32(&p, &rate) || !at_end(p)) {
            reply_err("rate");
            return;
        }
    }
    if (rate < (int32_t)STEP_RATE_MIN || rate > (int32_t)STEP_RATE_MAX) {
        reply_err("rate range");
        return;
    }

    switch (stepper_move(axis, steps, (uint16_t)rate)) {
    case MOVE_OK:
        was_busy[axis] = 1;
        reply_ok();
        break;
    case MOVE_ERR_BUSY:
        reply_err("busy");
        break;
    case MOVE_ERR_STEPS:
        reply_err("steps range");
        break;
    default:
        reply_err("rate range");
        break;
    }
}

static void cmd_status(void)
{
    uart_puts("pos X=");
    uart_put_i32(stepper_position(AXIS_X));
    uart_puts(" Y=");
    uart_put_i32(stepper_position(AXIS_Y));

    uart_puts(" busy X=");
    uart_put_i32(stepper_busy(AXIS_X));
    uart_puts(" Y=");
    uart_put_i32(stepper_busy(AXIS_Y));

    uart_puts(" hold X=");
    uart_put_i32(stepper_get_hold(AXIS_X));
    uart_puts(" Y=");
    uart_put_i32(stepper_get_hold(AXIS_Y));
    uart_putc('\n');
}

static void cmd_zero(const char *p)
{
    axis_t axis;

    if (at_end(p)) {
        stepper_zero(AXIS_X);
        stepper_zero(AXIS_Y);
        reply_ok();
        return;
    }

    if (!parse_axis(&p, &axis) || !at_end(p)) {
        reply_err("axis");
        return;
    }

    stepper_zero(axis);
    reply_ok();
}

static void cmd_hold(const char *p)
{
    axis_t axis;
    int32_t on;

    if (!parse_axis(&p, &axis)) {
        reply_err("axis");
        return;
    }
    if (!parse_i32(&p, &on) || !at_end(p) || (on != 0 && on != 1)) {
        reply_err("expected 0 or 1");
        return;
    }

    stepper_set_hold(axis, (uint8_t)on);
    reply_ok();
}

static void handle_line(const char *line)
{
    const char *p = line;
    uint8_t cmd;

    skip_spaces(&p);
    cmd = to_upper(*p);
    p++;

    /* The command letter must stand alone. */
    if (cmd != '?' && *p != '\0' && *p != ' ' && *p != '\t') {
        reply_err("unknown command");
        return;
    }

    switch (cmd) {
    case 'M':
        cmd_move(p);
        break;
    case 'S':
        if (at_end(p)) {
            cmd_status();
        } else {
            reply_err("unexpected argument");
        }
        break;
    case 'Z':
        cmd_zero(p);
        break;
    case 'H':
        cmd_hold(p);
        break;
    case 'A':
        stepper_abort();
        reply_ok();
        break;
    case '?':
        help_text();
        break;
    default:
        reply_err("unknown command");
        break;
    }
}

/* ---------------------------------------------------------------- loop --- */

static void report_completions(void)
{
    uint8_t i;

    for (i = 0; i < (uint8_t)AXIS_COUNT; i++) {
        if (was_busy[i] && !stepper_busy((axis_t)i)) {
            was_busy[i] = 0;
            uart_puts("done ");
            uart_putc(axis_name((axis_t)i));
            uart_putc('\n');
        }
    }
}

int main(void)
{
    char line[LINE_MAX];

    was_busy[AXIS_X] = 0;
    was_busy[AXIS_Y] = 0;

    stepper_init();
    uart_init();
    sei();

    uart_puts("cheapscan ready\n");

    for (;;) {
        if (uart_poll_line(line, (uint8_t)sizeof(line))) {
            handle_line(line);
        }
        report_completions();
    }
}
