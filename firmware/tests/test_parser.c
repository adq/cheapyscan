/* SPDX-License-Identifier: MIT */
/* Copyright (c) 2026 Andrew de Quincey */

/*
 * Host-side test for the command parser in src/main.c.
 *
 * The firmware itself can only be checked on the board, but the parser is pure
 * logic and is where a mistake is most likely and least visible. This compiles
 * src/main.c natively with the UART and stepper layers replaced by stubs, so
 * every command can be fed in and its reply and its effect on the stepper
 * layer checked.
 *
 * Build and run with tests/run.sh.
 */

#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "../src/config.h"
#include "../src/stepper.h"

/* ------------------------------------------------------------ uart stub --- */

static char out_buf[4096];
static size_t out_len;

static void out_reset(void) { out_len = 0; out_buf[0] = '\0'; }

void uart_init(void) { }

void uart_putc(char c)
{
    if (out_len + 1 < sizeof(out_buf)) {
        out_buf[out_len++] = c;
        out_buf[out_len] = '\0';
    }
}

void uart_puts(const char *s)
{
    while (*s) {
        uart_putc(*s++);
    }
}

void uart_put_i32(int32_t v)
{
    char tmp[16];
    snprintf(tmp, sizeof(tmp), "%ld", (long)v);
    uart_puts(tmp);
}

void uart_kv(const char *key, int32_t v)
{
    uart_puts(key);
    uart_put_i32(v);
    uart_putc('\n');
}

/* The test drives handle_line() directly, so this is never expected to fire. */
uint8_t uart_poll_line(char *dst, uint8_t size)
{
    (void)dst;
    (void)size;
    return 0;
}

/* --------------------------------------------------------- stepper stub --- */

static struct {
    int32_t       position[AXIS_COUNT];
    uint8_t       busy[AXIS_COUNT];
    uint8_t       hold[AXIS_COUNT];
    int           move_calls;
    axis_t        last_axis;
    int32_t       last_steps;
    uint16_t      last_rate;
    int           abort_calls;
    move_result_t next_result;
} sim;

static void sim_reset(void)
{
    memset(&sim, 0, sizeof(sim));
    sim.hold[AXIS_X] = HOLD_DEFAULT;
    sim.hold[AXIS_Y] = HOLD_DEFAULT;
    sim.next_result = MOVE_OK;
}

void stepper_init(void) { }

move_result_t stepper_move(axis_t a, int32_t steps, uint16_t rate)
{
    sim.move_calls++;
    sim.last_axis = a;
    sim.last_steps = steps;
    sim.last_rate = rate;

    if (sim.next_result == MOVE_OK) {
        sim.busy[a] = 1;
    }
    return sim.next_result;
}

void stepper_abort(void)
{
    sim.abort_calls++;
    sim.busy[AXIS_X] = 0;
    sim.busy[AXIS_Y] = 0;
}

uint8_t stepper_busy(axis_t a) { return sim.busy[a]; }
int32_t stepper_position(axis_t a) { return sim.position[a]; }
void stepper_zero(axis_t a) { sim.position[a] = 0; }
void stepper_set_hold(axis_t a, uint8_t on) { sim.hold[a] = on ? 1 : 0; }
uint8_t stepper_get_hold(axis_t a) { return sim.hold[a]; }

/* ------------------------------------------------- the code under test --- */

/*
 * main.c defines main(); rename it so this file's main() wins, and pull in the
 * static parser functions.
 */
#define main firmware_main
#include "../src/main.c"
#undef main

/* ----------------------------------------------------------- assertions --- */

static int failures;
static int checks;

static void check(int condition, const char *what)
{
    checks++;
    if (!condition) {
        failures++;
        printf("  FAIL  %s\n", what);
    }
}

/* Feed one command line and compare the complete reply. */
static void expect_reply(const char *line, const char *want)
{
    out_reset();
    handle_line(line);
    checks++;
    if (strcmp(out_buf, want) != 0) {
        failures++;
        printf("  FAIL  \"%s\" replied \"%s\", wanted \"%s\"\n",
               line, out_buf, want);
    }
}

static void expect_contains(const char *line, const char *want)
{
    out_reset();
    handle_line(line);
    checks++;
    if (strstr(out_buf, want) == NULL) {
        failures++;
        printf("  FAIL  \"%s\" reply lacked \"%s\" (got \"%s\")\n",
               line, want, out_buf);
    }
}

/* --------------------------------------------------------------- tests --- */

static void test_move_accepted(void)
{
    sim_reset();
    expect_reply("M X 1600 400", "ok\n");
    check(sim.move_calls == 1, "move issued once");
    check(sim.last_axis == AXIS_X, "move went to X");
    check(sim.last_steps == 1600, "step count passed through");
    check(sim.last_rate == 400, "rate passed through");

    sim_reset();
    expect_reply("M Y -800 50", "ok\n");
    check(sim.last_axis == AXIS_Y, "move went to Y");
    check(sim.last_steps == -800, "negative step count kept its sign");
    check(sim.last_rate == 50, "explicit rate kept");
}

static void test_move_defaults_and_forms(void)
{
    sim_reset();
    expect_reply("M X 100", "ok\n");
    check(sim.last_rate == STEP_RATE_DEFAULT, "omitted rate uses the default");

    sim_reset();
    expect_reply("m x 100 200", "ok\n");
    check(sim.move_calls == 1, "lower case command and axis accepted");

    sim_reset();
    expect_reply("   M   X   +250   300   ", "ok\n");
    check(sim.last_steps == 250, "leading plus and extra spaces accepted");
    check(sim.last_rate == 300, "rate parsed after extra spaces");
}

static void test_move_rejected(void)
{
    sim_reset();
    expect_reply("M Z 100", "err axis\n");
    check(sim.move_calls == 0, "bad axis issues no move");

    sim_reset();
    expect_reply("M X", "err steps\n");
    check(sim.move_calls == 0, "missing step count issues no move");

    sim_reset();
    expect_reply("M X abc", "err steps\n");

    sim_reset();
    expect_reply("M X 100abc", "err steps\n");
    check(sim.move_calls == 0, "trailing junk on the step count is rejected");

    sim_reset();
    expect_reply("M X 100 9999", "err rate range\n");
    check(sim.move_calls == 0, "rate above the maximum issues no move");

    sim_reset();
    expect_reply("M X 100 1", "err rate range\n");
    check(sim.move_calls == 0, "rate below the minimum issues no move");

    sim_reset();
    expect_reply("M X 100 400 500", "err rate\n");
    check(sim.move_calls == 0, "a third argument is rejected");

    sim_reset();
    expect_reply("M XY 100", "err axis\n");
    check(sim.move_calls == 0, "a two letter axis is rejected, not truncated");

    /* Larger than STEP_COUNT_MAX, so it must not wrap into a small move. */
    sim_reset();
    expect_reply("M X 99999999", "err steps\n");
    check(sim.move_calls == 0, "an oversized step count is rejected");
}

static void test_move_busy(void)
{
    sim_reset();
    sim.next_result = MOVE_ERR_BUSY;
    expect_reply("M X 100", "err busy\n");
}

static void test_status(void)
{
    sim_reset();
    sim.position[AXIS_X] = -1234;
    sim.position[AXIS_Y] = 56;
    sim.busy[AXIS_Y] = 1;
    sim.hold[AXIS_X] = 0;
    sim.hold[AXIS_Y] = 1;

    expect_reply("S",
                 "pos X=-1234 Y=56 busy X=0 Y=1 hold X=0 Y=1\n");

    sim_reset();
    expect_reply("S extra", "err unexpected argument\n");
}

static void test_zero(void)
{
    sim_reset();
    sim.position[AXIS_X] = 500;
    sim.position[AXIS_Y] = 900;
    expect_reply("Z", "ok\n");
    check(sim.position[AXIS_X] == 0, "bare Z zeroed X");
    check(sim.position[AXIS_Y] == 0, "bare Z zeroed Y");

    sim_reset();
    sim.position[AXIS_X] = 500;
    sim.position[AXIS_Y] = 900;
    expect_reply("Z X", "ok\n");
    check(sim.position[AXIS_X] == 0, "Z X zeroed X");
    check(sim.position[AXIS_Y] == 900, "Z X left Y alone");

    sim_reset();
    expect_reply("Z Q", "err axis\n");
}

static void test_hold(void)
{
    sim_reset();
    expect_reply("H X 0", "ok\n");
    check(sim.hold[AXIS_X] == 0, "H X 0 released X");
    check(sim.hold[AXIS_Y] == HOLD_DEFAULT, "H X 0 left Y alone");

    sim_reset();
    expect_reply("H Y 1", "ok\n");
    check(sim.hold[AXIS_Y] == 1, "H Y 1 held Y");

    sim_reset();
    expect_reply("H X 2", "err expected 0 or 1\n");
    expect_reply("H X", "err expected 0 or 1\n");
    expect_reply("H Q 1", "err axis\n");
}

static void test_abort_and_help(void)
{
    sim_reset();
    sim.busy[AXIS_X] = 1;
    expect_reply("A", "ok\n");
    check(sim.abort_calls == 1, "A aborted once");
    check(sim.busy[AXIS_X] == 0, "A cleared the busy flag");

    sim_reset();
    expect_contains("?", "M <axis> <steps>");
}

static void test_unknown(void)
{
    sim_reset();
    expect_reply("Q", "err unknown command\n");
    expect_reply("MOVE X 100", "err unknown command\n");
    check(sim.move_calls == 0, "an unknown command issues no move");
}

/*
 * The done reply is what a capture application waits on before firing the
 * shutter, so it must appear exactly once per completed move and must not
 * appear for an axis that never moved.
 */
static void test_done_reporting(void)
{
    sim_reset();
    was_busy[AXIS_X] = 0;
    was_busy[AXIS_Y] = 0;

    out_reset();
    handle_line("M X 100 400");
    check(was_busy[AXIS_X] == 1, "accepted move armed the done report");

    out_reset();
    report_completions();
    check(strcmp(out_buf, "") == 0, "no done while the axis is still busy");

    sim.busy[AXIS_X] = 0;
    out_reset();
    report_completions();
    check(strcmp(out_buf, "done X\n") == 0, "done X once the move finished");

    out_reset();
    report_completions();
    check(strcmp(out_buf, "") == 0, "done is not repeated");

    /* A rejected move must not arm a done report. */
    sim_reset();
    was_busy[AXIS_X] = 0;
    was_busy[AXIS_Y] = 0;
    sim.next_result = MOVE_ERR_BUSY;
    out_reset();
    handle_line("M Y 100");
    check(was_busy[AXIS_Y] == 0, "rejected move did not arm a done report");
    out_reset();
    report_completions();
    check(strcmp(out_buf, "") == 0, "no done for a rejected move");
}

int main(void)
{
    printf("parser tests\n");

    test_move_accepted();
    test_move_defaults_and_forms();
    test_move_rejected();
    test_move_busy();
    test_status();
    test_zero();
    test_hold();
    test_abort_and_help();
    test_unknown();
    test_done_reporting();

    printf("%d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
